"""
generate_charts.py – Charts im Mockup-Stil
Ausgabe nach data/charts/ (wird per Git committed, dann per GitHub Raw URL referenziert)
"""

import json, logging
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
ROOT = Path(__file__).parent.parent

# ── Stil: hell, editorial, monospace ──────────────────────────────
BG      = "#ffffff"
SURFACE = "#f4f3ef"
TEXT    = "#1a1a1a"
SUB     = "#888888"
GRID    = "#ebe9e3"
BORDER  = "#d8d5cd"

# Farben wie Mockup: Strom schwarz, Fossile in Grauabstufungen
COL = {
    "strom":  "#1a1a1a",
    "brent":  "#9ca3af",
    "ttf":    "#c4b5a0",
    "coal":   "#d1d5db",
    "dark":   "#1a1a1a",
    "mid":    "#6b7280",
    "light":  "#9ca3af",
    "pale":   "#d1d5db",
}

MONO = "monospace"


def style_ax(ax, fig):
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)
    ax.tick_params(colors=SUB, labelsize=9)
    for sp in ["top", "right"]: ax.spines[sp].set_visible(False)
    for sp in ["left", "bottom"]: ax.spines[sp].set_color(BORDER)
    ax.grid(True, color=GRID, linestyle="-", linewidth=0.5, alpha=1.0)
    ax.set_axisbelow(True)


def save(fig, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(path), dpi=110, bbox_inches="tight", facecolor=BG, edgecolor="none")
    plt.close(fig)
    log.info(f"  → {path.name}")


# ── Chart 1: Index-Zeitreihe ───────────────────────────────────────

def chart_index(idx_csv: Path, out: Path):
    df = pd.read_csv(str(idx_csv))
    if df.empty: return

    series = [
        ("strom_eur_mwh_idx", "Strom Day-Ahead DE",  COL["strom"],  2.0,  []),
        ("brent_eur_bbl_idx", "Brent Rohöl",          COL["brent"],  1.5,  []),
        ("ttf_idx",           "Erdgas TTF",            COL["ttf"],    1.5,  []),
        ("coal_eur_t_idx",    "Kohle API2",            COL["coal"],   1.5,  [4, 3]),
    ]

    fig, ax = plt.subplots(figsize=(11, 5), dpi=110)
    style_ax(ax, fig)

    labels = df["kw_label"].tolist()
    x = range(len(labels))

    for col, label, color, lw, dash in series:
        if col not in df.columns: continue
        vals = df[col].tolist()
        ax.plot(x, vals, label=label, color=color, linewidth=lw,
                linestyle=(0, dash) if dash else "solid")
        # letzter Wert
        last = df[col].dropna()
        if not last.empty:
            ax.text(len(last)-1 + 0.2, last.iloc[-1],
                    f"{last.iloc[-1]:.0f}", color=color, fontsize=8,
                    va="center", fontfamily=MONO)

    ax.axhline(100, color=BORDER, linewidth=0.8, linestyle="--")

    step = max(1, len(labels) // 10)
    ax.set_xticks(list(range(0, len(labels), step)))
    ax.set_xticklabels(labels[::step], rotation=35, ha="right",
                       fontsize=8, fontfamily=MONO)
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter("%g"))
    ax.tick_params(axis="y", labelsize=8)
    for tick in ax.get_yticklabels():
        tick.set_fontfamily(MONO)

    # Legende manuell (wie Mockup)
    legend_items = [(l, c, d) for _, l, c, _, d in series
                    if (_ := None) is None and any(col in df.columns
                    for col, lbl, clr, lw2, ds in series if lbl == l)]
    from matplotlib.lines import Line2D
    handles = [
        Line2D([0], [0], color=c, linewidth=1.5,
               linestyle=(0, d) if d else "solid", label=l)
        for _, l, c, _, d in series
        if (col := _) is not None or True
    ]
    handles2 = []
    for col, label, color, lw, dash in series:
        if col not in df.columns: continue
        handles2.append(Line2D([0],[0], color=color, linewidth=1.5,
                               linestyle=(0,dash) if dash else "solid", label=label))
    ax.legend(handles=handles2, loc="upper right", fontsize=9,
              frameon=True, facecolor=BG, edgecolor=BORDER,
              prop={"family": MONO, "size": 9})

    fig.tight_layout()
    save(fig, out)


# ── Chart 2: Fahrzeuge ─────────────────────────────────────────────

def chart_vehicle(data: dict, out: Path):
    vc = data.get("vehicle_comparison", {})
    if not vc: return

    # Reihenfolge: bestes zuerst (nach km_for_budget)
    order_km   = ["bev_home", "ice", "bev_public_ac", "bev_public_dc"]
    order_cost = ["ice", "bev_public_dc", "bev_public_ac", "bev_home"]

    colors_km   = [COL["dark"], COL["mid"], COL["light"], COL["pale"]]
    colors_cost = [COL["dark"], COL["mid"], COL["light"], COL["pale"]]

    def get_bars(order, val_key):
        labels, vals, prices, cols = [], [], [], []
        for key, color in zip(order, [COL["dark"], COL["mid"], COL["light"], COL["pale"]]):
            e = vc.get(key)
            if not e: continue
            labels.append(f"{e['label']}\n{e['price_label']}")
            vals.append(e.get(val_key, 0))
            cols.append(color)
        return labels, vals, cols

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.5), dpi=110)
    fig.patch.set_facecolor(BG)

    for ax, order, val_key, title, unit_fmt in [
        (ax1, order_km,   "km_for_budget",  "Reichweite für 50 €",  "{:.0f} km"),
        (ax2, order_cost, "cost_per_100km", "Kosten pro 100 km",    "{:.2f} €"),
    ]:
        style_ax(ax, fig)
        lbls, vals, cols = get_bars(order, val_key)
        if not vals: continue

        y = range(len(lbls))
        bars = ax.barh(list(y), vals, color=cols, height=0.55)
        ax.set_yticks(list(y))
        ax.set_yticklabels(lbls, fontsize=9, fontfamily=MONO)
        ax.invert_yaxis()
        ax.set_title(title, fontsize=11, fontfamily="serif", pad=10, color=TEXT)
        ax.set_xlabel(unit_fmt.split()[1] if " " in unit_fmt else "", fontsize=9)

        max_val = max(vals)
        for bar, val, col in zip(bars, vals, cols):
            txt_color = "#fff" if col in [COL["dark"], COL["mid"]] else TEXT
            ax.text(bar.get_width() - max_val * 0.02,
                    bar.get_y() + bar.get_height() / 2,
                    unit_fmt.format(val),
                    va="center", ha="right", color=txt_color,
                    fontsize=9, fontfamily=MONO, fontweight="bold")
        ax.set_xlim(0, max_val * 1.05)
        ax.xaxis.set_visible(False)
        ax.spines["bottom"].set_visible(False)

    fig.suptitle("Opel Astra – Benziner vs. Elektro",
                 fontsize=13, fontfamily="serif", color=TEXT, y=1.01)
    fig.tight_layout()
    save(fig, out)


# ── Chart 3: Heizkosten ────────────────────────────────────────────

def chart_heating(data: dict, out: Path):
    heating = data.get("heating_costs", {})
    if not heating: return

    sys_order = ["heat_pump", "gas_boiler", "oil_boiler"]  # kein Direktstrom
    sys_cols  = [COL["dark"], COL["mid"], COL["light"]]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4), dpi=110)
    fig.patch.set_facecolor(BG)

    for ax, (prop_key, prop_label) in zip([ax1, ax2], [
        ("haus_150qm",    "Einfamilienhaus 150 m²"),
        ("wohnung_100qm", "Wohnung 100 m²"),
    ]):
        style_ax(ax, fig)
        systems = heating.get(prop_key, {}).get("systems", {})
        lbls, vals, cols = [], [], []
        for sk, col in zip(sys_order, sys_cols):
            sys = systems.get(sk, {})
            cost = sys.get("weekly_cost_eur")
            if cost is None: continue
            lbls.append(sys.get("label", sk))
            vals.append(cost)
            cols.append(col)

        if not vals: continue
        y = range(len(lbls))
        bars = ax.barh(list(y), vals, color=cols, height=0.5)
        ax.set_yticks(list(y))
        ax.set_yticklabels(lbls, fontsize=9, fontfamily=MONO)
        ax.invert_yaxis()
        ax.set_title(prop_label, fontsize=11, fontfamily="serif", pad=10, color=TEXT)

        max_val = max(vals)
        for bar, val, col in zip(bars, vals, cols):
            txt_color = "#fff" if col in [COL["dark"], COL["mid"]] else TEXT
            ax.text(bar.get_width() - max_val * 0.02,
                    bar.get_y() + bar.get_height() / 2,
                    f"{val:.0f} €",
                    va="center", ha="right", color=txt_color,
                    fontsize=9, fontfamily=MONO, fontweight="bold")
        ax.set_xlim(0, max_val * 1.05)
        ax.xaxis.set_visible(False)
        ax.spines["bottom"].set_visible(False)

    fig.suptitle("Wöchentliche Heizkosten",
                 fontsize=13, fontfamily="serif", color=TEXT, y=1.01)
    fig.tight_layout()
    save(fig, out)


# ── Main ───────────────────────────────────────────────────────────

def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s %(message)s")

    charts_dir  = ROOT / "data" / "charts"
    latest_path = ROOT / C.DATA_DIR / "latest.json"
    idx_csv     = ROOT / C.DATA_DIR / "indexed.csv"

    if not latest_path.exists():
        log.error("latest.json fehlt"); return

    with open(latest_path, encoding="utf-8") as f:
        data = json.load(f)

    log.info("Erzeuge Charts …")
    if idx_csv.exists():
        chart_index(idx_csv, charts_dir / "chart_index.png")
    chart_vehicle(data, charts_dir / "chart_vehicle.png")
    chart_heating(data, charts_dir / "chart_heating.png")
    log.info("✓ Charts fertig")


if __name__ == "__main__":
    main()
