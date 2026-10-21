import smtplib
import os
import re
import time
import config
import logging
import base64
import requests
from email.message import EmailMessage
from jinja2 import Environment, FileSystemLoader

logger = logging.getLogger(__name__)
_TEMPLATES_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", config.TEMPLATES_DIR))
env = Environment(loader=FileSystemLoader(_TEMPLATES_DIR))


class SMTPConnectionManager:
    """
    Persistent, self-healing SMTP connection manager for bulk email dispatch.
    Reuses an authenticated TLS connection across hundreds of emails to eliminate
    the overhead and rate-limit triggers of reconnecting for every single recipient.
    Automatically reconnects if the socket drops or server times out.
    """
    def __init__(self, host=None, port=None, user=None, password=None, timeout=20, delay_between_sends=0.15):
        self.host = host or config.SMTP_SERVER
        self.port = port or config.SMTP_PORT
        self.user = user or config.SENDER_EMAIL
        self.password = password or config.SENDER_PASS
        self.timeout = timeout
        self.delay_between_sends = delay_between_sends
        self.smtp = None
        self.is_connected = False

    def connect(self):
        """Establish TLS connection and authenticate with SMTP server."""
        if not self.user or not self.password:
            raise ValueError("Sender email and password/app password are not configured.")

        try:
            if self.smtp:
                try:
                    self.smtp.quit()
                except Exception:
                    pass

            self.smtp = smtplib.SMTP(self.host, self.port, timeout=self.timeout)
            self.smtp.ehlo()
            self.smtp.starttls()
            self.smtp.ehlo()
            self.smtp.login(self.user, self.password)
            self.is_connected = True
            logger.info(f"Connected and authenticated to SMTP server {self.host}:{self.port}")
        except Exception as e:
            self.is_connected = False
            self.smtp = None
            raise e

    def send_message(self, msg: EmailMessage, retry_count=1) -> tuple[bool, str]:
        """Send message using the active connection, reconnecting on disconnect."""
        for attempt in range(retry_count + 1):
            try:
                if not self.is_connected or not self.smtp:
                    self.connect()

                self.smtp.send_message(msg)

                if self.delay_between_sends > 0:
                    time.sleep(self.delay_between_sends)

                return True, "Success"

            except (smtplib.SMTPServerDisconnected, smtplib.SMTPConnectError, ConnectionResetError, BrokenPipeError, TimeoutError) as net_err:
                logger.warning(f"SMTP connection lost ({type(net_err).__name__}). Reconnecting (attempt {attempt + 1}/{retry_count + 1})...")
                self.is_connected = False
                time.sleep(1.0)
                try:
                    self.connect()
                except Exception as reconnect_err:
                    if attempt == retry_count:
                        return False, f"SMTP Reconnection Failed: {reconnect_err}"

            except smtplib.SMTPRecipientsRefused as e:
                logger.error(f"Recipient refused: {e}")
                return False, f"Recipient Refused: {e}"

            except smtplib.SMTPAuthenticationError as e:
                logger.error(f"SMTP Auth error: {e}")
                self.is_connected = False
                return False, f"SMTP Auth Error: {e}"

            except smtplib.SMTPResponseException as e:
                err_code = e.smtp_code
                err_msg = e.smtp_error.decode('utf-8', errors='ignore') if isinstance(e.smtp_error, bytes) else str(e.smtp_error)
                logger.error(f"SMTP Error {err_code}: {err_msg}")
                if err_code == 421 and attempt < retry_count:
                    logger.warning(f"SMTP 421 temporary limit. Backing off 3s before retry {attempt + 2}...")
                    time.sleep(3.0)
                    try:
                        self.connect()
                        continue
                    except Exception:
                        pass
                lower_err = err_msg.lower()
                if "quota" in lower_err or "limit" in lower_err or err_code == 452 or "daily" in lower_err:
                    return False, f"Daily Sending Limit / Quota Exceeded ({err_code}): {err_msg}"
                return False, f"SMTP Error ({err_code}): {err_msg}"

            except Exception as e:
                logger.error(f"Unexpected email error: {e}")
                if attempt == retry_count:
                    return False, f"Email Dispatch Error: {type(e).__name__} - {e}"
                time.sleep(1.0)

        return False, "Email sending failed after retries."

    def close(self):
        """Cleanly terminate the SMTP session."""
        if self.smtp:
            try:
                self.smtp.quit()
            except Exception:
                pass
            finally:
                self.smtp = None
                self.is_connected = False

    def __enter__(self):
        try:
            self.connect()
        except Exception as e:
            logger.warning(f"Pre-connect failed: {e}. Will attempt on first send.")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


# In-memory tracking of exhausted GAS Web App endpoints for the current runtime session
_EXHAUSTED_GAS_URLS = set()

def reset_exhausted_gas_urls():
    """Resets the exhausted URL cache."""
    global _EXHAUSTED_GAS_URLS
    _EXHAUSTED_GAS_URLS.clear()


def send_certificate_email(
    to_email: str,
    name: str,
    pdf_path: str,
    event: str = "Event",
    tier: str = "Participant",
    cert_id: str = "",
    cert_type: str = "Certificate of Participation",
    smtp_manager: SMTPConnectionManager = None
) -> tuple[bool, str]:
    """
    Sends certificate PDF to recipient with enterprise-grade resilience:
      1. Tries Google Apps Script Proxy (supports comma-separated pool of multiple GAS URLs).
      2. If a GAS URL hits Google's 100/day limit ('Service invoked too many times'), it cycles to the next URL.
      3. If all GAS endpoints are exhausted, it AUTOMATICALLY falls back to Direct SMTP seamlessly.
      4. If both fail, it provides an actionable error message with exact remediation steps.
    """
    try:
        if cert_type == "CERT_Template":
            cert_type = "Certificate of Participation"

        # Sanitize text inputs & prevent CRLF header injection
        clean_name = re.sub(r'[\r\n\t]+', ' ', name or '').strip().title()
        clean_event = re.sub(r'[\r\n\t]+', ' ', event or 'Event').strip()
        safe_name_str = re.sub(r'[^a-zA-Z0-9_\-]', '_', clean_name)[:35].strip('_')
        if not safe_name_str:
            safe_name_str = "Certificate"
        attachment_filename = f"{safe_name_str}_Certificate.pdf"
        
        subject = re.sub(r'[\r\n\t]+', ' ', f"Your {cert_type} - {clean_event}").strip()
        if not subject:
            subject = "Your Certificate"

        # Load and render template
        template = env.get_template('email_template.html')
        html_body = template.render(name=clean_name, event=clean_event, tier=tier, cert_id=cert_id, cert_type=cert_type)
        
        # Read PDF
        if not os.path.exists(pdf_path):
            logger.error(f"PDF missing at {pdf_path}")
            return False, "PDF generation failed or file is missing."
            
        with open(pdf_path, 'rb') as f:
            pdf_data = f.read()

        last_gas_err = None
        gas_attempted = False

        # Route 1: Google Apps Script Proxy Pool (if configured)
        if config.GAS_MAILER_URL:
            # Parse comma-separated or single GAS URLs
            all_gas_urls = [u.strip() for u in config.GAS_MAILER_URL.split(",") if u.strip()]
            active_gas_urls = [u for u in all_gas_urls if u not in _EXHAUSTED_GAS_URLS]

            if active_gas_urls:
                gas_attempted = True
                encoded_pdf = base64.b64encode(pdf_data).decode('utf-8')
                payload = {
                    "to": to_email,
                    "subject": subject,
                    "html": html_body,
                    "attachment_base64": encoded_pdf,
                    "filename": attachment_filename
                }

                for gas_url in active_gas_urls:
                    try:
                        logger.info(f"Attempting dispatch via GAS Proxy ({gas_url[:35]}...)...")
                        resp = requests.post(gas_url, json=payload, timeout=30)
                        try:
                            resp_json = resp.json()
                            if resp.status_code == 200 and resp_json.get('success'):
                                logger.info(f"Email dispatched successfully to {to_email} via GAS Proxy")
                                return True, "Success"
                            else:
                                err_detail = resp_json.get('error', resp.text)
                                last_gas_err = err_detail
                                logger.warning(f"GAS Proxy Error from {gas_url[:35]}...: {err_detail}")

                                # Detect Google Apps Script daily quota limit
                                if any(k in str(err_detail).lower() for k in [
                                    "too many times for one day",
                                    "service invoked too many times",
                                    "quota",
                                    "limit exceeded"
                                ]):
                                    _EXHAUSTED_GAS_URLS.add(gas_url)
                                    logger.warning(f"GAS endpoint {gas_url[:35]}... reached daily quota. Failing over...")
                                    continue
                                else:
                                    # Non-quota error, still try fallback
                                    break
                        except ValueError:
                            if "Access Denied" in resp.text or "accounts.google.com" in resp.text:
                                last_gas_err = "Google Apps Script Error: Access Denied. Ensure Web App is deployed with 'Who has access: Anyone'."
                            else:
                                snippet = resp.text.strip()[:160].replace('\n', ' ')
                                last_gas_err = f"Google Apps Script Error (non-JSON): {snippet}"
                            logger.error(last_gas_err)
                    except requests.Timeout:
                        last_gas_err = "Google Apps Script timed out after 30 seconds."
                        logger.warning(last_gas_err)
                    except Exception as gas_err:
                        last_gas_err = f"GAS Proxy Request Failed: {gas_err}"
                        logger.warning(last_gas_err)
            else:
                last_gas_err = "All configured Google Apps Script Web App accounts have exhausted their daily quota."
                logger.warning(last_gas_err)

        # Route 2: Direct SMTP (used as primary if no GAS, or automatic fallback if GAS hit quota/failed)
        can_use_smtp = bool(config.SENDER_EMAIL and config.SENDER_PASS)
        if can_use_smtp:
            if gas_attempted:
                logger.info(f"GAS dispatch exhausted or failed ({last_gas_err}). Seamlessly failing over to Direct SMTP...")

            msg = EmailMessage()
            msg['Subject'] = subject
            msg['From'] = f"ISTE MBCET <{config.SENDER_EMAIL}>"
            msg['To'] = to_email
            msg.set_content("Please enable HTML to view this email.")
            msg.add_alternative(html_body, subtype='html')
            msg.add_attachment(pdf_data, maintype='application', subtype='pdf', filename=attachment_filename)

            if smtp_manager:
                return smtp_manager.send_message(msg)

            # Standalone single-send connection
            with SMTPConnectionManager(timeout=20, delay_between_sends=0) as manager:
                return manager.send_message(msg)

        # If we reached here, both GAS failed (or wasn't configured) and SMTP is not configured
        if last_gas_err:
            if "too many times for one day" in str(last_gas_err).lower() or "quota" in str(last_gas_err).lower():
                return False, (
                    f"Google Apps Script daily email quota exceeded: {last_gas_err}. "
                    "Solution: Configure SENDER_EMAIL & SENDER_PASS (App Password) on Render (500-2000/day limit), "
                    "or deploy GAS with a college Google Workspace account, or add backup comma-separated GAS_MAILER_URLs."
                )
            return False, f"GAS Proxy Error: {last_gas_err}"

        return False, "No email provider configured. Please configure SENDER_EMAIL & SENDER_PASS or GAS_MAILER_URL."

    except Exception as e:
        logger.error(f"Unexpected error in send_certificate_email for {to_email}: {e}")
        return False, f"Unexpected Mail Error: {type(e).__name__} - {e}"
