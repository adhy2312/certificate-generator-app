import smtplib
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import config
import logging
from jinja2 import Environment, FileSystemLoader

logger = logging.getLogger(__name__)

# Setup Jinja2 environment
env = Environment(loader=FileSystemLoader(config.TEMPLATES_DIR))

def send_certificate_email(to_email: str, name: str, pdf_path: str, event: str = "Event", tier: str = "Participant", cert_id: str = "") -> bool:
    try:
        msg = MIMEMultipart('alternative')
        msg['From'] = f"ISTE No-Reply <{config.SENDER_EMAIL}>"
        msg['To'] = to_email
        msg['Subject'] = f"Your Certificate - {event}"
        
        # Any replies go to the organization email, not your personal backup email
        msg.add_header('reply-to', 'istestudentchapter@mbcet.ac.in')

        # Load and render template
        template = env.get_template('email_template.html')
        html_body = template.render(name=name, event=event, tier=tier, cert_id=cert_id)
        
        # Attach HTML body
        msg.attach(MIMEText(html_body, 'html'))

        # Attach PDF
        if os.path.exists(pdf_path):
            with open(pdf_path, 'rb') as attachment:
                part = MIMEBase('application', 'octet-stream')
                part.set_payload(attachment.read())
            encoders.encode_base64(part)
            filename = os.path.basename(pdf_path)
            part.add_header('Content-Disposition', f'attachment; filename="{filename}"')
            msg.attach(part)
        else:
            logger.error(f"PDF missing at {pdf_path}")
            return False

        with smtplib.SMTP_SSL(config.SMTP_SERVER, config.SMTP_PORT) as server:
            server.login(config.SENDER_EMAIL, config.SENDER_PASS)
            server.send_message(msg)

        logger.info(f"Email sent successfully to {to_email}")
        return True

    except Exception as e:
        logger.error(f"SMTP error to {to_email}: {e}")
        return False
