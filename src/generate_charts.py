"""
generate_charts.py – Drei Charts aus Tagesdaten ab 1.1.2026

Chart 1: Alle Energieträger indexiert auf 100 = 1.1.2026 (Zeitreihe täglich)
Chart 2: Opel Astra ICE vs BEV – km für 50€ und Kosten/100km
Chart 3: Heizkosten wöchentlich – Haus 150m² und Wohnung 100m²
"""

import json
import logging
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd

import sys
sys.path.insert(0, str(Path(__file__).parent))
import config as C

log = logging.getLogger(__name__)

BG   = C.COLORS["background"]
SURF = C.COLORS["surface"]
TEXT = C.COLORS["text"]
SUB  = C.COLORS["subtext"]
GRID = C.COLORS["grid"]


def dark(ax, fig):
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(SURF)
    ax.tick_params(colors=SUB, labelsize=9)
    for sp in ["top", "right"]:
        ax.spines[sp].set_visible(False)
    for sp in ["left", "bottom"]:
        ax.spines[sp].set_color(GRID)
    ax.grid(True, color=GRID, linestyle="--", linewidth=0.6, alpha=0.7)
    ax.title.set_color(TEXT)
    ax.xaxis.label.set_color(SUB)
    ax.yaxis.label.set_color(SUB)


def save(fig, path: str):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor=BG, edgecolor="none")
    plt.close(fig)
    log.info(f"  Gespeichert → {path}")


# ── Chart 1: Index 100 = 1.1.2026 ─────────────────────────────────

def chart_index(idx_csv: str, out: str):
    df = pd.read_csv(idx_csv, parse_dates=["date"])
    if df.empty:
        log.warning("indexed.csv leer")
        return

    series = [
        ("strom_eur_mwh_idx", "Strom Day-Ahead DE",     C.COLORS["electricity"]),
        ("brent_eur_bbl_idx",  "Brent Rohöl (EUR/bbl)", C.COLORS["brent"]),
        ("ttf_idx",            "Erdgas TTF (EUR/MWh)",  C.COLORS["ttf"]),
        ("heizoel_eur_liter_idx", "Heizöl (EUR/L)",     C.COLORS["heating_oil"]),
    ]

    fig, ax = plt.subplots(figsize=(14, 7), dpi=120)
    dark(ax, fig)

    for col, label, color in series:
        if col not in df.columns:
            continue
        s = df[["date", col]].dropna()
        ax.plot(s["date"], s[col], label=label, linewidth=1.8,
                color=color, alpha=0.9)
        # letzter Wert als Label
        last = s.iloc[-1]
        ax.text(last["date"], last[col], f"  {last[col]:.0f}",
                color=color, fontsize=8, va="center")

    ax.axhline(100, color="#ffffff", linewidth=0.7, linestyle="--", alpha=0.3)
    ax.text(df["date"].iloc[0], 101, "  Basis 100 = 1.1.2026",
            color=SUB, fontsize=8)

    ax.set_title("Energiepreise Deutschland – Index 100 = 1. Januar 2026",
                 fontsize=14, fontweight="bold", pad=14)
    ax.set_ylabel("Index")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d.%m."))
    ax.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=0, interval=2))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=35, ha="right")

    legend = ax.legend(loc="upper left", fontsize=10, frameon=True,
                       facecolor=SURF, edgecolor=GRID, labelcolor=TEXT)
    legend.get_frame().set_alpha(0.9)

    fig.text(0.5, 0.01,
             "Strom: Energy-Charts/ENTSO-E · Brent, TTF: Yahoo Finance · "
             "Heizöl: NY Harbor ULSD Futures (Proxy) · Tageswerte",
             ha="center", fontsize=7.5, color=SUB)

    fig.tight_layout(rect=[0, 0.04, 1, 1])
    save(fig, out)


# ── Chart 2: Fahrzeugvergleich ─────────────────────────────────────

def chart_vehicle(data: dict, out: str):
    vc = data.get("vehicle_comparison", {})
    if not vc:
        return

    mapping = [
        ("ice",           "Benziner\n(E5)",         C.COLORS["ice"]),
        ("bev_home",      "BEV\nHeimladen",         C.COLORS["bev_home"]),
        ("bev_public_ac", "BEV\nÖffentl. AC",       C.COLORS["bev_ac"]),
        ("bev_public_dc", "BEV\nSchnellladen DC",   C.COLORS["bev_dc"]),
    ]

    labels, km_vals, cost_vals, colors = [], [], [], []
    for key, label, color in mapping:
        e = vc.get(key)
        if not e:
            continue
        labels.append(label)
        km_vals.append(e.get("km_for_budget", 0))
        cost_vals.append(e.get("cost_per_100km", 0))
        colors.append(color)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 6), dpi=120)
    fig.suptitle("Opel Astra – Benziner vs. Elektro",
                 fontsize=13, fontweight="bold", color=TEXT)

    for ax, vals, title, unit in [
        (ax1, km_vals,  f"Reichweite mit {C.COMPARISON_BUDGET_EUR:.0f} €", "km"),
        (ax2, cost_vals, "Kosten pro 100 km", "EUR"),
    ]:
        dark(ax, fig)
        bars = ax.barh(labels, vals, color=colors, height=0.5, alpha=0.88)
        ax.set_title(title, fontsize=11, pad=8)
        ax.set_xlabel(unit)
        for bar, val in zip(bars, vals):
            ax.text(bar.get_width() + max(vals) * 0.02,
                    bar.get_y() + bar.get_height() / 2,
                    f"{val:,.0f} {unit}" if unit == "km" else f"{val:.2f} €",
                    va="center", color=TEXT, fontsize=9, fontweight="bold")
        ax.set_xlim(0, max(vals) * 1.25)
        ax.invert_yaxis()

    fig.text(0.5, -0.02,
             f"Benziner: {C.VEHICLE['ice']['consumption_l_100km']} L/100km · "
             f"Elektro: {C.VEHICLE['bev']['consumption_kwh_100km_real']} kWh/100km (real)",
             ha="center", fontsize=7.5, color=SUB)
    fig.tight_layout(rect=[0, 0.04, 1, 1])
    save(fig, out)


# ── Chart 3: Heizkosten ────────────────────────────────────────────

def chart_heating(data: dict, out: str):
    heating = data.get("heating_costs", {})
    if not heating:
        return

    sys_keys   = ["gas_boiler", "oil_boiler", "heat_pump", "direct_electric"]
    sys_labels = ["Gasheizung", "Ölheizung", "Wärmepumpe\n(COP 3,5)", "Direktstrom"]
    sys_colors = [C.COLORS["gas"], C.COLORS["oil_heat"],
                  C.COLORS["heat_pump"], C.COLORS["direct_elec"]]

    fig, axes = plt.subplots(1, 2, figsize=(13, 6), dpi=120)
    fig.suptitle("Heizkosten im Vergleich – wöchentliche Energiekosten",
                 fontsize=13, fontweight="bold", color=TEXT)

    for ax, (prop_key, prop_label) in zip(axes, [
        ("haus_150qm",    "Einfamilienhaus 150 m²"),
        ("wohnung_100qm", "Wohnung 100 m²"),
    ]):
        dark(ax, fig)
        vals = [
            heating.get(prop_key, {}).get("systems", {})
                   .get(sk, {}).get("weekly_cost_eur") or 0
            for sk in sys_keys
        ]
        bars = ax.bar(sys_labels, vals, color=sys_colors, width=0.5, alpha=0.88)
        ax.set_title(prop_label, fontsize=11, pad=8)
        ax.set_ylabel("EUR / Woche")
        for bar, val in zip(bars, vals):
            if val:
                ax.text(bar.get_x() + bar.get_width() / 2,
                        bar.get_height() + max(v for v in vals if v) * 0.02,
                        f"{val:.2f} €", ha="center", color=TEXT,
                        fontsize=9, fontweight="bold")
        ax.set_ylim(0, max(v for v in vals if v) * 1.25)

    fig.text(0.5, -0.02,
             f"Strom: BDEW {C.BDEW['electricity_ct_kwh']} ct/kWh · "
             f"Gas: BDEW {C.BDEW['gas_ct_kwh']} ct/kWh · "
             f"Öl: Futures-Proxy",
             ha="center", fontsize=7.5, color=SUB)
    fig.tight_layout(rect=[0, 0.04, 1, 1])
    save(fig, out)


# ── Einstieg ───────────────────────────────────────────────────────

def main():
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s  %(levelname)-8s %(message)s")

    latest_path = Path(C.DATA_DIR) / "latest.json"
    idx_csv     = Path(C.DATA_DIR) / "indexed.csv"

    if not latest_path.exists():
        log.error("latest.json fehlt – zuerst fetch_prices.py")
        return

    with open(latest_path, encoding="utf-8") as f:
        data = json.load(f)

    log.info("Erzeuge Charts …")

    if idx_csv.exists():
        chart_index(str(idx_csv), f"{C.OUTPUT_DIR}/chart_index.png")
    else:
        log.warning("indexed.csv fehlt – Index-Chart übersprungen")

    chart_vehicle(data, f"{C.OUTPUT_DIR}/chart_vehicle.png")
    chart_heating(data, f"{C.OUTPUT_DIR}/chart_heating.png")

    log.info("✓ Charts fertig")


if __name__ == "__main__":
    main()
