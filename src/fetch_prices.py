"""
fetch_prices.py – Tägliche Energiepreisdaten für Deutschland ab 1.1.2026

Quellen:
  - Energy-Charts API  → Day-Ahead-Strom DE-LU (stündlich → täglich)
  - Yahoo Finance      → Brent, TTF, Heizöl-Futures, EUR/USD
  - Tankerkönig        → Kraftstoffpreise DE (täglich)

Ausgabe:
  - data/daily_prices.csv     (alle Tage ab 1.1.2026, täglich erweitert)
  - data/latest.json          (heutiger Stand für Newsletter)
  - data/indexed.csv          (alle Serien auf Index 100 = 1.1.2026)
"""

import os
import json
import logging
import requests
import pandas as pd
import yfinance as yf
from datetime import date, timedelta
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent))
import config as C

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s %(message)s")
log = logging.getLogger(__name__)

START_DATE = date(2026, 1, 1)
TODAY      = date.today()
YESTERDAY  = TODAY - timedelta(days=1)


# ── Hilfsfunktion: yfinance Series sauber extrahieren ─────────────

def yf_close(df, ticker) -> pd.Series:
    """Extrahiert Close-Spalte robust – egal ob Single- oder MultiIndex"""
    if df.empty:
        return pd.Series(dtype=float)
    close = df["Close"]
    # yfinance gibt bei Multi-Ticker MultiIndex zurück
    if isinstance(close.columns if hasattr(close, 'columns') else None, pd.MultiIndex):
        close = close[ticker]
    # Manchmal ist Close selbst ein DataFrame mit einer Spalte
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    return close.squeeze().dropna()


# ── 1. Day-Ahead-Strom ─────────────────────────────────────────────

def fetch_electricity() -> pd.DataFrame:
    log.info("Energy-Charts: Day-Ahead-Strom DE-LU …")
    url = "https://api.energy-charts.info/price"
    r = requests.get(url, params={
        "bzn":   "DE-LU",
        "start": START_DATE.isoformat(),
        "end":   TODAY.isoformat(),
    }, timeout=30)
    r.raise_for_status()
    raw = r.json()

    df = pd.DataFrame({"ts": raw["unix_seconds"], "price": raw["price"]})
    df["date"] = (pd.to_datetime(df["ts"], unit="s", utc=True)
                  .dt.tz_convert("Europe/Berlin")
                  .dt.date)
    daily = df.dropna(subset=["price"]).groupby("date")["price"].mean().round(2)
    result = daily.reset_index()
    result.columns = ["date", "strom_eur_mwh"]
    log.info(f"  {len(result)} Tage geladen")
    return result


# ── 2. Yahoo Finance ───────────────────────────────────────────────

def fetch_yahoo() -> pd.DataFrame:
    log.info("Yahoo Finance: Rohstoff-Futures …")
    tickers = {
        "brent":       "BZ=F",
        "ttf":         "TTF=F",
        "heating_oil": "HO=F",
        "eurusd":      "EURUSD=X",
    }

    frames = []
    for name, ticker in tickers.items():
        try:
            raw = yf.download(
                ticker,
                start=START_DATE.isoformat(),
                end=TODAY.isoformat(),
                progress=False,
                auto_adjust=True,
            )
            close = yf_close(raw, ticker)
            if close.empty:
                log.warning(f"  {name} ({ticker}): keine Daten")
                continue
            s = close.copy()
            s.index = pd.to_datetime(s.index).date
            df = s.reset_index()
            df.columns = ["date", name]
            frames.append(df)
            log.info(f"  {name}: {len(df)} Tage")
        except Exception as exc:
            log.error(f"  {name} ({ticker}): {exc}")

    if not frames:
        return pd.DataFrame(columns=["date"])

    result = frames[0]
    for f in frames[1:]:
        result = result.merge(f, on="date", how="outer")
    result = result.sort_values("date").reset_index(drop=True)

    # Abgeleitete Spalten
    if "eurusd" in result.columns and "brent" in result.columns:
        result["brent_eur_bbl"] = (result["brent"] / result["eurusd"]).round(2)
    if "eurusd" in result.columns and "heating_oil" in result.columns:
        # HO=F: USD/gallon → EUR/Liter
        result["heizoel_eur_liter"] = (
            result["heating_oil"] / result["eurusd"] / C.HEATING_OIL_GALLON_TO_LITER
        ).round(3)
    if "ttf" in result.columns:
        result["ttf_ct_kwh"] = (result["ttf"] / 10).round(3)

    return result


# ── 3. Tankerkönig ─────────────────────────────────────────────────

def fetch_tankerkoenig(api_key: str) -> dict | None:
    if not api_key or api_key == "123":
        log.warning("Tankerkönig: kein gültiger API-Key")
        return None

    log.info("Tankerkönig: Kraftstoffpreise …")
    all_prices: dict[str, list[float]] = {"e5": [], "e10": [], "diesel": []}

    for lat, lng in C.TANKERKOENIG_CITIES:
        try:
            r = requests.get(C.TANKERKOENIG_URL, params={
                "lat": lat, "lng": lng,
                "rad": C.TANKERKOENIG_RADIUS_KM,
                "sort": "dist", "type": "all",
                "apikey": api_key,
            }, timeout=10)
            data = r.json()
            if not data.get("ok"):
                log.warning(f"  TK Fehler {lat},{lng}: {data.get('message')}")
                continue
            for station in data.get("stations", [])[:C.TANKERKOENIG_STATIONS_PER_CITY]:
                for fuel in all_prices:
                    p = station.get(fuel)
                    if isinstance(p, (int, float)) and 0.8 < p < 4.0:
                        all_prices[fuel].append(p)
        except Exception as exc:
            log.error(f"  TK {lat},{lng}: {exc}")

    if not any(all_prices.values()):
        return None

    result = {}
    for fuel, prices in all_prices.items():
        if prices:
            result[fuel] = round(sum(prices) / len(prices), 3)
    return result


# ── 4. Indexierung auf 100 = 1.1.2026 ─────────────────────────────

def build_indexed(df: pd.DataFrame) -> pd.DataFrame:
    """Alle Preisspalten auf Index 100 = erster verfügbarer Wert ab 1.1.2026 normieren"""
    price_cols = ["strom_eur_mwh", "brent_eur_bbl", "ttf", "heizoel_eur_liter"]
    price_cols = [c for c in price_cols if c in df.columns]

    df_idx = df[["date"] + price_cols].copy()
    df_idx = df_idx.sort_values("date").reset_index(drop=True)

    for col in price_cols:
        base_rows = df_idx[df_idx[col].notna()]
        if base_rows.empty:
            continue
        base_val = base_rows.iloc[0][col]
        if base_val and base_val != 0:
            df_idx[col + "_idx"] = (df_idx[col] / base_val * 100).round(2)

    return df_idx


# ── 5. Fahrzeugvergleich & Heizkosten ─────────────────────────────

def compute_vehicle(fuel: dict | None) -> dict:
    ice  = C.VEHICLE["ice"]
    bev  = C.VEHICLE["bev"]
    budget = C.COMPARISON_BUDGET_EUR
    result = {}

    if fuel and fuel.get(ice["fuel_type"]):
        p = fuel[ice["fuel_type"]]
        cons = ice["consumption_l_100km"]
        result["ice"] = {
            "label": ice["label"],
            "price_per_unit": p, "unit": "EUR/L",
            "km_for_budget": round(budget / p / cons * 100),
            "cost_per_100km": round(p * cons, 2),
        }

    bev_cons = bev["consumption_kwh_100km_real"]
    for key, label, ct in [
        ("bev_home",      "Heimladen",        C.BDEW["electricity_ct_kwh"]),
        ("bev_public_ac", "Öffentlich AC",    C.PUBLIC_CHARGING_AC_CT_KWH),
        ("bev_public_dc", "Schnellladen DC",  C.PUBLIC_CHARGING_DC_CT_KWH),
    ]:
        p = ct / 100
        entry = {
            "label": f"{bev['label']} – {label}",
            "price_per_unit": round(p, 4), "unit": "EUR/kWh",
            "km_for_budget": round(budget / p / bev_cons * 100),
            "cost_per_100km": round(p * bev_cons, 2),
        }
        if "ice" in result:
            entry["savings_pct_vs_ice"] = round(
                (1 - entry["cost_per_100km"] / result["ice"]["cost_per_100km"]) * 100, 1
            )
        result[key] = entry

    return result


def compute_heating() -> dict:
    gas_ct  = C.BDEW["gas_ct_kwh"]
    elec_ct = C.BDEW["electricity_ct_kwh"]
    result  = {}

    for prop_key, prop in C.HEATING.items():
        wkwh = prop["weekly_kwh"]
        result[prop_key] = {"label": prop["label"], "systems": {}}
        for sys_key, sys in C.HEATING_SYSTEMS.items():
            fuel = sys["fuel"]
            if fuel == "gas":
                cost = round(wkwh / sys["efficiency"] * gas_ct / 100, 2)
            elif fuel == "electricity":
                cop = sys.get("cop", sys.get("efficiency", 1.0))
                cost = round(wkwh / cop * elec_ct / 100, 2)
            else:
                cost = None
            result[prop_key]["systems"][sys_key] = {
                "label": sys["label"],
                "weekly_cost_eur": cost,
            }
    return result


# ── Hauptfunktion ──────────────────────────────────────────────────

def main():
    os.makedirs(C.DATA_DIR, exist_ok=True)
    os.makedirs(C.OUTPUT_DIR, exist_ok=True)

    tk_key = os.environ.get("TANKERKOENIG_API_KEY", "")

    # Daten abrufen
    df_strom = fetch_electricity()
    df_yahoo = fetch_yahoo()
    fuel     = fetch_tankerkoenig(tk_key)

    # Zusammenführen
    df = df_strom.copy()
    if not df_yahoo.empty and "date" in df_yahoo.columns:
        df_yahoo["date"] = pd.to_datetime(df_yahoo["date"]).dt.date
        df = df.merge(df_yahoo, on="date", how="outer")
    df = df.sort_values("date").reset_index(drop=True)

    # Tagespreise speichern
    daily_path = Path(C.DATA_DIR) / "daily_prices.csv"
    df.to_csv(daily_path, index=False, float_format="%.4f")
    log.info(f"Tagespreise → {daily_path} ({len(df)} Tage)")

    # Indexierung
    df_idx = build_indexed(df)
    idx_path = Path(C.DATA_DIR) / "indexed.csv"
    df_idx.to_csv(idx_path, index=False, float_format="%.2f")
    log.info(f"Index-CSV   → {idx_path}")

    # Berechnungen
    vehicle = compute_vehicle(fuel)
    heating = compute_heating()

    # latest.json
    latest = {
        "meta": {
            "generated": TODAY.isoformat(),
            "data_from": START_DATE.isoformat(),
            "data_to":   YESTERDAY.isoformat(),
        },
        "latest_day": {
            col: (df[col].dropna().iloc[-1] if col in df.columns and df[col].notna().any() else None)
            for col in ["strom_eur_mwh", "brent_eur_bbl", "ttf", "ttf_ct_kwh",
                        "heizoel_eur_liter"]
        },
        "fuel_prices":        fuel,
        "vehicle_comparison": vehicle,
        "heating_costs":      heating,
        "reference": {
            "bdew_electricity_ct_kwh":   C.BDEW["electricity_ct_kwh"],
            "bdew_gas_ct_kwh":           C.BDEW["gas_ct_kwh"],
            "bdew_reference_period":     C.BDEW["reference_period"],
            "public_charging_ac_ct_kwh": C.PUBLIC_CHARGING_AC_CT_KWH,
            "public_charging_dc_ct_kwh": C.PUBLIC_CHARGING_DC_CT_KWH,
            "index_base_date":           START_DATE.isoformat(),
            "index_base_value":          100,
        },
    }

    # Floats aus numpy konvertieren
    def to_python(obj):
        if hasattr(obj, "item"):
            return obj.item()
        if isinstance(obj, dict):
            return {k: to_python(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [to_python(v) for v in obj]
        return obj

    latest = to_python(latest)

    latest_path = Path(C.DATA_DIR) / "latest.json"
    with open(latest_path, "w", encoding="utf-8") as f:
        json.dump(latest, f, ensure_ascii=False, indent=2)
    log.info(f"latest.json → {latest_path}")
    log.info("✓ Datenabruf abgeschlossen")
    return latest


if __name__ == "__main__":
    main()
