import smtplib
import os
import config
import logging
from email.message import EmailMessage
from jinja2 import Environment, FileSystemLoader

logger = logging.getLogger(__name__)
env = Environment(loader=FileSystemLoader(config.TEMPLATES_DIR))

def send_certificate_email(to_email: str, name: str, pdf_path: str, event: str = "Event", tier: str = "Participant", cert_id: str = "") -> bool:
    try:
        # Load and render template
        template = env.get_template('email_template.html')
        html_body = template.render(name=name, event=event, tier=tier, cert_id=cert_id)
        
        # Read PDF
        if not os.path.exists(pdf_path):
            logger.error(f"PDF missing at {pdf_path}")
            return False
            
        with open(pdf_path, 'rb') as f:
            pdf_data = f.read()
        
        filename = os.path.basename(pdf_path)

        # Construct Email
        msg = EmailMessage()
        msg['Subject'] = f"Your Certificate - {event}"
        msg['From'] = f"ISTE MBCET <{config.SENDER_EMAIL}>"
        msg['To'] = to_email
        msg.set_content("Please enable HTML to view this email.")
        msg.add_alternative(html_body, subtype='html')
        
        # Attach PDF
        msg.add_attachment(pdf_data, maintype='application', subtype='pdf', filename=filename)

        # Send via Gmail SMTP
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(config.SENDER_EMAIL, config.SENDER_PASS)
            smtp.send_message(msg)

        logger.info(f"Email dispatched successfully to {to_email} via Gmail")
        return True

    except Exception as e:
        logger.error(f"SMTP error to {to_email}: {e}")
        return False
