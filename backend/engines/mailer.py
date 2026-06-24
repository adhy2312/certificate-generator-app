import smtplib
import os
import config
import logging
import base64
import requests
from email.message import EmailMessage
from jinja2 import Environment, FileSystemLoader

logger = logging.getLogger(__name__)
env = Environment(loader=FileSystemLoader(config.TEMPLATES_DIR))

def send_certificate_email(to_email: str, name: str, pdf_path: str, event: str = "Event", tier: str = "Participant", cert_id: str = "") -> tuple[bool, str]:
    try:
        # Load and render template
        template = env.get_template('email_template.html')
        html_body = template.render(name=name, event=event, tier=tier, cert_id=cert_id)
        
        # Read PDF
        if not os.path.exists(pdf_path):
            logger.error(f"PDF missing at {pdf_path}")
            return False, "PDF generation failed or file is missing."
            
        with open(pdf_path, 'rb') as f:
            pdf_data = f.read()
        
        filename = os.path.basename(pdf_path)

        # Check if Google Apps Script Proxy is configured
        if config.GAS_MAILER_URL:
            logger.info("Using Google Apps Script Proxy for dispatch...")
            encoded_pdf = base64.b64encode(pdf_data).decode('utf-8')
            payload = {
                "to": to_email,
                "subject": f"Your Certificate - {event}",
                "html": html_body,
                "attachment_base64": encoded_pdf,
                "filename": filename
            }
            resp = requests.post(config.GAS_MAILER_URL, json=payload, timeout=20)
            if resp.status_code == 200 and resp.json().get('success'):
                logger.info(f"Email dispatched successfully to {to_email} via GAS Proxy")
                return True, "Success"
            else:
                logger.error(f"GAS Proxy Error: {resp.text}")
                return False, f"GAS Proxy Error: {resp.text}"

        # Fallback to local Gmail SMTP (Port 587 STARTTLS)
        msg = EmailMessage()
        msg['Subject'] = f"Your Certificate - {event}"
        msg['From'] = f"ISTE MBCET <{config.SENDER_EMAIL}>"
        msg['To'] = to_email
        msg.set_content("Please enable HTML to view this email.")
        msg.add_alternative(html_body, subtype='html')
        
        msg.add_attachment(pdf_data, maintype='application', subtype='pdf', filename=filename)

        with smtplib.SMTP('smtp.gmail.com', 587, timeout=15) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.login(config.SENDER_EMAIL, config.SENDER_PASS)
            smtp.send_message(msg)

        logger.info(f"Email dispatched successfully to {to_email} via local Gmail SMTP")
        return True, "Success"

    except smtplib.SMTPAuthenticationError as e:
        logger.error(f"Gmail Auth Error: {e}")
        return False, f"Gmail Authentication Error: {e}"
    except Exception as e:
        logger.error(f"SMTP error to {to_email}: {type(e).__name__} - {e}")
        return False, f"SMTP Connection Error: {type(e).__name__} - {e}"
