"""
fetch_prices.py – Energiepreisdaten Deutschland ab 1.1.2026

Ausgabe data/daily_prices.csv:
  date, strom_eur_mwh, brent_eur_bbl, ttf_eur_mwh, coal_usd_t, heizoel_eur_liter, eurusd
  strom_idx, brent_idx, ttf_idx, coal_idx, heizoel_idx
  (Index 100 = erster Handelstag ab 1.1.2026 je Spalte)

data/latest.json: aktuelle Wochenwerte für Newsletter-Tabelle
"""

import os, json, logging, requests
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf

import sys
sys.path.insert(0, str(Path(__file__).parent))
import config as C

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s %(message)s")
log = logging.getLogger(__name__)

START_DATE  = date(2026, 1, 1)
BASE_DATE   = date(2026, 1, 1)   # Index 100 = erster Handelstag ab diesem Datum
TODAY       = date.today()
ROOT        = Path(__file__).parent.parent
OILPRICE_BASE = "https://api.oilpriceapi.com/v1"


# ── Hilfsfunktionen ────────────────────────────────────────────────

def yf_close(df) -> pd.Series:
    if df.empty:
        return pd.Series(dtype=float)
    close = df["Close"]
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    return close.squeeze().dropna()


def oilprice_historical(api_key: str, code: str) -> pd.Series:
    url = f"{OILPRICE_BASE}/prices/historical"
    try:
        r = requests.get(url,
            params={"by_code": code, "start_at": START_DATE.isoformat(),
                    "end_at": TODAY.isoformat(), "interval": "daily"},
            headers={"Authorization": f"Token {api_key}"}, timeout=20)
        r.raise_for_status()
        prices = r.json().get("data", {}).get("prices", [])
        if not prices:
            return pd.Series(dtype=float)
        df = pd.DataFrame(prices)
        df["date"] = pd.to_datetime(df["created_at"]).dt.date
        daily = df.groupby("date")["price"].mean()
        log.info(f"  oilprice {code}: {len(daily)} Tage")
        return daily
    except Exception as e:
        log.error(f"  oilprice {code}: {e}")
        return pd.Series(dtype=float)


# ── 1. Strom Day-Ahead ─────────────────────────────────────────────

def fetch_electricity() -> pd.Series:
    log.info("Energy-Charts: Strom Day-Ahead DE-LU …")
    r = requests.get("https://api.energy-charts.info/price", params={
        "bzn": "DE-LU",
        "start": START_DATE.isoformat(),
        "end":   TODAY.isoformat(),
    }, timeout=30)
    r.raise_for_status()
    raw = r.json()
    df = pd.DataFrame({"ts": raw["unix_seconds"], "price": raw["price"]})
    df["date"] = (pd.to_datetime(df["ts"], unit="s", utc=True)
                  .dt.tz_convert("Europe/Berlin").dt.date)
    daily = df.dropna(subset=["price"]).groupby("date")["price"].mean().round(2)
    log.info(f"  {len(daily)} Tage")
    return daily.rename("strom_eur_mwh")


# ── 2. Rohstoffe ───────────────────────────────────────────────────

def fetch_commodities(oilprice_key: str) -> pd.DataFrame:
    log.info("Yahoo Finance: Rohstoffe …")
    frames = {}

    for name, ticker in [("brent","BZ=F"), ("ttf","TTF=F"),
                          ("heating_oil","HO=F"), ("eurusd","EURUSD=X")]:
        try:
            raw = yf.download(ticker, start=START_DATE.isoformat(),
                              end=TODAY.isoformat(), progress=False, auto_adjust=True)
            s = yf_close(raw)
            if s.empty:
                log.warning(f"  {name}: keine Daten")
                continue
            s.index = pd.to_datetime(s.index).date
            frames[name] = s
            log.info(f"  {name}: {len(s)} Tage")
        except Exception as e:
            log.error(f"  {name}: {e}")

    # Kohle: oilpriceapi primär, ^COAL als Fallback
    coal = pd.Series(dtype=float)
    if oilprice_key:
        coal = oilprice_historical(oilprice_key, "COAL_USD")
    if coal.empty:
        try:
            raw = yf.download("^COAL", start=START_DATE.isoformat(),
                              end=TODAY.isoformat(), progress=False, auto_adjust=True)
            s = yf_close(raw)
            if not s.empty:
                s.index = pd.to_datetime(s.index).date
                coal = s
                log.info(f"  coal (^COAL): {len(coal)} Tage")
        except Exception as e:
            log.error(f"  ^COAL: {e}")
    if not coal.empty:
        frames["coal_usd_t"] = coal

    if not frames:
        return pd.DataFrame()

    df = pd.DataFrame(frames)
    df.index.name = "date"

    # EUR-Umrechnungen
    eurusd = df["eurusd"] if "eurusd" in df.columns else pd.Series(1.10, index=df.index)
    if "brent" in df.columns:
        df["brent_eur_bbl"] = (df["brent"] / eurusd).round(2)
    if "heating_oil" in df.columns:
        df["heizoel_eur_liter"] = (df["heating_oil"] / eurusd / C.HEATING_OIL_GALLON_TO_LITER).round(3)
    if "ttf" in df.columns:
        df["ttf_eur_mwh"] = df["ttf"].round(2)
        df["ttf_ct_kwh"]  = (df["ttf"] / 10).round(3)

    return df


# ── 3. Index berechnen und in CSV schreiben ────────────────────────

def build_daily_csv(strom: pd.Series, commodities: pd.DataFrame) -> pd.DataFrame:
    """
    Merged alle Daten, berechnet Index 100 = erster Handelstag ab BASE_DATE,
    speichert Rohpreise + _idx Spalten in eine CSV.
    """
    # Zusammenführen
    df = strom.to_frame()
    if not commodities.empty:
        df = df.join(commodities, how="outer")
    df = df.sort_index()
    df.index = pd.to_datetime(df.index)

    # Indexspalten berechnen
    price_cols = {
        "strom_eur_mwh":    "strom_idx",
        "brent_eur_bbl":    "brent_idx",
        "ttf_eur_mwh":      "ttf_idx",
        "coal_usd_t":       "coal_idx",
        "heizoel_eur_liter":"heizoel_idx",
    }

    for price_col, idx_col in price_cols.items():
        if price_col not in df.columns:
            continue
        s = df[price_col].dropna()
        # Basiswert: erster Wert ab BASE_DATE
        candidates = s[s.index >= pd.Timestamp(BASE_DATE)]
        if candidates.empty:
            continue
        base_val = candidates.iloc[0]
        if base_val and base_val != 0:
            df[idx_col] = (df[price_col] / base_val * 100).round(2)
            log.info(f"  Index {idx_col}: Basis {candidates.index[0].date()} = {base_val:.3f}")

    df.index.name = "date"
    return df


# ── 4. Tankerkönig ─────────────────────────────────────────────────

def fetch_tankerkoenig(api_key: str) -> dict | None:
    if not api_key or api_key == "123":
        log.warning("Tankerkönig: kein gültiger Key")
        return None
    log.info("Tankerkönig: Kraftstoffpreise …")
    all_prices: dict[str, list] = {"e5": [], "e10": [], "diesel": []}
    for lat, lng in C.TANKERKOENIG_CITIES:
        try:
            r = requests.get(C.TANKERKOENIG_URL, params={
                "lat": lat, "lng": lng, "rad": C.TANKERKOENIG_RADIUS_KM,
                "sort": "dist", "type": "all", "apikey": api_key,
            }, timeout=10)
            data = r.json()
            if not data.get("ok"):
                continue
            for st in data.get("stations", [])[:C.TANKERKOENIG_STATIONS_PER_CITY]:
                for fuel in all_prices:
                    p = st.get(fuel)
                    if isinstance(p, (int, float)) and 0.8 < p < 4.0:
                        all_prices[fuel].append(p)
        except Exception as e:
            log.error(f"  TK {lat},{lng}: {e}")
    if not any(all_prices.values()):
        return None
    return {k: round(sum(v)/len(v), 3) for k, v in all_prices.items() if v}


# ── 5. Wochendurchschnitt für Newsletter-Tabelle ───────────────────

def current_week_summary(df: pd.DataFrame) -> dict:
    """Letzte abgeschlossene Woche (Mo–Fr) mit validen Börsendaten"""
    bdays = df[df.index.weekday < 5].copy()
    bdays["kw_label"] = bdays.index.to_series().apply(
        lambda d: f"{d.isocalendar().year}-KW{d.isocalendar().week:02d}"
    )
    agg_cols = [c for c in ["strom_eur_mwh", "brent_eur_bbl", "ttf_eur_mwh",
                             "ttf_ct_kwh", "coal_usd_t", "heizoel_eur_liter"]
                if c in bdays.columns]
    weekly = bdays.groupby("kw_label")[agg_cols].mean().round(3)
    # Letzte Woche mit Börsendaten
    check_cols = [c for c in ["brent_eur_bbl", "ttf_eur_mwh"] if c in weekly.columns]
    valid = weekly.dropna(subset=check_cols, how="all") if check_cols else weekly
    if valid.empty:
        return {}
    row = valid.iloc[-1].to_dict()
    row["kw_label"] = valid.index[-1]
    return row


# ── 6. Fahrzeug & Heizung ──────────────────────────────────────────

def compute_vehicle(fuel: dict | None) -> dict:
    ice = C.VEHICLE["ice"]
    bev = C.VEHICLE["bev"]
    result = {}
    if fuel and fuel.get(ice["fuel_type"]):
        p = fuel[ice["fuel_type"]]
        cons = ice["consumption_l_100km"]
        result["ice"] = {
            "label": "Benziner", "price_label": f"{p:.2f} €/L",
            "km_for_budget": round(C.COMPARISON_BUDGET_EUR / p / cons * 100),
            "cost_per_100km": round(p * cons, 2),
        }
    bev_cons = bev["consumption_kwh_100km_real"]
    for key, label, ct in [
        ("bev_home",      "Heimladen",       C.BDEW["electricity_ct_kwh"]),
        ("bev_public_ac", "Öffentlich AC",   C.PUBLIC_CHARGING_AC_CT_KWH),
        ("bev_public_dc", "Schnellladen DC", C.PUBLIC_CHARGING_DC_CT_KWH),
    ]:
        p = ct / 100
        entry = {
            "label": label, "price_label": f"{ct:.0f} ct/kWh",
            "km_for_budget": round(C.COMPARISON_BUDGET_EUR / p / bev_cons * 100),
            "cost_per_100km": round(p * bev_cons, 2),
        }
        if "ice" in result:
            entry["savings_pct"] = round(
                (1 - entry["cost_per_100km"] / result["ice"]["cost_per_100km"]) * 100, 1)
        result[key] = entry
    return result


def compute_heating() -> dict:
    gas_ct = C.BDEW["gas_ct_kwh"]
    elec_ct = C.BDEW["electricity_ct_kwh"]
    result = {}
    for prop_key, prop in C.HEATING.items():
        wkwh = prop["weekly_kwh"]
        result[prop_key] = {"label": prop["label"], "systems": {}}
        for sys_key, sys in C.HEATING_SYSTEMS.items():
            if sys_key == "direct_electric":
                continue
            fuel = sys["fuel"]
            cost = None
            if fuel == "gas":
                cost = round(wkwh / sys["efficiency"] * gas_ct / 100, 2)
            elif fuel == "electricity":
                cop = sys.get("cop", sys.get("efficiency", 1.0))
                cost = round(wkwh / cop * elec_ct / 100, 2)
            result[prop_key]["systems"][sys_key] = {
                "label": sys["label"], "weekly_cost_eur": cost}
    return result


# ── Hauptfunktion ──────────────────────────────────────────────────

def main():
    os.makedirs(ROOT / C.DATA_DIR, exist_ok=True)
    os.makedirs(ROOT / C.OUTPUT_DIR, exist_ok=True)

    tk_key       = os.environ.get("TANKERKOENIG_API_KEY", "")
    oilprice_key = os.environ.get("OILPRICE_API", "")

    strom      = fetch_electricity()
    commodities = fetch_commodities(oilprice_key)
    fuel        = fetch_tankerkoenig(tk_key)

    # Alles in eine CSV: Rohpreise + Index
    df = build_daily_csv(strom, commodities)
    daily_path = ROOT / C.DATA_DIR / "daily_prices.csv"
    df.to_csv(daily_path, float_format="%.4f")
    log.info(f"daily_prices.csv → {len(df)} Tage, {len(df.columns)} Spalten")

    # Wochendurchschnitt
    cur_week = current_week_summary(df)
    log.info(f"Aktuelle Woche: {cur_week.get('kw_label', '?')}")

    def to_py(obj):
        if isinstance(obj, float) and obj != obj: return None
        if hasattr(obj, "item"): return obj.item()
        if isinstance(obj, dict): return {k: to_py(v) for k, v in obj.items()}
        if isinstance(obj, list): return [to_py(v) for v in obj]
        return obj

    latest = to_py({
        "meta": {
            "generated":    TODAY.isoformat(),
            "current_week": cur_week.get("kw_label", ""),
            "base_date":    BASE_DATE.isoformat(),
        },
        "current_week":     cur_week,
        "fuel_prices":      fuel,
        "vehicle_comparison": compute_vehicle(fuel),
        "heating_costs":    compute_heating(),
        "reference": {
            "bdew_electricity_ct_kwh":   C.BDEW["electricity_ct_kwh"],
            "bdew_gas_ct_kwh":           C.BDEW["gas_ct_kwh"],
            "bdew_reference_period":     C.BDEW["reference_period"],
            "public_charging_ac_ct_kwh": C.PUBLIC_CHARGING_AC_CT_KWH,
            "public_charging_dc_ct_kwh": C.PUBLIC_CHARGING_DC_CT_KWH,
        },
    })

    latest_path = ROOT / C.DATA_DIR / "latest.json"
    with open(latest_path, "w", encoding="utf-8") as f:
        json.dump(latest, f, ensure_ascii=False, indent=2)
    log.info("✓ Datenabruf abgeschlossen")
    return latest


if __name__ == "__main__":
    main()
