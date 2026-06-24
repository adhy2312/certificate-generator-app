import smtplib
import sys

def test_smtp(email, app_password):
    print(f"Testing SMTP connection for {email}...")
    try:
        print("1. Connecting to smtp.gmail.com on Port 587...")
        smtp = smtplib.SMTP('smtp.gmail.com', 587, timeout=10)
        smtp.set_debuglevel(1)  # Print all server responses
        
        print("2. Starting TLS encryption...")
        smtp.ehlo()
        smtp.starttls()
        
        print("3. Attempting login...")
        smtp.login(email, app_password)
        
        print("SUCCESS! Your university email is completely unlocked for SMTP!")
        smtp.quit()
        
    except smtplib.SMTPAuthenticationError as e:
        print("\n[ERROR] Authentication Failed!")
        print(f"Google says: {e}")
        print("\nCommon reasons:")
        print("1. The app password has a typo or space in it.")
        print("2. Your university admin has completely disabled SMTP access.")
        print("3. You recently changed your password, which invalidated the app password.")
        
    except Exception as e:
        print(f"\n[ERROR] Network or Connection Error: {e}")

if __name__ == "__main__":
    print("=== Google Workspace SMTP Diagnostic ===")
    user_email = input("Enter your University Email: ").strip()
    user_pass = input("Enter your 16-character App Password (no spaces): ").strip().replace(" ", "")
    print("\n")
    test_smtp(user_email, user_pass)
