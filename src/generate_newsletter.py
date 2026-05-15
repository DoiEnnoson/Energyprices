"""
generate_newsletter.py – HTML-E-Mail im Mockup-Stil
Charts kommen per GitHub Raw URL (kein Base64, kein Gmail-Clip)
"""

import json, logging, os
from datetime import date
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent))
import config as C

log = logging.getLogger(__name__)
ROOT = Path(__file__).parent.parent


def img(filename: str, alt: str) -> str:
    """CID-Referenz – Bild wird als MIME-Attachment eingebettet (kein Gmail-Block)"""
    cid = filename.replace(".png", "")
    return (f'<img src="cid:{cid}" alt="{alt}" width="620" '
            f'style="width:100%;max-width:620px;display:block;margin:12px 0;" />')


def fmt(val, dec=2, unit="") -> str:
    if val is None: return "–"
    s = f"{val:,.{dec}f}".replace(",","X").replace(".",",").replace("X",".")
    return f"{s} {unit}".strip()


def build_html(data: dict) -> str:
    meta   = data.get("meta", {})
    cur    = data.get("current_week", {})
    fuel   = data.get("fuel_prices") or {}
    vc     = data.get("vehicle_comparison", {})
    heat   = data.get("heating_costs", {})
    ref    = data.get("reference", {})
    week   = meta.get("current_week", "")
    today  = meta.get("generated", date.today().isoformat())

    CSS = """
      body{margin:0;padding:0;background:#f4f3ef;font-family:Georgia,serif;color:#1a1a1a;}
      .page{max-width:680px;margin:0 auto;background:#fff;border:1px solid #d8d5cd;}
      .header{padding:2rem 2.5rem 1.5rem;border-bottom:2px solid #1a1a1a;}
      .meta{font-family:'Courier New',monospace;font-size:11px;letter-spacing:.12em;
            text-transform:uppercase;color:#888;margin-bottom:.5rem;}
      h1{font-size:26px;font-weight:normal;line-height:1.2;letter-spacing:-.02em;margin:0;}
      .sub{font-size:11px;color:#888;margin-top:.4rem;font-family:'Courier New',monospace;}
      .section{padding:1.75rem 2.5rem;border-bottom:1px solid #d8d5cd;}
      .slabel{font-family:'Courier New',monospace;font-size:10px;letter-spacing:.15em;
              text-transform:uppercase;color:#aaa;margin-bottom:1rem;}
      table{width:100%;border-collapse:collapse;font-size:13px;}
      td{padding:.45rem 0;border-bottom:1px solid #ebe9e3;color:#333;vertical-align:top;}
      td:last-child{text-align:right;font-family:'Courier New',monospace;color:#1a1a1a;}
      .sm{font-size:11px;color:#aaa;display:block;}
      .footer{padding:1rem 2.5rem;font-size:10px;color:#bbb;line-height:1.7;
              font-family:'Courier New',monospace;}
    """

    # Preistabelle
    def row(label, sub, val, unit):
        sub_html = f'<span class="sm">{sub}</span>' if sub else ""
        return (f"<tr><td>{label}{sub_html}</td>"
                f"<td>{fmt(val, 2, unit)}</td></tr>")

    # BDEW-Periode als Monat/Jahr (z.B. "Mai '26")
    from datetime import datetime as _dt
    try:
        _monate = ["Jan","Feb","Mär","Apr","Mai","Jun","Jul","Aug","Sep","Okt","Nov","Dez"]
        _d = _dt.fromisoformat(today)
        bdew_period = f"{_monate[_d.month-1]} '{str(_d.year)[2:]}"
    except Exception:
        bdew_period = ref.get("bdew_reference_period", "")

    price_rows = (
        row("Strom (Börse)",         "Wochendurchschnitt", cur.get("strom_eur_mwh"),    "EUR/MWh") +
        row("Erdgas (Börse)",        "Wochendurchschnitt", cur.get("ttf_eur_mwh"),      "EUR/MWh") +
        row("Erdgas (Börse)",        "",                   cur.get("ttf_ct_kwh"),        "ct/kWh")  +
        row("Brent Rohöl",           "Wochendurchschnitt", cur.get("brent_eur_bbl"),    "EUR/bbl") +
        row("Kohle (Börse)",         "",                   cur.get("coal_eur_t"),        "EUR/t")   +
        row("Heizöl (Retail-Proxy)", "",                   cur.get("heizoel_eur_liter"), "EUR/l")
    )
    for label, key in [("Super E5","e5"),("E10","e10"),("Diesel","diesel")]:
        if fuel.get(key):
            price_rows += row(label, "Bundesdurchschnitt", fuel[key], "EUR/l")
    price_rows += (
        row(f"Haushaltsstrom ({bdew_period})", "", ref.get("bdew_electricity_ct_kwh"), "ct/kWh") +
        row(f"Haushaltsgas ({bdew_period})",   "", ref.get("bdew_gas_ct_kwh"),         "ct/kWh")
    )

    return f"""<!DOCTYPE html>
<html lang="de">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Wöchentliche Energiepreise Deutschland – {week}</title>
<style>{CSS}</style></head>
<body>
<div class="page">

  <div class="header">
    <div class="meta">Wöchentliche Energiepreise Deutschland &nbsp;·&nbsp; {week}</div>
    <h1>Wöchentliche Energiepreise<br>Deutschland</h1>
    <div class="sub">Index 100 = 1. Januar 2026 &nbsp;·&nbsp; Wochendurchschnitte</div>
  </div>

  <div class="section">
    <div class="slabel">Preisentwicklung seit 1.1.2026</div>
    {img("chart_index.png", "Energiepreisindex")}
  </div>

  <div class="section">
    <div class="slabel">Marktpreise {week}</div>
    <table>{price_rows}</table>
  </div>

  <div class="section">
    <div class="slabel">Mobilität &nbsp;·&nbsp; Opel Astra</div>
    {img("chart_vehicle.png", "Fahrzeugvergleich")}
  </div>

  <div class="section">
    <div class="slabel">Heizkosten &nbsp;·&nbsp; Wöchentlich</div>
    {img("chart_heating.png", "Heizkosten")}
  </div>

  <div class="footer">
    Energy-Charts/ENTSO-E (Strom Day-Ahead) · Yahoo Finance BZ=F (Brent) · Yahoo Finance TTF=F (Erdgas TTF) ·
    OilPrice.com COAL_USD (Kohle, Spotpreis) · Yahoo Finance HO=F (Heizöl, NY Harbor ULSD als Retail-Proxy) ·
    Tankerkönig/MTS-K (Kraftstoffpreise, Bundesdurchschnitt aus 7 Städten) ·
    GlobalPetrolPrices.com (Haushaltsstrom & Haushaltsgas, automatisch aktualisiert)<br>
    Fahrzeugvergleich: Opel Astra 1.2 Turbo 130 PS (Benziner) vs. Opel Astra Electric 156 PS ·
    Realer Verbrauch: 6,5 L/100 km bzw. 18 kWh/100 km (Spritmonitor.de-Durchschnitt, kein WLTP-Laborwert) ·
    Ladepreise: Tankerkönig (E5), Verivox-Marktdurchschnitt DE (AC/DC), BDEW-Haushaltsstrompreis (Wallbox) ·
    Automatisch generiert am {today}
  </div>

</div>
</body></html>"""


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s %(message)s")

    latest_path = ROOT / C.DATA_DIR / "latest.json"
    if not latest_path.exists():
        log.error("latest.json fehlt"); return

    with open(latest_path, encoding="utf-8") as f:
        data = json.load(f)

    week = data.get("meta", {}).get("current_week", date.today().isoformat())
    html = build_html(data)

    out = ROOT / C.OUTPUT_DIR / f"newsletter_{week}.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    log.info(f"Newsletter → {out}")
    log.info("✓ Newsletter erzeugt")


if __name__ == "__main__":
    main()
