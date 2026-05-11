"""
run.py – Pipeline-Einstiegspunkt für GitHub Actions

Flags:
  --no-email    Mail überspringen
  --no-update   BDEW-Referenzpreise nicht neu abfragen
"""

import argparse
import logging
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

sys.path.insert(0, str(Path(__file__).parent / "src"))


def step(name: str, fn):
    log.info(f"══ {name} ══")
    fn()
    log.info(f"✓ {name}\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-email",  action="store_true")
    parser.add_argument("--no-update", action="store_true")
    args = parser.parse_args()

    if not args.no_update:
        import auto_update_reference_prices
        step("Referenzpreise", auto_update_reference_prices.main)

    import fetch_prices
    step("Energiepreise abrufen", fetch_prices.main)

    import generate_charts
    step("Charts", generate_charts.main)

    import generate_newsletter
    step("Newsletter", generate_newsletter.main)

    if not args.no_email:
        import send_email
        step("E-Mail senden", send_email.main)


if __name__ == "__main__":
    main()
