"""
fetch_prices.py – Energiepreisdaten Deutschland ab 1.1.2026

Quellen:
  Energy-Charts API   → Strom Day-Ahead DE-LU (stündlich → Tagesdurchschnitt)
  Yahoo Finance       → Brent, TTF, Heizöl, EUR/USD (Primär)
  oilpriceapi.com     → Kohle API2 CIF ARA (Primär), Rest als Fallback
  Tankerkönig         → Kraftstoffpreise DE

Chart-Daten: Tagesdurchschnitte Mo–Fr, keine Wochenaggregation
Newsletter-Tabelle: letzte abgeschlossene Woche (Mo–Fr Durchschnitt)
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

START_DATE = date(2026, 1, 1)
TODAY      = date.today()
ROOT       = Path(__file__).parent.parent

OILPRICE_BASE = "https://api.oilpriceapi.com/v1"


# ── Hilfsfunktionen ────────────────────────────────────────────────

def yf_close(df) -> pd.Series:
    if df.empty:
        return pd.Series(dtype=float)
    close = df["Close"]
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    return close.squeeze().dropna()


def oilprice_headers(api_key: str) -> dict:
    return {"Authorization": f"Token {api_key}", "Content-Type": "application/json"}


def oilprice_historical(api_key: str, code: str) -> pd.Series:
    """Historische Tagesdaten von oilpriceapi.com ab START_DATE"""
    url = f"{OILPRICE_BASE}/prices/historical"
    params = {
        "by_code": code,
        "start_at": START_DATE.isoformat(),
        "end_at": TODAY.isoformat(),
        "interval": "daily",
    }
    try:
        r = requests.get(url, params=params, headers=oilprice_headers(api_key), timeout=20)
        r.raise_for_status()
        data = r.json()
        prices = data.get("data", {}).get("prices", [])
        if not prices:
            log.warning(f"  oilprice {code}: keine Daten")
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

def fetch_electricity() -> pd.DataFrame:
    log.info("Energy-Charts: Strom Day-Ahead DE-LU …")
    r = requests.get("https://api.energy-charts.info/price", params={
        "bzn": "DE-LU",
        "start": START_DATE.isoformat(),
        "end": TODAY.isoformat(),
    }, timeout=30)
    r.raise_for_status()
    raw = r.json()

    df = pd.DataFrame({"ts": raw["unix_seconds"], "price": raw["price"]})
    df["date"] = (pd.to_datetime(df["ts"], unit="s", utc=True)
                  .dt.tz_convert("Europe/Berlin").dt.date)
    daily = (df.dropna(subset=["price"])
               .groupby("date")["price"].mean().round(2))
    log.info(f"  {len(daily)} Tage (inkl. Wochenenden)")
    return daily.reset_index().rename(columns={"price": "strom_eur_mwh"})


# ── 2. Yahoo Finance ───────────────────────────────────────────────

def fetch_yahoo(oilprice_key: str) -> pd.DataFrame:
    log.info("Yahoo Finance: Rohstoffe …")

    yf_tickers = {
        "brent":       "BZ=F",
        "ttf":         "TTF=F",
        "heating_oil": "HO=F",
        "eurusd":      "EURUSD=X",
    }

    frames = []
    for name, ticker in yf_tickers.items():
        try:
            raw = yf.download(ticker, start=START_DATE.isoformat(),
                              end=TODAY.isoformat(), progress=False, auto_adjust=True)
            close = yf_close(raw)
            if close.empty:
                log.warning(f"  {name} ({ticker}): keine Daten")
                continue
            close.index = pd.to_datetime(close.index).date
            df = close.reset_index()
            df.columns = ["date", name]
            frames.append(df)
            log.info(f"  {name}: {len(df)} Tage (Mo–Fr)")
        except Exception as e:
            log.error(f"  {name} ({ticker}): {e}")

    # Kohle: oilpriceapi.com (API2 CIF ARA) primär
    coal_series = pd.Series(dtype=float)
    if oilprice_key:
        coal_series = oilprice_historical(oilprice_key, "COAL_USD")
    if coal_series.empty:
        log.info("  Kohle: oilprice fehlgeschlagen, versuche ^COAL (Yahoo)")
        try:
            raw = yf.download("^COAL", start=START_DATE.isoformat(),
                              end=TODAY.isoformat(), progress=False, auto_adjust=True)
            coal_series = yf_close(raw)
            coal_series.index = pd.to_datetime(coal_series.index).date
            if not coal_series.empty:
                log.info(f"  coal (^COAL Proxy): {len(coal_series)} Tage")
        except Exception as e:
            log.error(f"  ^COAL: {e}")

    if not coal_series.empty:
        df_coal = coal_series.reset_index()
        df_coal.columns = ["date", "coal_usd_t"]
        frames.append(df_coal)

    if not frames:
        return pd.DataFrame(columns=["date"])

    result = frames[0]
    for f in frames[1:]:
        result = result.merge(f, on="date", how="outer")
    result = result.sort_values("date").reset_index(drop=True)

    # Abgeleitete EUR-Spalten
    eurusd = result.get("eurusd", pd.Series(1.10, index=result.index))
    if "eurusd" in result.columns:
        eurusd = result["eurusd"]

    if "brent" in result.columns:
        result["brent_eur_bbl"] = (result["brent"] / eurusd).round(2)
    if "heating_oil" in result.columns:
        result["heizoel_eur_liter"] = (
            result["heating_oil"] / eurusd / C.HEATING_OIL_GALLON_TO_LITER
        ).round(3)
    if "ttf" in result.columns:
        result["ttf_ct_kwh"] = (result["ttf"] / 10).round(3)
    if "coal_usd_t" in result.columns:
        result["coal_eur_t"] = (result["coal_usd_t"] / eurusd).round(2)

    return result


# ── 3. Tankerkönig ─────────────────────────────────────────────────

def fetch_tankerkoenig(api_key: str) -> dict | None:
    if not api_key or api_key == "123":
        log.warning("Tankerkönig: kein gültiger Key")
        return None
    log.info("Tankerkönig: Kraftstoffpreise …")
    all_prices: dict[str, list] = {"e5": [], "e10": [], "diesel": []}
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


# ── 4. Wochendurchschnitt (für Newsletter-Tabelle) ─────────────────

def last_complete_week(df: pd.DataFrame, price_cols: list) -> dict:
    """Letzter abgeschlossener Mo–Fr Block mit validen Daten"""
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df["weekday"] = df["date"].dt.weekday  # 0=Mo, 4=Fr
    df_bdays = df[df["weekday"] < 5]  # nur Mo–Fr

    df_bdays = df_bdays.copy()
    df_bdays["kw"] = df_bdays["date"].dt.isocalendar().week.astype(int)
    df_bdays["year"] = df_bdays["date"].dt.isocalendar().year.astype(int)
    df_bdays["kw_label"] = df_bdays.apply(
        lambda r: f"{r['year']}-KW{r['kw']:02d}", axis=1
    )

    agg = {col: "mean" for col in price_cols if col in df_bdays.columns}
    weekly = df_bdays.groupby("kw_label").agg(agg).round(3).reset_index()
    weekly = weekly.sort_values("kw_label").reset_index(drop=True)

    # Letzte Woche mit validen Commodity-Daten
    commodity_cols = [c for c in ["brent_eur_bbl", "ttf", "heizoel_eur_liter"]
                      if c in weekly.columns]
    if commodity_cols:
        valid = weekly.dropna(subset=commodity_cols, how="all")
    else:
        valid = weekly

    if valid.empty:
        return {}
    return valid.iloc[-1].to_dict()


# ── 5. Berechnungen ────────────────────────────────────────────────

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
            if sys_key == "direct_electric":
                continue
            fuel = sys["fuel"]
            if fuel == "gas":
                cost = round(wkwh / sys["efficiency"] * gas_ct / 100, 2)
            elif fuel == "electricity":
                cop = sys.get("cop", sys.get("efficiency", 1.0))
                cost = round(wkwh / cop * elec_ct / 100, 2)
            else:
                cost = None
            result[prop_key]["systems"][sys_key] = {
                "label": sys["label"], "weekly_cost_eur": cost
            }
    return result


# ── Hauptfunktion ──────────────────────────────────────────────────

def main():
    os.makedirs(C.DATA_DIR, exist_ok=True)
    os.makedirs(C.OUTPUT_DIR, exist_ok=True)

    tk_key       = os.environ.get("TANKERKOENIG_API_KEY", "")
    oilprice_key = os.environ.get("OILPRICE_API", "")

    # Daten abrufen
    df_strom = fetch_electricity()
    df_comm  = fetch_yahoo(oilprice_key)
    fuel     = fetch_tankerkoenig(tk_key)

    # Zusammenführen (outer join – Strom hat Wochenenden, Börsen nicht)
    df = df_strom.copy()
    if not df_comm.empty and "date" in df_comm.columns:
        df_comm["date"] = pd.to_datetime(df_comm["date"]).dt.date
        df = df.merge(df_comm, on="date", how="outer")
    df = df.sort_values("date").reset_index(drop=True)

    # Tagesdaten speichern (Chart-Basis)
    daily_path = ROOT / C.DATA_DIR / "daily_prices.csv"
    df.to_csv(daily_path, index=False, float_format="%.4f")
    log.info(f"Tagesdaten → {daily_path} ({len(df)} Tage)")

    # Wochendurchschnitt für Newsletter-Tabelle
    price_cols = ["strom_eur_mwh", "brent_eur_bbl", "ttf", "ttf_ct_kwh",
                  "coal_eur_t", "heizoel_eur_liter"]
    cur_week = last_complete_week(df, price_cols)
    log.info(f"Aktuelle Woche: {cur_week.get('kw_label', '?')}")

    # Berechnungen
    vehicle = compute_vehicle(fuel)
    heating = compute_heating()

    def to_py(obj):
        if hasattr(obj, "item"): return obj.item()
        if isinstance(obj, float) and (obj != obj): return None  # NaN → None
        if isinstance(obj, dict): return {k: to_py(v) for k, v in obj.items()}
        if isinstance(obj, list): return [to_py(v) for v in obj]
        return obj

    latest = to_py({
        "meta": {
            "generated": TODAY.isoformat(),
            "current_week": cur_week.get("kw_label", ""),
        },
        "current_week": cur_week,
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

    latest_path = ROOT / C.DATA_DIR / "latest.json"
    with open(latest_path, "w", encoding="utf-8") as f:
        json.dump(latest, f, ensure_ascii=False, indent=2)
    log.info(f"latest.json → {latest_path}")
    log.info("✓ Datenabruf abgeschlossen")
    return latest


if __name__ == "__main__":
    main()
