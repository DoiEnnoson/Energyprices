"""
send_email.py – Newsletter per Gmail mit eingebetteten Charts (CID)

Secret GMAIL_CONFIG = "absender@gmail.com:app-passwort:empfaenger@gmail.com"
Charts werden als MIME-Inline-Images angehängt → funktioniert in Gmail ohne Bildblockierung
"""

import logging, os, smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent))
import config as C

log = logging.getLogger(__name__)
ROOT = Path(__file__).parent.parent

CHARTS = [
    ("chart_index",   "chart_index.png"),
    ("chart_vehicle", "chart_vehicle.png"),
    ("chart_heating", "chart_heating.png"),
]


def parse_config():
    raw = os.environ["GMAIL_CONFIG"].strip().split(":")
    if len(raw) < 3:
        raise ValueError("GMAIL_CONFIG: 'absender@gmail.com:app-passwort:empfaenger@gmail.com'")
    sender   = raw[0]
    password = raw[1]
    to       = [t.strip() for t in ":".join(raw[2:]).split(",")]
    return sender, password, to


def load_newsletter() -> tuple[str, str]:
    htmls = sorted((ROOT / C.OUTPUT_DIR).glob("newsletter_*.html"), reverse=True)
    if not htmls:
        raise FileNotFoundError(f"Kein newsletter_*.html in {C.OUTPUT_DIR}")
    path = htmls[0]
    return path.read_text(encoding="utf-8"), path.stem.replace("newsletter_", "")


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s %(message)s")

    sender, password, to = parse_config()
    html, week = load_newsletter()
    subject = f"Wöchentliche Energiepreise Deutschland – {week}"

    # MIMEMultipart related: HTML + eingebettete Bilder
    msg = MIMEMultipart("related")
    msg["Subject"] = subject
    msg["From"]    = sender
    msg["To"]      = ", ".join(to)

    msg.attach(MIMEText(html, "html", "utf-8"))

    charts_dir = ROOT / "data" / "charts"
    for cid, filename in CHARTS:
        path = charts_dir / filename
        if not path.exists():
            log.warning(f"Chart nicht gefunden: {path}")
            continue
        img = MIMEImage(path.read_bytes())
        img.add_header("Content-ID", f"<{cid}>")
        img.add_header("Content-Disposition", "inline", filename=filename)
        msg.attach(img)
        log.info(f"  Angehängt: {filename}")

    with smtplib.SMTP("smtp.gmail.com", 587) as s:
        s.ehlo()
        s.starttls()
        s.login(sender, password)
        s.sendmail(sender, to, msg.as_string())

    log.info(f"✓ E-Mail gesendet an {to}")


if __name__ == "__main__":
    main()
