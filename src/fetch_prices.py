"""
fetch_prices.py – Tages- und Wochendaten ab 1.1.2026

Quellen:
  Energy-Charts API  → Strom Day-Ahead DE-LU
  Yahoo Finance      → Brent, TTF, Kohle (MTF=F), Heizöl, EUR/USD
  Tankerkönig        → Kraftstoffpreise DE

Ausgabe:
  data/daily_prices.csv   – Tagespreise
  data/weekly_prices.csv  – Wochendurchschnitte (KW-Basis)
  data/indexed.csv        – Index 100 = erste KW 2026
  data/latest.json        – aktuelle KW für Newsletter
"""

import os, json, logging, requests
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


def yf_close(df, ticker) -> pd.Series:
    if df.empty:
        return pd.Series(dtype=float)
    close = df["Close"]
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    return close.squeeze().dropna()


def fetch_electricity() -> pd.DataFrame:
    log.info("Energy-Charts: Strom Day-Ahead …")
    r = requests.get("https://api.energy-charts.info/price", params={
        "bzn": "DE-LU", "start": START_DATE.isoformat(), "end": TODAY.isoformat()
    }, timeout=30)
    r.raise_for_status()
    raw = r.json()
    df = pd.DataFrame({"ts": raw["unix_seconds"], "price": raw["price"]})
    df["date"] = (pd.to_datetime(df["ts"], unit="s", utc=True)
                  .dt.tz_convert("Europe/Berlin").dt.date)
    daily = df.dropna(subset=["price"]).groupby("date")["price"].mean().round(2).reset_index()
    daily.columns = ["date", "strom_eur_mwh"]
    log.info(f"  {len(daily)} Tage")
    return daily


def fetch_yahoo() -> pd.DataFrame:
    log.info("Yahoo Finance: Rohstoffe …")
    # Kohle: MTF=F rollt monatlich – mehrere Ticker probieren
    COAL_TICKERS = ["MTF=F", "MTFM26.NYM", "MTFN26.NYM", "MTFQ26.NYM"]

    tickers = {
        "brent":       ["BZ=F"],
        "ttf":         ["TTF=F"],
        "coal":        COAL_TICKERS,
        "heating_oil": ["HO=F"],
        "eurusd":      ["EURUSD=X"],
    }
    frames = []
    for name, ticker_list in tickers.items():
        if isinstance(ticker_list, str):
            ticker_list = [ticker_list]
        got_data = False
        for ticker in ticker_list:
            try:
                raw = yf.download(ticker, start=START_DATE.isoformat(),
                                  end=TODAY.isoformat(), progress=False, auto_adjust=True)
                close = yf_close(raw, ticker)
                if close.empty:
                    continue
                s = close.copy()
                s.index = pd.to_datetime(s.index).date
                df = s.reset_index()
                df.columns = ["date", name]
                frames.append(df)
                log.info(f"  {name} ({ticker}): {len(df)} Tage")
                got_data = True
                break
            except Exception as e:
                log.warning(f"  {name} ({ticker}): {e}")
        if not got_data:
            log.warning(f"  {name}: alle Ticker ohne Daten – wird übersprungen")

    if not frames:
        return pd.DataFrame(columns=["date"])

    result = frames[0]
    for f in frames[1:]:
        result = result.merge(f, on="date", how="outer")
    result = result.sort_values("date").reset_index(drop=True)

    eurusd = result["eurusd"] if "eurusd" in result.columns else pd.Series(1.10, index=result.index)

    if "brent" in result.columns:
        result["brent_eur_bbl"] = (result["brent"] / eurusd).round(2)
    if "heating_oil" in result.columns:
        result["heizoel_eur_liter"] = (
            result["heating_oil"] / eurusd / C.HEATING_OIL_GALLON_TO_LITER
        ).round(3)
    if "ttf" in result.columns:
        result["ttf_ct_kwh"] = (result["ttf"] / 10).round(3)
    if "coal" in result.columns:
        result["coal_eur_t"] = (result["coal"] / eurusd).round(2)

    return result


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


def to_weekly(df: pd.DataFrame, price_cols: list) -> pd.DataFrame:
    """Tagesdaten → Wochendurchschnitte, KW-Bezeichnung"""
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df["kw"] = df["date"].dt.isocalendar().week.astype(int)
    df["year"] = df["date"].dt.isocalendar().year.astype(int)
    df["kw_label"] = df.apply(lambda r: f"{r['year']}-KW{r['kw']:02d}", axis=1)

    agg = {col: "mean" for col in price_cols if col in df.columns}
    weekly = df.groupby("kw_label").agg(agg).round(3).reset_index()
    weekly = weekly.sort_values("kw_label").reset_index(drop=True)
    return weekly


def build_indexed(weekly: pd.DataFrame, price_cols: list) -> pd.DataFrame:
    idx = weekly[["kw_label"] + [c for c in price_cols if c in weekly.columns]].copy()
    for col in price_cols:
        if col not in idx.columns:
            continue
        base = idx[col].dropna()
        if base.empty:
            continue
        base_val = base.iloc[0]
        if base_val and base_val != 0:
            idx[col + "_idx"] = (idx[col] / base_val * 100).round(1)
    return idx


def compute_vehicle(fuel: dict | None) -> dict:
    ice = C.VEHICLE["ice"]
    bev = C.VEHICLE["bev"]
    budget = C.COMPARISON_BUDGET_EUR
    result = {}

    if fuel and fuel.get(ice["fuel_type"]):
        p = fuel[ice["fuel_type"]]
        cons = ice["consumption_l_100km"]
        result["ice"] = {
            "label": "Benziner", "price_label": f"{p:.2f} €/L",
            "km_for_budget": round(budget / p / cons * 100),
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
            "km_for_budget": round(budget / p / bev_cons * 100),
            "cost_per_100km": round(p * bev_cons, 2),
        }
        if "ice" in result:
            entry["savings_pct"] = round((1 - entry["cost_per_100km"] / result["ice"]["cost_per_100km"]) * 100, 1)
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
            if sys_key == "direct_electric":
                continue  # niemand heizt mit Direktstrom
            fuel = sys["fuel"]
            if fuel == "gas":
                cost = round(wkwh / sys["efficiency"] * gas_ct / 100, 2)
            elif fuel == "electricity":
                cop = sys.get("cop", sys.get("efficiency", 1.0))
                cost = round(wkwh / cop * elec_ct / 100, 2)
            else:
                cost = None
            result[prop_key]["systems"][sys_key] = {"label": sys["label"], "weekly_cost_eur": cost}
    return result


def main():
    os.makedirs(C.DATA_DIR, exist_ok=True)
    os.makedirs(C.OUTPUT_DIR, exist_ok=True)

    tk_key = os.environ.get("TANKERKOENIG_API_KEY", "")

    df_strom = fetch_electricity()
    df_yahoo = fetch_yahoo()
    fuel     = fetch_tankerkoenig(tk_key)

    # Zusammenführen
    df = df_strom.copy()
    if not df_yahoo.empty and "date" in df_yahoo.columns:
        df_yahoo["date"] = pd.to_datetime(df_yahoo["date"]).dt.date
        df = df.merge(df_yahoo, on="date", how="outer")
    df = df.sort_values("date").reset_index(drop=True)
    df.to_csv(Path(C.DATA_DIR) / "daily_prices.csv", index=False, float_format="%.4f")

    # Wochendurchschnitte
    price_cols = ["strom_eur_mwh", "brent_eur_bbl", "ttf", "ttf_ct_kwh",
                  "coal_eur_t", "heizoel_eur_liter"]
    weekly = to_weekly(df, price_cols)
    weekly.to_csv(Path(C.DATA_DIR) / "weekly_prices.csv", index=False, float_format="%.4f")
    log.info(f"Wochendaten → {len(weekly)} Wochen")

    # Index
    idx = build_indexed(weekly, ["strom_eur_mwh", "brent_eur_bbl", "ttf", "coal_eur_t"])
    idx.to_csv(Path(C.DATA_DIR) / "indexed.csv", index=False, float_format="%.1f")

    # Aktuelle KW
    cur = weekly.iloc[-1].to_dict() if not weekly.empty else {}
    vehicle = compute_vehicle(fuel)
    heating = compute_heating()

    def to_py(obj):
        if hasattr(obj, "item"): return obj.item()
        if isinstance(obj, dict): return {k: to_py(v) for k, v in obj.items()}
        if isinstance(obj, list): return [to_py(v) for v in obj]
        return obj

    latest = to_py({
        "meta": {
            "generated": TODAY.isoformat(),
            "current_week": cur.get("kw_label", ""),
        },
        "current_week": cur,
        "fuel_prices": fuel,
        "vehicle_comparison": vehicle,
        "heating_costs": heating,
        "reference": {
            "bdew_electricity_ct_kwh":   C.BDEW["electricity_ct_kwh"],
            "bdew_gas_ct_kwh":           C.BDEW["gas_ct_kwh"],
            "bdew_reference_period":     C.BDEW["reference_period"],
            "public_charging_ac_ct_kwh": C.PUBLIC_CHARGING_AC_CT_KWH,
            "public_charging_dc_ct_kwh": C.PUBLIC_CHARGING_DC_CT_KWH,
        },
    })

    with open(Path(C.DATA_DIR) / "latest.json", "w", encoding="utf-8") as f:
        json.dump(latest, f, ensure_ascii=False, indent=2)
    log.info("✓ Datenabruf abgeschlossen")
    return latest


if __name__ == "__main__":
    main()
