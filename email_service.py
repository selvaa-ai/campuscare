import os
import smtplib
from email.message import EmailMessage

from dotenv import load_dotenv

load_dotenv()


def send_email(to: str, subject: str, body: str) -> None:
    subject = " ".join(subject.split())  # newline remove (header injection thadukka)

    if os.getenv("EMAIL_ENABLED", "false").lower() != "true":
        print(f"[EMAIL DISABLED] To: {to} | Subject: {subject}")
        return

    try:
        msg = EmailMessage()
        msg["From"] = os.getenv("EMAIL_FROM")
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body)

        with smtplib.SMTP(os.getenv("SMTP_HOST"), int(os.getenv("SMTP_PORT", "587")), timeout=15) as server:
            server.starttls()
            server.login(os.getenv("SMTP_USER"), os.getenv("SMTP_PASSWORD"))
            server.send_message(msg)
        print(f"[EMAIL SENT] To: {to} | Subject: {subject}")
    except Exception as e:
        print(f"[EMAIL FAILED] To: {to} | Error: {e}")