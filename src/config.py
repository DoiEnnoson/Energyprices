"""
config.py – Zentrale Konfiguration für den Energie-Newsletter
Fahrzeugdaten, Heizreferenzen, BDEW-Preise, API-Endpunkte.
"""

# ── Fahrzeug: Opel Astra ────────────────────────────────────────────
VEHICLE = {
    "name": "Opel Astra",
    "ice": {
        "label": "Astra 1.2 Turbo 130 PS (Benziner)",
        "consumption_l_100km": 6.5,      # realer Verbrauch, WLTP ~5.8 L
        "fuel_type": "e5",
    },
    "bev": {
        "label": "Astra Electric 156 PS",
        "consumption_kwh_100km_wltp": 15.8,
        "consumption_kwh_100km_real": 18.0,  # realer Verbrauch
    },
}

COMPARISON_BUDGET_EUR = 50.0   # „Wieviel km für 50 €?"
COMPARISON_DISTANCE_KM = 100.0  # „Was kostet 100 km?"

# ── Ladepreise (öffentlich) – Verivox-Durchschnitt DE 2025 ─────────
# Keine kostenfreie Live-API verfügbar; Werte werden quartalsweise geprüft.
PUBLIC_CHARGING_AC_CT_KWH = 54.0   # AC-Normalladung Ø Deutschland
PUBLIC_CHARGING_DC_CT_KWH = 64.0   # DC-Schnellladen Ø Deutschland
PUBLIC_CHARGING_SOURCE = "Verivox/BDEW Ø 2025"

# ── BDEW Haushaltspreise (statisch, quartalsweise aktualisieren) ────
BDEW = {
    "electricity_ct_kwh": 39.0,   # Q1 2025 ~39 ct/kWh inkl. MwSt.
    "gas_ct_kwh": 11.5,           # Q1 2025 ~11.5 ct/kWh
    "reference_period": "Q1 2025",
    "source": "BDEW Strompreisanalyse / Bundesnetzagentur Monitoringbericht 2025",
}

# ── Heizung: Jahresbedarf ──────────────────────────────────────────
HEATING = {
    "haus_150qm": {
        "label": "Einfamilienhaus 150 m²",
        "annual_kwh": 15_000,
        "weekly_kwh": 15_000 / 52,
    },
    "wohnung_100qm": {
        "label": "Wohnung 100 m²",
        "annual_kwh": 8_000,
        "weekly_kwh": 8_000 / 52,
    },
}

HEATING_SYSTEMS = {
    "gas_boiler": {
        "label": "Gasheizung",
        "efficiency": 0.87,
        "fuel": "gas",
    },
    "oil_boiler": {
        "label": "Ölheizung",
        "efficiency": 0.85,
        "fuel": "oil",
        "kwh_per_liter": 10.0,
    },
    "heat_pump": {
        "label": "Wärmepumpe (COP 3,5)",
        "cop": 3.5,
        "fuel": "electricity",
    },
    "direct_electric": {
        "label": "Direktstromheizung",
        "efficiency": 1.0,
        "fuel": "electricity",
    },
}

# ── Yahoo Finance Ticker ───────────────────────────────────────────
YAHOO_TICKERS = {
    "brent": "BZ=F",       # Brent Crude Oil Futures, USD/bbl
    "ttf":   "TTF=F",      # TTF Natural Gas Futures, EUR/MWh
    "coal":  "MTF=F",      # Coal API2 CIF ARA (Argus/McCloskey), USD/t – EU-Benchmark
    "heating_oil": "HO=F", # NY Harbor ULSD Futures, USD/gallon – Heizöl-Proxy
    "eurusd": "EURUSD=X",  # EUR/USD Wechselkurs
}

# Heizöl: HO=F ist ULSD in USD/gallon → EUR/Liter
# 1 US gallon = 3.78541 Liter, Wert ÷ EURUSD ÷ 3.78541
HEATING_OIL_GALLON_TO_LITER = 3.78541

# Tankerkönig API (kostenlos, Registrierung nötig)
TANKERKOENIG_URL = "https://creativecommons.tankerkoenig.de/json/list.php"
# Repräsentative Städte für Bundesdurchschnitt
TANKERKOENIG_CITIES = [
    (52.52,  13.40),   # Berlin
    (48.14,  11.58),   # München
    (53.55,   9.99),   # Hamburg
    (51.23,   6.77),   # Düsseldorf
    (50.11,   8.68),   # Frankfurt
    (48.78,   9.18),   # Stuttgart
    (51.05,  13.74),   # Dresden
]
TANKERKOENIG_RADIUS_KM = 5
TANKERKOENIG_STATIONS_PER_CITY = 20

# ── Ausgabepfade ───────────────────────────────────────────────────
DATA_DIR = "data"
OUTPUT_DIR = "output"

# ── Chart-Farben (konsistentes Farbschema) ─────────────────────────
COLORS = {
    "electricity": "#3b82f6",   # Blau
    "brent":       "#f97316",   # Orange
    "ttf":         "#22c55e",   # Grün
    "coal":        "#8b5cf6",   # Lila
    "heating_oil": "#ec4899",   # Pink
    "ice":         "#f97316",   # Orange – Benziner
    "bev_home":    "#3b82f6",   # Blau – Heimladen
    "bev_ac":      "#06b6d4",   # Cyan – öffentlich AC
    "bev_dc":      "#8b5cf6",   # Lila – Schnellladen
    "gas":         "#22c55e",   # Grün – Gasheizung
    "oil_heat":    "#f97316",   # Orange – Ölheizung
    "heat_pump":   "#3b82f6",   # Blau – Wärmepumpe
    "direct_elec": "#ec4899",   # Pink – Direktstrom
    "background":  "#0d1117",
    "surface":     "#161b22",
    "text":        "#e6edf3",
    "subtext":     "#8b949e",
    "grid":        "#21262d",
}
