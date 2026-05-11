"""
fetch_prices.py – Energiepreisdaten für Deutschland

Quellen:
  - Energy-Charts API (Fraunhofer ISE)  → Day-Ahead-Strom DE-LU
  - Yahoo Finance (yfinance)            → Brent, TTF, Coal API2, Heizöl-Futures, EUR/USD
  - Tankerkönig API                     → Bundesdurchschnitt Kraftstoffpreise

Ausgabe:
  - data/weekly_YYYY-WW.json   (aktuelle Woche, vollständige Rohdaten)
  - data/historical.csv        (wöchentliche Zusammenfassung, kumuliert)
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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Kalenderwoche berechnen ────────────────────────────────────────
TODAY = date.today()
WEEK_START = TODAY - timedelta(days=TODAY.weekday() + 7)   # letzter Montag
WEEK_END   = TODAY - timedelta(days=TODAY.weekday() + 1)   # letzter Sonntag
ISO_WEEK   = WEEK_START.isocalendar()
WEEK_LABEL = f"{ISO_WEEK.year}-KW{ISO_WEEK.week:02d}"

log.info(f"Datenabruf für Woche {WEEK_LABEL}  ({WEEK_START} – {WEEK_END})")


# ── 1. Day-Ahead-Strom von Energy-Charts ──────────────────────────

def fetch_electricity() -> dict:
    log.info("Energy-Charts: Day-Ahead-Strom DE-LU …")
    url = "https://api.energy-charts.info/price"
    r = requests.get(
        url,
        params={"bzn": "DE-LU", "start": WEEK_START.isoformat(), "end": WEEK_END.isoformat()},
        timeout=30,
    )
    r.raise_for_status()
    raw = r.json()

    df = pd.DataFrame({"ts": raw["unix_seconds"], "price": raw["price"]})
    df["datetime"] = pd.to_datetime(df["ts"], unit="s", utc=True).dt.tz_convert("Europe/Berlin")
    df["date"] = df["datetime"].dt.date
    df = df.dropna(subset=["price"])

    daily = df.groupby("date")["price"].agg(["mean", "min", "max"])
    result = {
        "source": "Energy-Charts API (Fraunhofer ISE)",
        "unit": "EUR/MWh",
        "week_avg": round(float(daily["mean"].mean()), 2),
        "week_min": round(float(df["price"].min()), 2),
        "week_max": round(float(df["price"].max()), 2),
        "daily": {
            str(d): {
                "avg": round(float(row["mean"]), 2),
                "min": round(float(row["min"]), 2),
                "max": round(float(row["max"]), 2),
            }
            for d, row in daily.iterrows()
        },
    }
    log.info(f"  Strom Ø {result['week_avg']} EUR/MWh")
    return result


# ── 2. Yahoo Finance: Rohstoffe ────────────────────────────────────

def fetch_yahoo() -> dict:
    log.info("Yahoo Finance: Rohstoff-Futures …")
    start_str = (WEEK_START - timedelta(days=7)).isoformat()
    end_str   = (WEEK_END + timedelta(days=2)).isoformat()

    results = {}
    for name, ticker in C.YAHOO_TICKERS.items():
        try:
            df = yf.download(ticker, start=start_str, end=end_str, progress=False, auto_adjust=True)
            if df.empty:
                log.warning(f"  {name} ({ticker}): keine Daten")
                continue
            # Nur letzte Woche (Mo–So), Fallback auf letzte 5 Handelstage
            week_df = df.loc[WEEK_START.isoformat():WEEK_END.isoformat()]
            if week_df.empty:
                log.warning(f"  {name}: Woche ohne Daten, nutze letzte Handelstage")
                week_df = df.tail(5)

            close = week_df["Close"].dropna()
            results[name] = {
                "ticker": ticker,
                "avg": round(float(close.mean()), 4),
                "min": round(float(close.min()), 4),
                "max": round(float(close.max()), 4),
                "last": round(float(close.iloc[-1]), 4),
            }
            log.info(f"  {name}: Ø {results[name]['avg']:.3f}")
        except Exception as exc:
            log.error(f"  {name} ({ticker}): {exc}")

    # ── Abgeleitete Größen ────────────────────────────────────────
    eurusd = results.get("eurusd", {}).get("avg", 1.10)

    # Brent: USD/bbl → EUR/bbl & EUR/MWh
    if "brent" in results:
        brent_usd_bbl = results["brent"]["avg"]
        results["brent"]["avg_eur_bbl"] = round(brent_usd_bbl / eurusd, 2)
        # 1 bbl ≈ 1.628 MWh (Rohöl)
        results["brent"]["avg_eur_mwh"] = round(brent_usd_bbl / eurusd / 1.628, 2)

    # Coal API2: USD/t → EUR/t & EUR/MWh (Heizwert ~6.7 MWh/t Steinkohle)
    if "coal" in results:
        coal_usd_t = results["coal"]["avg"]
        results["coal"]["avg_eur_t"] = round(coal_usd_t / eurusd, 2)
        results["coal"]["avg_eur_mwh"] = round(coal_usd_t / eurusd / 6.7, 2)

    # Heizöl: USD/gallon → EUR/Liter
    if "heating_oil" in results:
        ho_usd_gal = results["heating_oil"]["avg"]
        results["heating_oil"]["avg_eur_liter"] = round(
            ho_usd_gal / eurusd / C.HEATING_OIL_GALLON_TO_LITER, 3
        )
        # Retail-Aufschlag DE ~+0.12 EUR/L (Steuern, Lieferung)
        results["heating_oil"]["retail_est_eur_liter"] = round(
            results["heating_oil"]["avg_eur_liter"] + 0.12, 3
        )
        results["heating_oil"]["retail_note"] = (
            "Futures-Proxy (NY Harbor ULSD) + ~0.12 EUR/L Aufschlag. "
            "Aktuelle DE-Verbraucherpreise: BAFA / heizoel.de"
        )

    # TTF: bereits EUR/MWh, ggf. in ct/kWh umrechnen
    if "ttf" in results:
        results["ttf"]["avg_ct_kwh"] = round(results["ttf"]["avg"] / 10, 3)

    return results


# ── 3. Tankerkönig: Kraftstoffpreise ─────────────────────────────

def fetch_tankerkoenig(api_key: str) -> dict | None:
    if not api_key:
        log.warning("Tankerkönig: kein API-Key gesetzt (Secret TANKERKOENIG_API_KEY), übersprungen")
        return None

    log.info("Tankerkönig: Kraftstoffpreise DE …")
    all_prices: dict[str, list[float]] = {"e5": [], "e10": [], "diesel": []}

    for lat, lng in C.TANKERKOENIG_CITIES:
        params = {
            "lat": lat, "lng": lng,
            "rad": C.TANKERKOENIG_RADIUS_KM,
            "sort": "dist",
            "type": "all",
            "apikey": api_key,
        }
        try:
            r = requests.get(C.TANKERKOENIG_URL, params=params, timeout=10)
            data = r.json()
            if not data.get("ok"):
                log.warning(f"  Tankerkönig Fehler bei {lat},{lng}: {data.get('message')}")
                continue
            for station in data.get("stations", [])[:C.TANKERKOENIG_STATIONS_PER_CITY]:
                for fuel in all_prices:
                    price = station.get(fuel)
                    if isinstance(price, (int, float)) and 0.8 < price < 4.0:
                        all_prices[fuel].append(price)
        except Exception as exc:
            log.error(f"  Tankerkönig {lat},{lng}: {exc}")

    if not any(all_prices.values()):
        log.error("Tankerkönig: keine validen Preise erhalten")
        return None

    result = {
        "source": "Tankerkönig / MTS-K (Bundesdurchschnitt aus 7 Städten)",
        "unit": "EUR/Liter",
    }
    for fuel, prices in all_prices.items():
        if prices:
            result[fuel] = round(sum(prices) / len(prices), 3)
            result[f"{fuel}_n"] = len(prices)
            log.info(f"  {fuel}: Ø {result[fuel]:.3f} EUR/L (n={len(prices)})")

    return result


# ── 4. Fahrzeug-Vergleich ─────────────────────────────────────────

def compute_vehicle_comparison(fuel: dict | None, elec_home_ct: float) -> dict:
    """Opel Astra ICE vs BEV – Reichweite und Kosten"""
    log.info("Berechne Fahrzeugvergleich …")
    ice_cfg = C.VEHICLE["ice"]
    bev_cfg = C.VEHICLE["bev"]
    budget  = C.COMPARISON_BUDGET_EUR
    dist    = C.COMPARISON_DISTANCE_KM

    results: dict = {}

    # ICE
    if fuel and fuel.get(ice_cfg["fuel_type"]):
        p = fuel[ice_cfg["fuel_type"]]
        cons = ice_cfg["consumption_l_100km"]
        results["ice"] = {
            "label":            ice_cfg["label"],
            "price_per_unit":   p,
            "unit":             "EUR/L",
            "km_for_budget":    round(budget / p / cons * 100),
            "cost_per_100km":   round(p * cons, 2),
        }

    bev_cons = bev_cfg["consumption_kwh_100km_real"]

    # BEV – Heimladen (BDEW-Haushaltsstrompreis)
    p_home = elec_home_ct / 100
    results["bev_home"] = {
        "label":          bev_cfg["label"] + " – Heimladen",
        "price_per_unit": round(p_home, 4),
        "unit":           "EUR/kWh",
        "km_for_budget":  round(budget / p_home / bev_cons * 100),
        "cost_per_100km": round(p_home * bev_cons, 2),
        "source":         f"BDEW Ø {C.BDEW['electricity_ct_kwh']} ct/kWh ({C.BDEW['reference_period']})",
    }

    # BEV – öffentlich AC
    p_ac = C.PUBLIC_CHARGING_AC_CT_KWH / 100
    results["bev_public_ac"] = {
        "label":          bev_cfg["label"] + " – Öffentlich AC",
        "price_per_unit": p_ac,
        "unit":           "EUR/kWh",
        "km_for_budget":  round(budget / p_ac / bev_cons * 100),
        "cost_per_100km": round(p_ac * bev_cons, 2),
        "source":         C.PUBLIC_CHARGING_SOURCE,
    }

    # BEV – DC Schnellladen
    p_dc = C.PUBLIC_CHARGING_DC_CT_KWH / 100
    results["bev_public_dc"] = {
        "label":          bev_cfg["label"] + " – Schnellladen DC",
        "price_per_unit": p_dc,
        "unit":           "EUR/kWh",
        "km_for_budget":  round(budget / p_dc / bev_cons * 100),
        "cost_per_100km": round(p_dc * bev_cons, 2),
        "source":         C.PUBLIC_CHARGING_SOURCE,
    }

    # Sparfaktor vs ICE
    if "ice" in results:
        for key in ["bev_home", "bev_public_ac", "bev_public_dc"]:
            ice_cost = results["ice"]["cost_per_100km"]
            bev_cost = results[key]["cost_per_100km"]
            if ice_cost > 0:
                results[key]["savings_pct_vs_ice"] = round((1 - bev_cost / ice_cost) * 100, 1)

    return results


# ── 5. Heizkosten ─────────────────────────────────────────────────

def compute_heating_costs(yahoo: dict) -> dict:
    """Wöchentliche Heizkosten für Haus 150 m² und Wohnung 100 m²"""
    log.info("Berechne Heizkosten …")

    # Preise zusammenstellen
    gas_ct_kwh  = C.BDEW["gas_ct_kwh"]   # Haushalt
    elec_ct_kwh = C.BDEW["electricity_ct_kwh"]
    oil_eur_l   = yahoo.get("heating_oil", {}).get("retail_est_eur_liter")

    results: dict = {}
    for prop_key, prop in C.HEATING.items():
        weekly_kwh = prop["weekly_kwh"]
        results[prop_key] = {"label": prop["label"], "systems": {}}

        for sys_key, sys in C.HEATING_SYSTEMS.items():
            fuel = sys["fuel"]
            entry: dict = {"label": sys["label"]}

            if fuel == "gas":
                kwh_input = weekly_kwh / sys["efficiency"]
                entry["weekly_cost_eur"] = round(kwh_input * gas_ct_kwh / 100, 2)
                entry["price_basis"] = f"{gas_ct_kwh} ct/kWh (BDEW {C.BDEW['reference_period']})"

            elif fuel == "oil":
                if oil_eur_l is None:
                    entry["weekly_cost_eur"] = None
                    entry["note"] = "Heizölpreis nicht verfügbar"
                else:
                    kwh_per_l = sys["kwh_per_liter"]
                    liters = (weekly_kwh / sys["efficiency"]) / kwh_per_l
                    entry["weekly_cost_eur"] = round(liters * oil_eur_l, 2)
                    entry["price_basis"] = f"{oil_eur_l:.3f} EUR/L (Futures-Proxy)"

            elif fuel == "electricity":
                cop_or_eff = sys.get("cop", sys.get("efficiency", 1.0))
                kwh_input  = weekly_kwh / cop_or_eff
                entry["weekly_cost_eur"] = round(kwh_input * elec_ct_kwh / 100, 2)
                entry["price_basis"] = f"{elec_ct_kwh} ct/kWh (BDEW {C.BDEW['reference_period']})"

            results[prop_key]["systems"][sys_key] = entry

    return results


# ── Hauptfunktion ──────────────────────────────────────────────────

def main():
    os.makedirs(C.DATA_DIR, exist_ok=True)
    os.makedirs(C.OUTPUT_DIR, exist_ok=True)

    api_key_tk = os.environ.get("TANKERKOENIG_API_KEY", "")

    # Daten abrufen
    electricity = fetch_electricity()
    yahoo       = fetch_yahoo()
    fuel        = fetch_tankerkoenig(api_key_tk)

    # Berechnungen
    vehicle = compute_vehicle_comparison(fuel, C.BDEW["electricity_ct_kwh"])
    heating = compute_heating_costs(yahoo)

    # Wochendaten zusammenstellen
    week_data = {
        "meta": {
            "week":       WEEK_LABEL,
            "week_start": WEEK_START.isoformat(),
            "week_end":   WEEK_END.isoformat(),
            "generated":  date.today().isoformat(),
        },
        "electricity_dayahead": electricity,
        "commodities":          yahoo,
        "fuel_prices":          fuel,
        "vehicle_comparison":   vehicle,
        "heating_costs":        heating,
        "reference": {
            "bdew_electricity_ct_kwh":    C.BDEW["electricity_ct_kwh"],
            "bdew_gas_ct_kwh":            C.BDEW["gas_ct_kwh"],
            "bdew_reference_period":      C.BDEW["reference_period"],
            "public_charging_ac_ct_kwh":  C.PUBLIC_CHARGING_AC_CT_KWH,
            "public_charging_dc_ct_kwh":  C.PUBLIC_CHARGING_DC_CT_KWH,
        },
    }

    # JSON speichern
    json_path = Path(C.DATA_DIR) / f"weekly_{WEEK_LABEL}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(week_data, f, ensure_ascii=False, indent=2)
    log.info(f"JSON gespeichert → {json_path}")

    # Historische CSV aktualisieren
    hist_path = Path(C.DATA_DIR) / "historical.csv"
    row = {
        "week":                       WEEK_LABEL,
        "week_start":                 WEEK_START.isoformat(),
        "elec_dayahead_avg_eur_mwh":  electricity.get("week_avg"),
        "brent_avg_eur_bbl":          yahoo.get("brent", {}).get("avg_eur_bbl"),
        "ttf_avg_eur_mwh":            yahoo.get("ttf", {}).get("avg"),
        "ttf_avg_ct_kwh":             yahoo.get("ttf", {}).get("avg_ct_kwh"),
        "coal_api2_avg_eur_t":        yahoo.get("coal", {}).get("avg_eur_t"),
        "coal_api2_avg_eur_mwh":      yahoo.get("coal", {}).get("avg_eur_mwh"),
        "heating_oil_retail_eur_l":   yahoo.get("heating_oil", {}).get("retail_est_eur_liter"),
        "fuel_e5_eur_l":              fuel.get("e5") if fuel else None,
        "fuel_e10_eur_l":             fuel.get("e10") if fuel else None,
        "fuel_diesel_eur_l":          fuel.get("diesel") if fuel else None,
        "eurusd":                     yahoo.get("eurusd", {}).get("avg"),
        "bdew_elec_ct_kwh":           C.BDEW["electricity_ct_kwh"],
        "bdew_gas_ct_kwh":            C.BDEW["gas_ct_kwh"],
        "cost_100km_ice_eur":         vehicle.get("ice", {}).get("cost_per_100km"),
        "cost_100km_bev_home_eur":    vehicle.get("bev_home", {}).get("cost_per_100km"),
        "cost_100km_bev_ac_eur":      vehicle.get("bev_public_ac", {}).get("cost_per_100km"),
        "cost_100km_bev_dc_eur":      vehicle.get("bev_public_dc", {}).get("cost_per_100km"),
        "heat_haus_gas_eur_week":     heating.get("haus_150qm", {}).get("systems", {}).get("gas_boiler", {}).get("weekly_cost_eur"),
        "heat_haus_oil_eur_week":     heating.get("haus_150qm", {}).get("systems", {}).get("oil_boiler", {}).get("weekly_cost_eur"),
        "heat_haus_heatpump_eur_week":heating.get("haus_150qm", {}).get("systems", {}).get("heat_pump", {}).get("weekly_cost_eur"),
    }

    new_row_df = pd.DataFrame([row])
    if hist_path.exists():
        hist_df = pd.read_csv(hist_path)
        # Woche ersetzen falls bereits vorhanden
        hist_df = hist_df[hist_df["week"] != WEEK_LABEL]
        hist_df = pd.concat([hist_df, new_row_df], ignore_index=True)
    else:
        hist_df = new_row_df

    hist_df = hist_df.sort_values("week_start").reset_index(drop=True)
    hist_df.to_csv(hist_path, index=False, float_format="%.4f")
    log.info(f"CSV aktualisiert → {hist_path} ({len(hist_df)} Wochen)")

    # Wochendaten auch als latest.json für Webseite
    latest_path = Path(C.DATA_DIR) / "latest.json"
    with open(latest_path, "w", encoding="utf-8") as f:
        json.dump(week_data, f, ensure_ascii=False, indent=2)
    log.info(f"latest.json → {latest_path}")

    log.info("✓ Datenabruf abgeschlossen")
    return week_data


if __name__ == "__main__":
    main()
