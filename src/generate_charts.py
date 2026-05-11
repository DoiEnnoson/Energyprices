"""
generate_charts.py – Erzeugt drei Diagramme für den Newsletter

Chart 1: Energiepreise der Woche (Day-Ahead-Strom + Rohstoffe, Zeitreihe aus CSV)
Chart 2: Opel Astra – km für 50 € und Kosten pro 100 km
Chart 3: Heizkosten im Vergleich (Haus 150 m² und Wohnung 100 m²)

Ausgabe: output/chart_prices.png, output/chart_vehicle.png, output/chart_heating.png
"""

import json
import logging
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import pandas as pd

import sys
sys.path.insert(0, str(Path(__file__).parent))
import config as C

log = logging.getLogger(__name__)


# ── Stilkonstanten ─────────────────────────────────────────────────

BG     = C.COLORS["background"]
SURF   = C.COLORS["surface"]
TEXT   = C.COLORS["text"]
SUB    = C.COLORS["subtext"]
GRID_C = C.COLORS["grid"]

def apply_dark_style(ax, fig):
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(SURF)
    ax.tick_params(colors=SUB, labelsize=9)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    for spine in ["left", "bottom"]:
        ax.spines[spine].set_color(GRID_C)
    ax.grid(True, color=GRID_C, linestyle="--", linewidth=0.6, alpha=0.6)
    ax.title.set_color(TEXT)
    ax.xaxis.label.set_color(SUB)
    ax.yaxis.label.set_color(SUB)


def source_note(fig, text: str):
    fig.text(0.5, 0.01, text, ha="center", fontsize=7.5, color=SUB)


def save(fig, path: str):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150, bbox_inches="tight",
                facecolor=BG, edgecolor="none")
    plt.close(fig)
    log.info(f"  Gespeichert → {path}")


# ── Chart 1: Energiepreise (historische Zeitreihe) ─────────────────

def chart_prices(hist_csv: str, out_path: str):
    df = pd.read_csv(hist_csv, parse_dates=["week_start"])
    df = df.tail(26)  # letzte 26 Wochen

    fig, axes = plt.subplots(2, 2, figsize=(14, 9), dpi=120)
    fig.suptitle("Energiepreise Deutschland – letzte 26 Wochen",
                 fontsize=14, fontweight="bold", color=TEXT, y=1.01)

    panels = [
        ("elec_dayahead_avg_eur_mwh", "Strom Day-Ahead",     "EUR/MWh",   C.COLORS["electricity"]),
        ("ttf_avg_eur_mwh",           "Erdgas (TTF)",         "EUR/MWh",   C.COLORS["ttf"]),
        ("brent_avg_eur_bbl",         "Brent Rohöl",          "EUR/bbl",   C.COLORS["brent"]),
        ("coal_api2_avg_eur_t",       "Kohle (API2 CIF ARA)", "EUR/t",     C.COLORS["coal"]),
    ]

    for ax, (col, title, unit, color) in zip(axes.flat, panels):
        apply_dark_style(ax, fig)
        if col in df.columns and df[col].notna().any():
            ax.plot(df["week_start"], df[col], color=color, linewidth=2.0, marker="o",
                    markersize=3.5, markerfacecolor=color, alpha=0.9)
            ax.fill_between(df["week_start"], df[col], alpha=0.12, color=color)
            last_val = df[col].dropna().iloc[-1]
            ax.axhline(last_val, color=color, linewidth=0.7, linestyle=":", alpha=0.4)
            ax.text(df["week_start"].iloc[-1], last_val,
                    f"  {last_val:.1f}", color=color, fontsize=8.5, va="center")
        ax.set_title(title, fontsize=11, fontweight="bold", pad=8)
        ax.set_ylabel(unit, fontsize=9)
        ax.xaxis.set_major_locator(mticker.MaxNLocator(6))
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=30, ha="right", fontsize=8)

    fig.tight_layout(rect=[0, 0.04, 1, 1])
    source_note(fig,
        "Strom: Energy-Charts/ENTSO-E · Gas (TTF), Brent: Yahoo Finance · "
        "Kohle API2 CIF ARA: Yahoo Finance (MTF=F)"
    )
    save(fig, out_path)


# ── Chart 2: Fahrzeugvergleich ─────────────────────────────────────

def chart_vehicle(data: dict, out_path: str):
    vc = data.get("vehicle_comparison", {})
    if not vc:
        log.warning("Keine Fahrzeugvergleichsdaten")
        return

    labels = []
    km_vals = []
    cost_vals = []
    colors = []

    mapping = [
        ("ice",           C.COLORS["ice"],      "Benziner"),
        ("bev_home",      C.COLORS["bev_home"], "BEV Heimladen"),
        ("bev_public_ac", C.COLORS["bev_ac"],   "BEV Öffentl. AC"),
        ("bev_public_dc", C.COLORS["bev_dc"],   "BEV Schnelll. DC"),
    ]

    for key, color, fallback_label in mapping:
        entry = vc.get(key)
        if not entry:
            continue
        labels.append(entry.get("label", fallback_label).split(" – ")[-1]
                       if " – " in entry.get("label", "") else fallback_label)
        km_vals.append(entry.get("km_for_budget", 0))
        cost_vals.append(entry.get("cost_per_100km", 0))
        colors.append(color)

    if not labels:
        log.warning("Fahrzeugvergleich: keine auswertbaren Einträge")
        return

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 6), dpi=120)
    fig.suptitle(
        f"Opel Astra: Benziner vs. Elektro – Kostenvergleich",
        fontsize=13, fontweight="bold", color=TEXT
    )

    # Links: km für 50 €
    apply_dark_style(ax1, fig)
    bars1 = ax1.barh(labels, km_vals, color=colors, height=0.55, alpha=0.88)
    ax1.set_title(f"Reichweite mit {C.COMPARISON_BUDGET_EUR:.0f} €", fontsize=11, pad=8)
    ax1.set_xlabel("Kilometer")
    for bar, val in zip(bars1, km_vals):
        ax1.text(bar.get_width() + max(km_vals) * 0.02, bar.get_y() + bar.get_height() / 2,
                 f"{val:,.0f} km", va="center", color=TEXT, fontsize=9, fontweight="bold")
    ax1.set_xlim(0, max(km_vals) * 1.22)
    ax1.invert_yaxis()

    # Rechts: Kosten pro 100 km
    apply_dark_style(ax2, fig)
    bars2 = ax2.barh(labels, cost_vals, color=colors, height=0.55, alpha=0.88)
    ax2.set_title("Kosten pro 100 km", fontsize=11, pad=8)
    ax2.set_xlabel("EUR")
    for bar, val in zip(bars2, cost_vals):
        ax2.text(bar.get_width() + max(cost_vals) * 0.02, bar.get_y() + bar.get_height() / 2,
                 f"{val:.2f} €", va="center", color=TEXT, fontsize=9, fontweight="bold")
    ax2.set_xlim(0, max(cost_vals) * 1.28)
    ax2.invert_yaxis()

    # Verbrauchshinweis
    fig.text(0.5, -0.02,
             f"Astra 1.2T: {C.VEHICLE['ice']['consumption_l_100km']} L/100km (real) · "
             f"Astra Electric: {C.VEHICLE['bev']['consumption_kwh_100km_real']} kWh/100km (real) · "
             f"Kraftstoff: Tankerkönig DE-Durchschnitt · Laden: BDEW / {C.PUBLIC_CHARGING_SOURCE}",
             ha="center", fontsize=7.5, color=SUB)

    fig.tight_layout(rect=[0, 0.04, 1, 1])
    save(fig, out_path)


# ── Chart 3: Heizkosten ────────────────────────────────────────────

def chart_heating(data: dict, out_path: str):
    heating = data.get("heating_costs", {})
    if not heating:
        log.warning("Keine Heizkostendaten")
        return

    system_keys  = ["gas_boiler", "oil_boiler", "heat_pump", "direct_electric"]
    system_labels = ["Gasheizung", "Ölheizung", "Wärmepumpe\n(COP 3,5)", "Direktstrom"]
    heat_colors   = [
        C.COLORS["gas"], C.COLORS["oil_heat"],
        C.COLORS["heat_pump"], C.COLORS["direct_elec"]
    ]
    prop_keys   = ["haus_150qm", "wohnung_100qm"]
    prop_labels = ["Einfamilienhaus 150 m²", "Wohnung 100 m²"]

    fig, axes = plt.subplots(1, 2, figsize=(13, 6), dpi=120)
    fig.suptitle("Heizkosten im Vergleich – wöchentliche Kosten", fontsize=13,
                 fontweight="bold", color=TEXT)

    for ax, prop_key, prop_label in zip(axes, prop_keys, prop_labels):
        apply_dark_style(ax, fig)
        values = []
        for sys_key in system_keys:
            cost = (heating
                    .get(prop_key, {})
                    .get("systems", {})
                    .get(sys_key, {})
                    .get("weekly_cost_eur"))
            values.append(cost if cost is not None else 0.0)

        bars = ax.bar(system_labels, values, color=heat_colors, width=0.55, alpha=0.88)
        ax.set_title(prop_label, fontsize=11, pad=8)
        ax.set_ylabel("EUR / Woche")
        for bar, val in zip(bars, values):
            if val > 0:
                ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + max(values) * 0.02,
                        f"{val:.2f} €", ha="center", color=TEXT, fontsize=9, fontweight="bold")
        ax.set_ylim(0, max(v for v in values if v > 0) * 1.22)
        plt.setp(ax.xaxis.get_majorticklabels(), fontsize=9)

    fig.text(0.5, -0.02,
             f"Haus: {C.HEATING['haus_150qm']['annual_kwh']:,} kWh/Jahr · "
             f"Wohnung: {C.HEATING['wohnung_100qm']['annual_kwh']:,} kWh/Jahr · "
             f"Gas: BDEW {C.BDEW['gas_ct_kwh']} ct/kWh · "
             f"Öl: HO=F Futures-Proxy · Strom: BDEW {C.BDEW['electricity_ct_kwh']} ct/kWh",
             ha="center", fontsize=7.5, color=SUB)

    fig.tight_layout(rect=[0, 0.04, 1, 1])
    save(fig, out_path)


# ── Einstiegspunkt ─────────────────────────────────────────────────

def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s %(message)s")

    latest_path = Path(C.DATA_DIR) / "latest.json"
    hist_csv    = Path(C.DATA_DIR) / "historical.csv"

    if not latest_path.exists():
        log.error(f"Keine Daten: {latest_path} – zuerst fetch_prices.py ausführen")
        return

    with open(latest_path, encoding="utf-8") as f:
        data = json.load(f)

    week = data["meta"]["week"]
    log.info(f"Erzeuge Charts für {week} …")

    if hist_csv.exists():
        chart_prices(str(hist_csv), f"{C.OUTPUT_DIR}/chart_prices.png")
    else:
        log.warning("historical.csv nicht gefunden – Preischart übersprungen")

    chart_vehicle(data, f"{C.OUTPUT_DIR}/chart_vehicle.png")
    chart_heating(data, f"{C.OUTPUT_DIR}/chart_heating.png")

    log.info("✓ Charts abgeschlossen")


if __name__ == "__main__":
    main()
