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
from matplotlib.lines import Line2D
import pandas as pd

import sys
sys.path.insert(0, str(Path(__file__).parent))
import config as C

log = logging.getLogger(__name__)
ROOT = Path(__file__).parent.parent

BG     = "#ffffff"
TEXT   = "#1a1a1a"
SUB    = "#888888"
GRID   = "#ebe9e3"
BORDER = "#d8d5cd"
MONO   = "monospace"

COL = {
    "strom": "#1a1a1a",
    "brent": "#9ca3af",
    "ttf":   "#c4b5a0",
    "coal":  "#d1d5db",
    "dark":  "#1a1a1a",
    "mid":   "#6b7280",
    "light": "#9ca3af",
    "pale":  "#d1d5db",
}


def style_ax(ax, fig):
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)
    ax.tick_params(colors=SUB, labelsize=9)
    for sp in ["top", "right"]:
        ax.spines[sp].set_visible(False)
    for sp in ["left", "bottom"]:
        ax.spines[sp].set_color(BORDER)
    ax.grid(True, color=GRID, linestyle="-", linewidth=0.5)
    ax.set_axisbelow(True)


def save(fig, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(path), dpi=110, bbox_inches="tight", facecolor=BG, edgecolor="none")
    plt.close(fig)
    log.info(f"  → {path.name}")


# ── Chart 1: Index-Zeitreihe ───────────────────────────────────────

def chart_index(idx_csv: Path, out: Path):
    df = pd.read_csv(str(idx_csv))
    if df.empty:
        return

    series = [
        ("strom_eur_mwh_idx", "Strom Day-Ahead DE", COL["strom"], 2.0, []),
        ("brent_eur_bbl_idx", "Brent Rohöl",         COL["brent"], 1.5, []),
        ("ttf_idx",           "Erdgas TTF",           COL["ttf"],   1.5, []),
        ("coal_eur_t_idx",    "Kohle API2",           COL["coal"],  1.5, [4, 3]),
    ]

    fig, ax = plt.subplots(figsize=(11, 5), dpi=110)
    style_ax(ax, fig)

    labels = df["kw_label"].tolist()
    x = list(range(len(labels)))

    legend_handles = []
    for col, label, color, lw, dash in series:
        if col not in df.columns:
            continue
        vals = df[col].tolist()
        ls = (0, tuple(dash)) if dash else "solid"
        ax.plot(x, vals, color=color, linewidth=lw, linestyle=ls)
        last = df[col].dropna()
        if not last.empty:
            ax.text(len(last) - 1 + 0.2, last.iloc[-1],
                    f"{last.iloc[-1]:.0f}", color=color, fontsize=8,
                    va="center", fontfamily=MONO)
        legend_handles.append(
            Line2D([0], [0], color=color, linewidth=1.5, linestyle=ls, label=label)
        )

    ax.axhline(100, color=BORDER, linewidth=0.8, linestyle="--")

    step = max(1, len(labels) // 10)
    ax.set_xticks(x[::step])
    ax.set_xticklabels(labels[::step], rotation=35, ha="right", fontsize=8, fontfamily=MONO)
    for tick in ax.get_yticklabels():
        tick.set_fontfamily(MONO)
        tick.set_fontsize(8)

    ax.legend(handles=legend_handles, loc="upper right", fontsize=9,
              frameon=True, facecolor=BG, edgecolor=BORDER,
              prop={"family": MONO, "size": 9})

    fig.tight_layout()
    save(fig, out)


# ── Chart 2: Fahrzeuge ─────────────────────────────────────────────

def chart_vehicle(data: dict, out: Path):
    vc = data.get("vehicle_comparison", {})
    if not vc:
        return

    order_km   = ["bev_home", "ice", "bev_public_ac", "bev_public_dc"]
    order_cost = ["ice", "bev_public_dc", "bev_public_ac", "bev_home"]
    shade      = [COL["dark"], COL["mid"], COL["light"], COL["pale"]]

    def get_bars(order, val_key):
        lbls, vals, cols = [], [], []
        for key, color in zip(order, shade):
            e = vc.get(key)
            if not e:
                continue
            lbls.append(f"{e['label']}\n{e['price_label']}")
            vals.append(e.get(val_key, 0))
            cols.append(color)
        return lbls, vals, cols

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.5), dpi=110)
    fig.patch.set_facecolor(BG)

    for ax, order, val_key, title, unit_fmt in [
        (ax1, order_km,   "km_for_budget",  "Reichweite für 50 €", "{:.0f} km"),
        (ax2, order_cost, "cost_per_100km", "Kosten pro 100 km",   "{:.2f} €"),
    ]:
        style_ax(ax, fig)
        lbls, vals, cols = get_bars(order, val_key)
        if not vals:
            continue

        y = list(range(len(lbls)))
        bars = ax.barh(y, vals, color=cols, height=0.55)
        ax.set_yticks(y)
        ax.set_yticklabels(lbls, fontsize=9, fontfamily=MONO)
        ax.invert_yaxis()
        ax.set_title(title, fontsize=11, fontfamily="serif", pad=10, color=TEXT)
        ax.xaxis.set_visible(False)
        ax.spines["bottom"].set_visible(False)

        max_val = max(vals) if vals else 1
        for bar, val, col in zip(bars, vals, cols):
            txt_color = "#fff" if col in [COL["dark"], COL["mid"]] else TEXT
            ax.text(bar.get_width() - max_val * 0.02,
                    bar.get_y() + bar.get_height() / 2,
                    unit_fmt.format(val),
                    va="center", ha="right",
                    color=txt_color, fontsize=9, fontfamily=MONO, fontweight="bold")
        ax.set_xlim(0, max_val * 1.05)

    fig.suptitle("Opel Astra – Benziner vs. Elektro",
                 fontsize=13, fontfamily="serif", color=TEXT, y=1.01)
    fig.tight_layout()
    save(fig, out)


# ── Chart 3: Heizkosten ────────────────────────────────────────────

def chart_heating(data: dict, out: Path):
    heating = data.get("heating_costs", {})
    if not heating:
        return

    sys_order = ["heat_pump", "gas_boiler", "oil_boiler"]
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
            if cost is None:
                continue
            lbls.append(sys.get("label", sk))
            vals.append(cost)
            cols.append(col)

        if not vals:
            continue

        y = list(range(len(lbls)))
        bars = ax.barh(y, vals, color=cols, height=0.5)
        ax.set_yticks(y)
        ax.set_yticklabels(lbls, fontsize=9, fontfamily=MONO)
        ax.invert_yaxis()
        ax.set_title(prop_label, fontsize=11, fontfamily="serif", pad=10, color=TEXT)
        ax.xaxis.set_visible(False)
        ax.spines["bottom"].set_visible(False)

        max_val = max(vals) if vals else 1
        for bar, val, col in zip(bars, vals, cols):
            txt_color = "#fff" if col in [COL["dark"], COL["mid"]] else TEXT
            ax.text(bar.get_width() - max_val * 0.02,
                    bar.get_y() + bar.get_height() / 2,
                    f"{val:.0f} €",
                    va="center", ha="right",
                    color=txt_color, fontsize=9, fontfamily=MONO, fontweight="bold")
        ax.set_xlim(0, max_val * 1.05)

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
        log.error("latest.json fehlt")
        return

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
