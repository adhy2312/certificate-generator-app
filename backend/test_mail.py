from engines.mailer import send_certificate_email
from engines.certificate import generate_pdf_from_svg
import logging

logging.basicConfig(level=logging.INFO)

print("Starting generation...")
pdf_path = generate_pdf_from_svg("Test Name", "Test Event", "Participant", "Oct 15, 2026", "TEST-CERT-12345")
print(f"PDF Path: {pdf_path}")
if pdf_path:
    success, err_msg = send_certificate_email("test@test.com", "Test Name", pdf_path, "Test Event", "Participant", "TEST-CERT-12345", "Certificate of Participation")
    print(f"Email Success: {success}, Error: {err_msg}")
else:
    print("PDF Generation Failed")
