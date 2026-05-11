"""
generate_newsletter.py – HTML-E-Mail und Web-JSON erzeugen

Ausgabe:
  output/newsletter_YYYY-KWxx.html   (E-Mail, inline CSS, eingebettete Charts als Base64)
  output/web_data.json               (maschinenlesbar, für Webseite)
"""

import base64
import json
import logging
from datetime import date
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent))
import config as C

log = logging.getLogger(__name__)


def img_b64(path: str) -> str:
    """PNG → data-URI für Inline-Einbettung in HTML-E-Mail"""
    p = Path(path)
    if not p.exists():
        return ""
    return "data:image/png;base64," + base64.b64encode(p.read_bytes()).decode()


def fmt_eur(val, decimals=2) -> str:
    if val is None:
        return "–"
    return f"{val:,.{decimals}f} €".replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_num(val, decimals=2, unit="") -> str:
    if val is None:
        return "–"
    s = f"{val:,.{decimals}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{s} {unit}".strip()


def trend_arrow(current, previous) -> str:
    if current is None or previous is None:
        return ""
    diff = current - previous
    if diff > 0.5:
        return " ▲"
    if diff < -0.5:
        return " ▼"
    return " ▶"


def build_html(data: dict, hist_df=None) -> str:
    meta = data["meta"]
    elec = data.get("electricity_dayahead", {})
    comm = data.get("commodities", {})
    fuel = data.get("fuel_prices") or {}
    vc   = data.get("vehicle_comparison", {})
    heat = data.get("heating_costs", {})
    ref  = data.get("reference", {})

    week  = meta["week"]
    wstart = meta["week_start"]
    wend   = meta["week_end"]

    # Charts einbetten
    img_prices  = img_b64(f"{C.OUTPUT_DIR}/chart_prices.png")
    img_vehicle = img_b64(f"{C.OUTPUT_DIR}/chart_vehicle.png")
    img_heating = img_b64(f"{C.OUTPUT_DIR}/chart_heating.png")

    img_tag = lambda src, alt: (
        f'<img src="{src}" alt="{alt}" '
        f'style="width:100%;max-width:680px;border-radius:8px;margin:12px 0;" />'
        if src else f'<p style="color:#8b949e;">[{alt} nicht verfügbar]</p>'
    )

    # ── Rohstofftabelle ────────────────────────────────────────────
    def comm_row(label, key, val_key, unit, decimals=2):
        val = comm.get(key, {}).get(val_key)
        return f"""
        <tr>
          <td style="padding:7px 12px;color:#e6edf3;">{label}</td>
          <td style="padding:7px 12px;text-align:right;color:#e6edf3;font-weight:600;">
            {fmt_num(val, decimals, unit)}
          </td>
        </tr>"""

    commodity_rows = (
        comm_row("Strom Day-Ahead DE-LU Ø",     "", "",     "EUR/MWh")   # sonderfall
        .replace("comm.get(\"\", {}).get(\"\")", "elec.get(\"week_avg\")")
    )
    # Neuaufbau als sauberer String
    rows_html = f"""
    <tr>
      <td style="padding:7px 12px;color:#e6edf3;">Strom Day-Ahead DE-LU Ø</td>
      <td style="padding:7px 12px;text-align:right;color:#3b82f6;font-weight:600;">
        {fmt_num(elec.get('week_avg'), 2, 'EUR/MWh')}
      </td>
    </tr>
    <tr>
      <td style="padding:7px 12px;color:#e6edf3;">Erdgas (TTF)</td>
      <td style="padding:7px 12px;text-align:right;color:#22c55e;font-weight:600;">
        {fmt_num(comm.get('ttf',{}).get('avg'), 2, 'EUR/MWh')}
        &nbsp;<small style="color:#8b949e;">({fmt_num(comm.get('ttf',{}).get('avg_ct_kwh'), 2, 'ct/kWh')})</small>
      </td>
    </tr>
    <tr>
      <td style="padding:7px 12px;color:#e6edf3;">Brent Rohöl</td>
      <td style="padding:7px 12px;text-align:right;color:#f97316;font-weight:600;">
        {fmt_num(comm.get('brent',{}).get('avg_eur_bbl'), 2, 'EUR/bbl')}
      </td>
    </tr>
    <tr>
      <td style="padding:7px 12px;color:#e6edf3;">Kohle API2 CIF ARA (EU-Benchmark)</td>
      <td style="padding:7px 12px;text-align:right;color:#8b5cf6;font-weight:600;">
        {fmt_num(comm.get('coal',{}).get('avg_eur_t'), 2, 'EUR/t')}
        &nbsp;<small style="color:#8b949e;">({fmt_num(comm.get('coal',{}).get('avg_eur_mwh'), 2, 'EUR/MWh')})</small>
      </td>
    </tr>
    <tr>
      <td style="padding:7px 12px;color:#e6edf3;">Heizöl (Futures-Proxy, retail ~+0,12 €/L)</td>
      <td style="padding:7px 12px;text-align:right;color:#ec4899;font-weight:600;">
        {fmt_num(comm.get('heating_oil',{}).get('retail_est_eur_liter'), 3, 'EUR/L')}
      </td>
    </tr>
    """
    if fuel:
        for flabel, fkey, fcolor in [
            ("Super E5",  "e5",     "#f97316"),
            ("E10",       "e10",    "#f59e0b"),
            ("Diesel",    "diesel", "#6b7280"),
        ]:
            fval = fuel.get(fkey)
            rows_html += f"""
    <tr>
      <td style="padding:7px 12px;color:#e6edf3;">{flabel} (Bundesdurchschnitt)</td>
      <td style="padding:7px 12px;text-align:right;color:{fcolor};font-weight:600;">
        {fmt_num(fval, 3, 'EUR/L')}
      </td>
    </tr>"""

    # ── Fahrzeugvergleich ──────────────────────────────────────────
    vc_rows = ""
    vc_order = [
        ("ice",           "#f97316"),
        ("bev_home",      "#3b82f6"),
        ("bev_public_ac", "#06b6d4"),
        ("bev_public_dc", "#8b5cf6"),
    ]
    for key, color in vc_order:
        entry = vc.get(key)
        if not entry:
            continue
        label    = entry.get("label", key)
        cost100  = entry.get("cost_per_100km")
        km50     = entry.get("km_for_budget")
        save_pct = entry.get("savings_pct_vs_ice")
        save_str = f'<small style="color:#22c55e;"> –{save_pct}% vs. Benziner</small>' if save_pct else ""
        vc_rows += f"""
    <tr>
      <td style="padding:7px 12px;color:#e6edf3;">{label}</td>
      <td style="padding:7px 12px;text-align:right;color:{color};font-weight:600;">
        {fmt_num(cost100, 2, '€/100 km')}
      </td>
      <td style="padding:7px 12px;text-align:right;color:{color};">
        {fmt_num(km50, 0, 'km')} für {C.COMPARISON_BUDGET_EUR:.0f} € {save_str}
      </td>
    </tr>"""

    # ── Heizkosten ─────────────────────────────────────────────────
    heat_rows = ""
    for prop_key, prop_label in [
        ("haus_150qm",     "Einfamilienhaus 150 m²"),
        ("wohnung_100qm",  "Wohnung 100 m²"),
    ]:
        heat_rows += f"""
    <tr style="background:#1c2128;">
      <td colspan="3" style="padding:10px 12px;color:#e6edf3;font-weight:700;
                             border-top:1px solid #21262d;">{prop_label}</td>
    </tr>"""
        systems = heat.get(prop_key, {}).get("systems", {})
        for sys_key in ["gas_boiler", "oil_boiler", "heat_pump", "direct_electric"]:
            sys = systems.get(sys_key)
            if not sys:
                continue
            cost = sys.get("weekly_cost_eur")
            basis = sys.get("price_basis", "")
            color_map = {
                "gas_boiler":      "#22c55e",
                "oil_boiler":      "#f97316",
                "heat_pump":       "#3b82f6",
                "direct_electric": "#ec4899",
            }
            color = color_map.get(sys_key, "#e6edf3")
            heat_rows += f"""
    <tr>
      <td style="padding:7px 12px;color:#e6edf3;padding-left:24px;">{sys.get('label', sys_key)}</td>
      <td style="padding:7px 12px;text-align:right;color:{color};font-weight:600;">
        {fmt_num(cost, 2, '€/Woche')}
      </td>
      <td style="padding:7px 12px;text-align:right;color:#8b949e;font-size:11px;">{basis}</td>
    </tr>"""

    # ── HTML zusammenbauen ─────────────────────────────────────────
    html = f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Energiepreise Deutschland – {week}</title>
</head>
<body style="margin:0;padding:0;background:#0d1117;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#0d1117;">
<tr><td align="center" style="padding:24px 16px;">

<table width="680" cellpadding="0" cellspacing="0"
       style="max-width:680px;background:#161b22;border-radius:12px;
              border:1px solid #21262d;overflow:hidden;">

  <!-- Header -->
  <tr><td style="background:linear-gradient(135deg,#1c2128,#0d1117);padding:28px 32px;">
    <p style="margin:0 0 4px;font-size:12px;color:#3b82f6;letter-spacing:1.5px;
               text-transform:uppercase;">Wöchentlicher Energie-Report</p>
    <h1 style="margin:0 0 6px;font-size:26px;font-weight:700;color:#e6edf3;">
      Energiepreise Deutschland
    </h1>
    <p style="margin:0;font-size:13px;color:#8b949e;">
      {week} &nbsp;·&nbsp; {wstart} bis {wend}
    </p>
  </td></tr>

  <!-- Marktübersicht -->
  <tr><td style="padding:28px 32px 8px;">
    <h2 style="margin:0 0 16px;font-size:16px;font-weight:700;color:#e6edf3;
               border-bottom:1px solid #21262d;padding-bottom:8px;">
      📊 Marktübersicht
    </h2>
    <table width="100%" cellpadding="0" cellspacing="0"
           style="border-collapse:collapse;border-radius:8px;overflow:hidden;
                  border:1px solid #21262d;">
      <thead>
        <tr style="background:#1c2128;">
          <th style="padding:10px 12px;text-align:left;color:#8b949e;font-size:11px;
                     text-transform:uppercase;letter-spacing:0.8px;">Energieträger</th>
          <th style="padding:10px 12px;text-align:right;color:#8b949e;font-size:11px;
                     text-transform:uppercase;letter-spacing:0.8px;">Wochendurchschnitt</th>
        </tr>
      </thead>
      <tbody>{rows_html}</tbody>
    </table>
  </td></tr>

  <!-- Chart Preise -->
  <tr><td style="padding:8px 32px 16px;">
    {img_tag(img_prices, "Energiepreisverlauf")}
  </td></tr>

  <!-- Fahrzeugvergleich -->
  <tr><td style="padding:8px 32px;">
    <h2 style="margin:0 0 8px;font-size:16px;font-weight:700;color:#e6edf3;
               border-bottom:1px solid #21262d;padding-bottom:8px;">
      🚗⚡ Opel Astra – Benziner vs. Elektro
    </h2>
    <p style="margin:0 0 12px;font-size:12px;color:#8b949e;">
      Realer Verbrauch: Benziner {C.VEHICLE['ice']['consumption_l_100km']} L/100 km ·
      Elektro {C.VEHICLE['bev']['consumption_kwh_100km_real']} kWh/100 km
    </p>
    <table width="100%" cellpadding="0" cellspacing="0"
           style="border-collapse:collapse;border-radius:8px;overflow:hidden;
                  border:1px solid #21262d;">
      <thead>
        <tr style="background:#1c2128;">
          <th style="padding:10px 12px;text-align:left;color:#8b949e;font-size:11px;
                     text-transform:uppercase;">Antrieb / Ladetyp</th>
          <th style="padding:10px 12px;text-align:right;color:#8b949e;font-size:11px;
                     text-transform:uppercase;">Kosten/100 km</th>
          <th style="padding:10px 12px;text-align:right;color:#8b949e;font-size:11px;
                     text-transform:uppercase;">Reichweite bei {C.COMPARISON_BUDGET_EUR:.0f} €</th>
        </tr>
      </thead>
      <tbody>{vc_rows}</tbody>
    </table>
    {img_tag(img_vehicle, "Fahrzeugvergleich")}
  </td></tr>

  <!-- Heizkosten -->
  <tr><td style="padding:8px 32px;">
    <h2 style="margin:0 0 8px;font-size:16px;font-weight:700;color:#e6edf3;
               border-bottom:1px solid #21262d;padding-bottom:8px;">
      🏠 Heizkosten im Vergleich
    </h2>
    <p style="margin:0 0 12px;font-size:12px;color:#8b949e;">
      Wöchentliche Heizkosten bei aktuellen Energiepreisen
    </p>
    <table width="100%" cellpadding="0" cellspacing="0"
           style="border-collapse:collapse;border-radius:8px;overflow:hidden;
                  border:1px solid #21262d;">
      <thead>
        <tr style="background:#1c2128;">
          <th style="padding:10px 12px;text-align:left;color:#8b949e;font-size:11px;
                     text-transform:uppercase;">Heizsystem</th>
          <th style="padding:10px 12px;text-align:right;color:#8b949e;font-size:11px;
                     text-transform:uppercase;">Wöchentliche Kosten</th>
          <th style="padding:10px 12px;text-align:right;color:#8b949e;font-size:11px;
                     text-transform:uppercase;">Preisbasis</th>
        </tr>
      </thead>
      <tbody>{heat_rows}</tbody>
    </table>
    {img_tag(img_heating, "Heizkosten")}
  </td></tr>

  <!-- Hinweis BDEW -->
  <tr><td style="padding:8px 32px 16px;">
    <div style="background:#1c2128;border-radius:8px;padding:16px;border-left:3px solid #3b82f6;">
      <p style="margin:0 0 4px;font-size:12px;font-weight:600;color:#e6edf3;">
        ℹ️ Hinweis Haushaltsstrompreis
      </p>
      <p style="margin:0;font-size:11px;color:#8b949e;line-height:1.6;">
        Heimladen und Heizstrom basieren auf dem BDEW-Haushaltsdurchschnitt
        ({ref.get('bdew_electricity_ct_kwh', C.BDEW['electricity_ct_kwh'])} ct/kWh,
        Stand {ref.get('bdew_reference_period', C.BDEW['reference_period'])}).
        Öffentliche Ladepreise nach Verivox-Marktstudie DE
        (AC: {ref.get('public_charging_ac_ct_kwh', C.PUBLIC_CHARGING_AC_CT_KWH):.0f} ct/kWh,
         DC: {ref.get('public_charging_dc_ct_kwh', C.PUBLIC_CHARGING_DC_CT_KWH):.0f} ct/kWh).
        Kein tagesaktueller Tarif-API verfügbar; Werte werden quartalsweise aktualisiert.
      </p>
    </div>
  </td></tr>

  <!-- Footer -->
  <tr><td style="padding:16px 32px 28px;border-top:1px solid #21262d;">
    <p style="margin:0;font-size:11px;color:#8b949e;line-height:1.7;">
      <strong style="color:#e6edf3;">Quellen:</strong>
      Energy-Charts/ENTSO-E (Strom Day-Ahead) ·
      Yahoo Finance – BZ=F, TTF=F, MTF=F, HO=F (Rohstoffe) ·
      Tankerkönig/MTS-K (Kraftstoff) ·
      BDEW Strompreisanalyse (Haushalt) ·
      Bundesnetzagentur Monitoringbericht
      <br>
      Kohle: API2 CIF ARA (Argus/McCloskey) – der europäische Import-Benchmark. ·
      Heizöl: NY Harbor ULSD Futures als Proxy, inkl. geschätztem DE-Aufschlag.
      <br><br>
      Automatisch generiert am {date.today().isoformat()} ·
      <a href="https://github.com/" style="color:#3b82f6;">GitHub Repository</a>
    </p>
  </td></tr>

</table>
</td></tr>
</table>
</body>
</html>"""

    return html


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s %(message)s")

    latest_path = Path(C.DATA_DIR) / "latest.json"
    if not latest_path.exists():
        log.error(f"{latest_path} nicht gefunden – zuerst fetch_prices.py ausführen")
        return

    with open(latest_path, encoding="utf-8") as f:
        data = json.load(f)

    week = data["meta"]["week"]

    # HTML-E-Mail
    html = build_html(data)
    out_html = Path(C.OUTPUT_DIR) / f"newsletter_{week}.html"
    out_html.write_text(html, encoding="utf-8")
    log.info(f"HTML-Newsletter → {out_html}")

    # Web-JSON (strukturiert, Webseite kann daraus rendern)
    web_json = Path(C.OUTPUT_DIR) / "web_data.json"
    with open(web_json, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    log.info(f"Web-JSON → {web_json}")

    log.info("✓ Newsletter erzeugt")
    return str(out_html)


if __name__ == "__main__":
    main()
