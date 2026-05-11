"""
generate_newsletter.py – Charts liegen in data/charts/ im Repo,
Email referenziert sie als GitHub Raw URLs. Kein Base64, kein Gmail-Clip.
"""

import json, logging, os
from datetime import date
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent))
import config as C

log = logging.getLogger(__name__)
ROOT = Path(__file__).parent.parent


def github_img_url(filename: str) -> str:
    """https://raw.githubusercontent.com/OWNER/REPO/main/data/charts/filename.png"""
    repo = os.environ.get("GITHUB_REPOSITORY", "")  # z.B. "DoiEnnoson/Energyprices"
    if not repo:
        log.warning("GITHUB_REPOSITORY nicht gesetzt – Bild-URLs werden leer")
        return ""
    return f"https://raw.githubusercontent.com/{repo}/main/data/charts/{filename}"


def img(filename: str, alt: str) -> str:
    url = github_img_url(filename)
    if not url:
        return f'<p style="color:#8b949e;">[{alt}]</p>'
    return (f'<img src="{url}" alt="{alt}" '
            f'style="width:100%;max-width:680px;border-radius:8px;margin:12px 0;" />')


def fmt(val, dec=2, unit="") -> str:
    if val is None: return "–"
    s = f"{val:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{s} {unit}".strip()


def build_html(data: dict) -> str:
    meta   = data.get("meta", {})
    latest = data.get("latest_day", {})
    fuel   = data.get("fuel_prices") or {}
    vc     = data.get("vehicle_comparison", {})
    heat   = data.get("heating_costs", {})
    ref    = data.get("reference", {})
    today  = meta.get("generated", date.today().isoformat())

    def row(label, val, unit, color):
        return (f'<tr><td style="padding:7px 12px;color:#e6edf3;">{label}</td>'
                f'<td style="padding:7px 12px;text-align:right;color:{color};font-weight:600;">'
                f'{fmt(val, 2, unit)}</td></tr>')

    market_rows = (
        row("Strom Day-Ahead DE-LU",     latest.get("strom_eur_mwh"),    "EUR/MWh", C.COLORS["electricity"]) +
        row("Erdgas TTF",                latest.get("ttf"),               "EUR/MWh", C.COLORS["ttf"]) +
        row("Erdgas TTF",                latest.get("ttf_ct_kwh"),        "ct/kWh",  C.COLORS["ttf"]) +
        row("Brent Rohöl",               latest.get("brent_eur_bbl"),     "EUR/bbl", C.COLORS["brent"]) +
        row("Heizöl (Futures-Proxy)",    latest.get("heizoel_eur_liter"), "EUR/L",   C.COLORS["heating_oil"])
    )
    for label, key, color in [("Super E5","e5",C.COLORS["ice"]),("E10","e10","#f59e0b"),("Diesel","diesel","#6b7280")]:
        if fuel.get(key):
            market_rows += row(f"{label} (Bundesdurchschnitt)", fuel[key], "EUR/L", color)

    vc_rows = ""
    for key, color in [("ice",C.COLORS["ice"]),("bev_home",C.COLORS["bev_home"]),
                       ("bev_public_ac",C.COLORS["bev_ac"]),("bev_public_dc",C.COLORS["bev_dc"])]:
        e = vc.get(key)
        if not e: continue
        save = e.get("savings_pct_vs_ice")
        save_str = f'<small style="color:#22c55e;"> –{save:.0f}%</small>' if save else ""
        vc_rows += (f'<tr><td style="padding:7px 12px;color:#e6edf3;">{e.get("label","")}</td>'
                    f'<td style="padding:7px 12px;text-align:right;color:{color};font-weight:600;">'
                    f'{fmt(e.get("cost_per_100km"),2,"€/100 km")} {save_str}</td>'
                    f'<td style="padding:7px 12px;text-align:right;color:{color};">'
                    f'{fmt(e.get("km_for_budget"),0,"km")} für {C.COMPARISON_BUDGET_EUR:.0f} €</td></tr>')

    heat_rows = ""
    color_map = {"gas_boiler":C.COLORS["gas"],"oil_boiler":C.COLORS["oil_heat"],
                 "heat_pump":C.COLORS["heat_pump"],"direct_electric":C.COLORS["direct_elec"]}
    for prop_key, prop_label in [("haus_150qm","Einfamilienhaus 150 m²"),("wohnung_100qm","Wohnung 100 m²")]:
        heat_rows += (f'<tr style="background:#1c2128;"><td colspan="2" style="padding:9px 12px;'
                      f'color:#e6edf3;font-weight:700;border-top:1px solid #21262d;">{prop_label}</td></tr>')
        for sk, slabel in [("gas_boiler","Gasheizung"),("oil_boiler","Ölheizung"),
                            ("heat_pump","Wärmepumpe (COP 3,5)"),("direct_electric","Direktstrom")]:
            cost = heat.get(prop_key,{}).get("systems",{}).get(sk,{}).get("weekly_cost_eur")
            c = color_map.get(sk,"#e6edf3")
            heat_rows += (f'<tr><td style="padding:6px 12px 6px 24px;color:#e6edf3;">{slabel}</td>'
                          f'<td style="padding:6px 12px;text-align:right;color:{c};font-weight:600;">'
                          f'{fmt(cost,2,"€/Woche")}</td></tr>')

    return f"""<!DOCTYPE html>
<html lang="de">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Energiepreise Deutschland – {today}</title></head>
<body style="margin:0;padding:0;background:#0d1117;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#0d1117;">
<tr><td align="center" style="padding:24px 16px;">
<table width="680" cellpadding="0" cellspacing="0"
  style="max-width:680px;background:#161b22;border-radius:12px;border:1px solid #21262d;">

  <tr><td style="background:linear-gradient(135deg,#1c2128,#0d1117);padding:28px 32px;">
    <p style="margin:0 0 4px;font-size:12px;color:#3b82f6;letter-spacing:1.5px;text-transform:uppercase;">
      Täglicher Energie-Report</p>
    <h1 style="margin:0 0 6px;font-size:24px;font-weight:700;color:#e6edf3;">Energiepreise Deutschland</h1>
    <p style="margin:0;font-size:13px;color:#8b949e;">
      Stand {today} · Index 100 = 1. Januar 2026</p>
  </td></tr>

  <tr><td style="padding:24px 32px 8px;">
    <h2 style="margin:0 0 14px;font-size:15px;font-weight:700;color:#e6edf3;
      border-bottom:1px solid #21262d;padding-bottom:8px;">📊 Aktuelle Marktpreise</h2>
    <table width="100%" cellpadding="0" cellspacing="0"
      style="border-collapse:collapse;border:1px solid #21262d;border-radius:8px;overflow:hidden;">
      <thead><tr style="background:#1c2128;">
        <th style="padding:9px 12px;text-align:left;color:#8b949e;font-size:11px;text-transform:uppercase;">Energieträger</th>
        <th style="padding:9px 12px;text-align:right;color:#8b949e;font-size:11px;text-transform:uppercase;">Aktuell</th>
      </tr></thead>
      <tbody>{market_rows}</tbody>
    </table>
  </td></tr>

  <tr><td style="padding:4px 32px 16px;">
    {img("chart_index.png", "Energiepreisindex ab 1.1.2026")}
  </td></tr>

  <tr><td style="padding:8px 32px;">
    <h2 style="margin:0 0 8px;font-size:15px;font-weight:700;color:#e6edf3;
      border-bottom:1px solid #21262d;padding-bottom:8px;">🚗⚡ Opel Astra – Benziner vs. Elektro</h2>
    <table width="100%" cellpadding="0" cellspacing="0"
      style="border-collapse:collapse;border:1px solid #21262d;border-radius:8px;overflow:hidden;">
      <thead><tr style="background:#1c2128;">
        <th style="padding:9px 12px;text-align:left;color:#8b949e;font-size:11px;text-transform:uppercase;">Antrieb</th>
        <th style="padding:9px 12px;text-align:right;color:#8b949e;font-size:11px;text-transform:uppercase;">Kosten/100 km</th>
        <th style="padding:9px 12px;text-align:right;color:#8b949e;font-size:11px;text-transform:uppercase;">Reichweite</th>
      </tr></thead>
      <tbody>{vc_rows}</tbody>
    </table>
    {img("chart_vehicle.png", "Fahrzeugvergleich")}
  </td></tr>

  <tr><td style="padding:8px 32px 16px;">
    <h2 style="margin:0 0 8px;font-size:15px;font-weight:700;color:#e6edf3;
      border-bottom:1px solid #21262d;padding-bottom:8px;">🏠 Heizkosten im Vergleich</h2>
    <table width="100%" cellpadding="0" cellspacing="0"
      style="border-collapse:collapse;border:1px solid #21262d;border-radius:8px;overflow:hidden;">
      <thead><tr style="background:#1c2128;">
        <th style="padding:9px 12px;text-align:left;color:#8b949e;font-size:11px;text-transform:uppercase;">Heizsystem</th>
        <th style="padding:9px 12px;text-align:right;color:#8b949e;font-size:11px;text-transform:uppercase;">€/Woche</th>
      </tr></thead>
      <tbody>{heat_rows}</tbody>
    </table>
    {img("chart_heating.png", "Heizkosten")}
  </td></tr>

  <tr><td style="padding:12px 32px 24px;border-top:1px solid #21262d;">
    <p style="margin:0;font-size:11px;color:#8b949e;line-height:1.7;">
      <strong style="color:#e6edf3;">Quellen:</strong>
      Energy-Charts/ENTSO-E · Yahoo Finance (BZ=F, TTF=F, HO=F) · Tankerkönig/MTS-K ·
      BDEW ({ref.get("bdew_reference_period","")}) · GlobalPetrolPrices.com<br>
      Automatisch generiert am {today}
    </p>
  </td></tr>

</table></td></tr></table>
</body></html>"""


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s %(message)s")

    latest_path = ROOT / C.DATA_DIR / "latest.json"
    if not latest_path.exists():
        log.error("latest.json fehlt"); return

    with open(latest_path, encoding="utf-8") as f:
        data = json.load(f)

    today = data.get("meta", {}).get("generated", date.today().isoformat())
    html  = build_html(data)

    out = ROOT / C.OUTPUT_DIR / f"newsletter_{today}.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    log.info(f"Newsletter → {out}")
    log.info("✓ Newsletter erzeugt")


if __name__ == "__main__":
    main()
