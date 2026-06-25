import os

# Centralized Configuration & State
GATEKEEPER_PASSWORD = os.getenv("GATEKEEPER_PASSWORD", "ISTE@2069")

# Directory Constants
TEMPLATES_DIR = "templates"
OUTPUT_DIR = "output"

# Email Dispatch Configuration (SMTP)
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 465))
SENDER_EMAIL = os.getenv("SENDER_EMAIL", "")
SENDER_PASS = os.getenv("SENDER_PASS", "")
GAS_MAILER_URL = os.getenv("GAS_MAILER_URL", "")

# Verification URL
PUBLIC_URL = os.getenv("PUBLIC_URL", "https://certificate-generator-app-dlh6.onrender.com")

# Ensure required directories exist on boot
os.makedirs(TEMPLATES_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Certificate Stamping Coordinates (Percentages)
COORD_X = 0.50
QR_X = 0.84

CERT_COORDS = {
    "DEFAULT": {
        "name_y": 0.490,
        "event_y": 0.616,
        "date_y": 0.721,
        "qr_y": 0.72,
        "prize_y": 0.561
    },
    "Certificate Of  Merit.png": {
        "name_y": 0.490,
        "event_y": 0.616,
        "date_y": 0.721,
        "qr_y": 0.72,
        "prize_y": 0.561,
        "prize_x": 0.55
    },
    "CERT TEMPLATE.png": {
        "name_y": 0.499,
        "event_y": 0.608,
        "date_y": 0.693,
        "qr_y": 0.70
    },
    "Certificate Of  Appreciation.png": {
        "name_y": 0.490,
        "event_y": 0.616,
        "date_y": 0.721,
        "qr_y": 0.72
    },
    "Certificate Of  Recognition.png": {
        "name_y": 0.490,
        "event_y": 0.616,
        "date_y": 0.721,
        "qr_y": 0.72
    },
    "Certificate Of  Volunteering.png": {
        "name_y": 0.490,
        "event_y": 0.616,
        "date_y": 0.721,
        "qr_y": 0.72
    }
}
