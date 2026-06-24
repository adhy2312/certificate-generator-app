import os

# Centralized Configuration & State
GATEKEEPER_PASSWORD = "ISTE@2069"

# Directory Constants
TEMPLATES_DIR = "templates"
OUTPUT_DIR = "output"

# Email Dispatch Configuration (SMTP)
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 465))
SENDER_EMAIL = os.getenv("SENDER_EMAIL", "adhithyamohansbackup@gmail.com")
SENDER_PASS = os.getenv("SENDER_PASS", "mpnyzpsoxfsejqoe")
GAS_MAILER_URL = os.getenv("GAS_MAILER_URL", "")

# Verification URL
PUBLIC_URL = os.getenv("PUBLIC_URL", "https://certificate-generator-app-dlh6.onrender.com")

# Ensure required directories exist on boot
os.makedirs(TEMPLATES_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Certificate Stamping Coordinates (Percentages)
COORD_NAME_X = 0.50
COORD_NAME_Y = 0.49

COORD_EVENT_X = 0.50
COORD_EVENT_Y = 0.605

COORD_DATE_X = 0.50
COORD_DATE_Y = 0.70

COORD_QR_X = 0.84
COORD_QR_Y = 0.70
