"""
send_email.py – E-Mail-Versand via Gmail

Secret: GMAIL_CONFIG = "absender@gmail.com:app-passwort:empfaenger@gmail.com"
"""

import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent))
import config as C

log = logging.getLogger(__name__)


def parse_gmail_config() -> tuple[str, str, list[str]]:
    raw = os.environ["GMAIL_CONFIG"]
    parts = raw.strip().split(":")
    if len(parts) < 3:
        raise ValueError("GMAIL_CONFIG muss Format 'absender@gmail.com:app-passwort:empfaenger@gmail.com' haben")
    sender   = parts[0]
    password = parts[1]
    to       = [t.strip() for t in ":".join(parts[2:]).split(",")]
    return sender, password, to


def load_newsletter() -> tuple[str, str]:
    htmls = sorted(Path(C.OUTPUT_DIR).glob("newsletter_*.html"), reverse=True)
    if not htmls:
        raise FileNotFoundError(f"Kein newsletter_*.html in {C.OUTPUT_DIR}")
    html_path = htmls[0]
    return html_path.read_text(encoding="utf-8"), html_path.stem.replace("newsletter_", "")


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s %(message)s")

    sender, password, to = parse_gmail_config()
    html, week = load_newsletter()
    subject = f"⚡ Energiepreise Deutschland – {week}"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = sender
    msg["To"]      = ", ".join(to)
    msg.attach(MIMEText(html, "html", "utf-8"))

    with smtplib.SMTP("smtp.gmail.com", 587) as s:
        s.ehlo()
        s.starttls()
        s.login(sender, password)
        s.sendmail(sender, to, msg.as_string())

    log.info(f"✓ E-Mail gesendet an {to}")


if __name__ == "__main__":
    main()
