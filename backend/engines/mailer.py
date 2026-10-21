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
                if "quota" in err_msg.lower() or "limit" in err_msg.lower() or err_code == 452:
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
    Sends certificate PDF to recipient via Google Apps Script Proxy or direct SMTP.
    If smtp_manager is provided, reuses the active SMTP connection for speed & reliability.
    """
    try:
        if cert_type == "CERT_Template":
            cert_type = "Certificate of Participation"

        clean_name = name.strip().title()
        safe_name_str = re.sub(r'[^a-zA-Z0-9_-]', '_', clean_name).replace(" ", "_")
        attachment_filename = f"{safe_name_str}_Certificate.pdf"
        
        subject = f"Your {cert_type} - {event}"

        # Load and render template
        template = env.get_template('email_template.html')
        html_body = template.render(name=clean_name, event=event, tier=tier, cert_id=cert_id, cert_type=cert_type)
        
        # Read PDF
        if not os.path.exists(pdf_path):
            logger.error(f"PDF missing at {pdf_path}")
            return False, "PDF generation failed or file is missing."
            
        with open(pdf_path, 'rb') as f:
            pdf_data = f.read()

        # Route 1: Google Apps Script Proxy (if configured)
        if config.GAS_MAILER_URL:
            logger.info("Using Google Apps Script Proxy for dispatch...")
            encoded_pdf = base64.b64encode(pdf_data).decode('utf-8')
            payload = {
                "to": to_email,
                "subject": subject,
                "html": html_body,
                "attachment_base64": encoded_pdf,
                "filename": attachment_filename
            }
            try:
                resp = requests.post(config.GAS_MAILER_URL, json=payload, timeout=30)
                try:
                    resp_json = resp.json()
                    if resp.status_code == 200 and resp_json.get('success'):
                        logger.info(f"Email dispatched successfully to {to_email} via GAS Proxy")
                        return True, "Success"
                    else:
                        err_detail = resp_json.get('error', resp.text)
                        logger.error(f"GAS Proxy Error: {err_detail}")
                        return False, f"GAS Proxy Error: {err_detail}"
                except ValueError:
                    if "Access Denied" in resp.text or "accounts.google.com" in resp.text:
                        err_msg = "Google Apps Script Error: Access Denied. Ensure Web App is deployed with 'Who has access: Anyone'."
                    else:
                        snippet = resp.text.strip()[:160].replace('\n', ' ')
                        err_msg = f"Google Apps Script Error (non-JSON): {snippet}"
                    logger.error(err_msg)
                    return False, err_msg
            except requests.Timeout:
                return False, "Google Apps Script timed out after 30 seconds."
            except Exception as gas_err:
                return False, f"GAS Proxy Request Failed: {gas_err}"

        # Route 2: Direct SMTP
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

    except Exception as e:
        logger.error(f"Unexpected error in send_certificate_email for {to_email}: {e}")
        return False, f"Unexpected Mail Error: {type(e).__name__} - {e}"
