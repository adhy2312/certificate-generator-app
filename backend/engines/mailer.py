import resend
import os
import base64
import config
import logging
from jinja2 import Environment, FileSystemLoader

logger = logging.getLogger(__name__)
env = Environment(loader=FileSystemLoader(config.TEMPLATES_DIR))

def send_certificate_email(to_email: str, name: str, pdf_path: str, event: str = "Event", tier: str = "Participant", cert_id: str = "") -> tuple[bool, str]:
    try:
        # Load and render template
        template = env.get_template('email_template.html')
        html_body = template.render(name=name, event=event, tier=tier, cert_id=cert_id)
        
        # Read and encode PDF
        if not os.path.exists(pdf_path):
            logger.error(f"PDF missing at {pdf_path}")
            return False, "PDF generation failed or file is missing."
            
        with open(pdf_path, 'rb') as f:
            pdf_data = f.read()
        
        encoded_pdf = base64.b64encode(pdf_data).decode('utf-8')
        filename = os.path.basename(pdf_path)

        resend.api_key = config.SENDER_PASS # Use SENDER_PASS variable for the API key

        # Send via Resend
        params = {
            "from": f"ISTE MBCET <{config.SENDER_EMAIL}>",
            "to": [to_email],
            "reply_to": "istestudentchapter@mbcet.ac.in",
            "subject": f"Your Certificate - {event}",
            "html": html_body,
            "attachments": [
                {
                    "filename": filename,
                    "content": encoded_pdf
                }
            ]
        }

        email = resend.Emails.send(params)
        logger.info(f"Resend dispatched successfully to {to_email}: {email}")
        return True, "Success"

    except Exception as e:
        logger.error(f"Resend API error to {to_email}: {e}")
        return False, f"Resend API Error: {str(e)}"
