"""
auto_update_reference_prices.py
─────────────────────────────────────────────────────────────────────
Aktualisiert BDEW["electricity_ct_kwh"] und BDEW["gas_ct_kwh"]
in config.py automatisch – kein manueller Eingriff.

Strategie:
  1. Scrape globalpetrolprices.com → DE Haushaltstrom + Haushaltsgas
  2. Schlägt das fehl (HTML-Struktur geändert): Groq-LLM extrahiert
     den Preis aus dem Seitentext (kostenloser Tier, llama3-70b)
  3. Verivox.de als zweite Scraping-Quelle (Fallback zu Groq)
  4. Wenn alle Quellen fehlschlagen: bestehender config.py-Wert bleibt
     erhalten – kein Absturz, nur Warning im Log

Voraussetzung:
  pip install requests beautifulsoup4 groq
  GitHub Secret: GROQ_API_KEY  (kostenlos: https://console.groq.com)

Läuft als erster Schritt im GitHub Actions Workflow, vor fetch_prices.py
"""

import logging
import os
import re
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

# ── Quellen ────────────────────────────────────────────────────────

SOURCES = {
    "electricity": {
        "gpp_url":     "https://www.globalpetrolprices.com/Germany/electricity_prices/",
        "verivox_url": "https://www.verivox.de/strom/",
        "groq_query":  (
            "Was ist aktuell der durchschnittliche Haushaltsstrompreis in Deutschland "
            "in Cent pro kWh (ct/kWh) inkl. MwSt.? Antworte NUR mit einer Zahl."
        ),
    },
    "gas": {
        "gpp_url":     "https://www.globalpetrolprices.com/Germany/natural-gas-prices/",
        "verivox_url": "https://www.verivox.de/gas/",
        "groq_query":  (
            "Was ist aktuell der durchschnittliche Haushaltsgaspreis in Deutschland "
            "in Cent pro kWh (ct/kWh) inkl. MwSt.? Antworte NUR mit einer Zahl."
        ),
    },
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
}

CONFIG_PATH = Path(__file__).parent / "config.py"


# ── Scraping: globalpetrolprices.com ──────────────────────────────

def scrape_globalpetrolprices(url: str) -> float | None:
    """
    Extrahiert EUR/kWh-Preis aus globalpetrolprices.com.
    Die Seite zeigt: 'EUR 0.371 per kWh' oder ähnlich als <span>.
    """
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        # Primär: Suche nach typischen Preis-Patterns auf der Seite
        text = soup.get_text(" ", strip=True)

        # Pattern 1: "EUR 0.371 per kWh" → 37.1 ct/kWh
        m = re.search(r"EUR\s+([\d]+\.\d+)\s+per\s+kWh", text, re.IGNORECASE)
        if m:
            eur_kwh = float(m.group(1))
            ct_kwh  = round(eur_kwh * 100, 2)
            log.info(f"  GPP direkt: {eur_kwh:.4f} EUR/kWh = {ct_kwh} ct/kWh")
            return ct_kwh

        # Pattern 2: Tabellenzelle mit Preis in EUR/kWh
        for cell in soup.find_all(["td", "span", "div"]):
            cell_text = cell.get_text(strip=True)
            m2 = re.search(r"([\d]+[\.,]\d+)\s*(?:EUR)?.*?kWh", cell_text, re.IGNORECASE)
            if m2:
                raw = m2.group(1).replace(",", ".")
                val = float(raw)
                if 0.01 < val < 2.0:   # Plausibilitätsprüfung: 1–200 ct/kWh
                    ct_kwh = round(val * 100 if val < 2.0 else val, 2)
                    if 5 < ct_kwh < 200:
                        log.info(f"  GPP Tabelle: {ct_kwh} ct/kWh")
                        return ct_kwh

        log.warning(f"GPP: kein Preis-Pattern gefunden auf {url}")
        return None

    except Exception as exc:
        log.error(f"GPP Scraping {url}: {exc}")
        return None


# ── Scraping: Verivox ──────────────────────────────────────────────

def scrape_verivox(url: str, energy_type: str) -> float | None:
    """Extrahiert Ø-Preis aus Verivox-Übersichtsseite"""
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        text = BeautifulSoup(r.text, "html.parser").get_text(" ", strip=True)

        # Verivox zeigt meist: "XX,XX Cent/kWh" oder "XX ct/kWh"
        patterns = [
            r"([\d]+[,.][\d]+)\s*(?:Cent|ct)[\s/]*kWh",
            r"Durchschnitt[^\d]+([\d]+[,.][\d]+)\s*ct",
        ]
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                val = float(m.group(1).replace(",", "."))
                if 3 < val < 200:
                    log.info(f"  Verivox ({energy_type}): {val} ct/kWh")
                    return val

        log.warning(f"Verivox: kein Preis gefunden für {energy_type}")
        return None

    except Exception as exc:
        log.error(f"Verivox Scraping {url}: {exc}")
        return None


# ── Groq-Fallback ─────────────────────────────────────────────────

def extract_with_groq(html_text: str, query: str, api_key: str) -> float | None:
    """
    Schickt den (gekürzten) Seitentext an Groq.
    Groq extrahiert den Preis als Zahl → wird geparst.

    Modell: llama-3.3-70b-versatile (kostenloser Tier, sehr schnell)
    """
    try:
        from groq import Groq
    except ImportError:
        log.error("groq-Paket nicht installiert: pip install groq")
        return None

    # Text kürzen: Groq-Kontext braucht nicht alles, 3000 Zeichen reichen
    truncated = html_text[:3000]

    prompt = f"""Du analysierst folgenden Text von einer Energiepreis-Website:

---
{truncated}
---

{query}

Wichtig: Antworte ausschließlich mit einer einzigen Dezimalzahl (z. B. "38.5").
Keine Einheiten, keine Erklärungen. Wenn der Preis nicht erkennbar ist: "0"."""

    try:
        client  = Groq(api_key=api_key)
        resp    = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=20,
        )
        raw  = resp.choices[0].message.content.strip()
        val  = float(re.search(r"[\d]+[.,]?[\d]*", raw).group().replace(",", "."))
        if 3 < val < 200:
            log.info(f"  Groq extrahiert: {val} ct/kWh")
            return val
        log.warning(f"  Groq: unplausibler Wert {val}")
        return None
    except Exception as exc:
        log.error(f"Groq-Extraktion: {exc}")
        return None


# ── Hauptfunktion: Preis ermitteln ────────────────────────────────

def fetch_price(energy_type: str, groq_api_key: str) -> float | None:
    src = SOURCES[energy_type]

    # Schritt 1: globalpetrolprices.com scrapen
    price = scrape_globalpetrolprices(src["gpp_url"])
    if price:
        return price

    # Schritt 2: Groq mit GPP-Seitentext
    if groq_api_key:
        log.info(f"  GPP direkt fehlgeschlagen → Groq-Fallback ({energy_type})")
        try:
            r    = requests.get(src["gpp_url"], headers=HEADERS, timeout=15)
            text = BeautifulSoup(r.text, "html.parser").get_text(" ", strip=True)
            price = extract_with_groq(text, src["groq_query"], groq_api_key)
            if price:
                return price
        except Exception as exc:
            log.error(f"  Groq-Fallback GPP: {exc}")

    # Schritt 3: Verivox scrapen
    log.info(f"  Groq fehlgeschlagen → Verivox ({energy_type})")
    time.sleep(1)  # kurze Pause zwischen Requests
    price = scrape_verivox(src["verivox_url"], energy_type)
    if price:
        return price

    # Schritt 4: Groq mit Verivox-Seitentext
    if groq_api_key:
        try:
            r    = requests.get(src["verivox_url"], headers=HEADERS, timeout=15)
            text = BeautifulSoup(r.text, "html.parser").get_text(" ", strip=True)
            price = extract_with_groq(text, src["groq_query"], groq_api_key)
            if price:
                return price
        except Exception as exc:
            log.error(f"  Groq-Fallback Verivox: {exc}")

    log.warning(f"  Alle Quellen erschöpft für {energy_type} – behalte bestehenden config.py-Wert")
    return None


# ── config.py patchen ─────────────────────────────────────────────

def update_config(elec_ct: float | None, gas_ct: float | None, source_label: str):
    """Überschreibt BDEW-Werte in config.py in-place"""
    if elec_ct is None and gas_ct is None:
        log.warning("Keine neuen Preise – config.py bleibt unverändert")
        return

    text = CONFIG_PATH.read_text(encoding="utf-8")
    original = text

    from datetime import date
    now_label = date.today().strftime("%Y-%m")

    if elec_ct is not None:
        text = re.sub(
            r'("electricity_ct_kwh"\s*:\s*)[\d.]+',
            lambda m: f'{m.group(1)}{elec_ct}',
            text,
        )
        log.info(f"config.py: electricity_ct_kwh → {elec_ct}")

    if gas_ct is not None:
        text = re.sub(
            r'("gas_ct_kwh"\s*:\s*)[\d.]+',
            lambda m: f'{m.group(1)}{gas_ct}',
            text,
        )
        log.info(f"config.py: gas_ct_kwh → {gas_ct}")

    # Referenzdatum aktualisieren
    text = re.sub(
        r'("reference_period"\s*:\s*)"[^"]+"',
        f'"reference_period": "{now_label} (auto)"',
        text,
    )

    # Quelle vermerken
    text = re.sub(
        r'("source"\s*:\s*)"[^"]+"',
        f'"source": "{source_label}"',
        text,
    )

    if text != original:
        CONFIG_PATH.write_text(text, encoding="utf-8")
        log.info("config.py aktualisiert")
    else:
        log.info("config.py: keine Änderung")


# ── Einstiegspunkt ─────────────────────────────────────────────────

def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s %(message)s",
    )

    groq_key = os.environ.get("GROQ_API_KEY", "")
    if not groq_key:
        log.warning(
            "GROQ_API_KEY nicht gesetzt – Groq-Fallback deaktiviert. "
            "Kostenloser Key: https://console.groq.com"
        )

    log.info("─── Haushaltsstrompreis DE ───")
    elec_ct = fetch_price("electricity", groq_key)

    log.info("─── Haushaltsgaspreis DE ────")
    gas_ct  = fetch_price("gas", groq_key)

    log.info(f"Ergebnis: Strom={elec_ct} ct/kWh  Gas={gas_ct} ct/kWh")

    sources_used = []
    if elec_ct:
        sources_used.append(f"Strom {elec_ct:.1f} ct/kWh")
    if gas_ct:
        sources_used.append(f"Gas {gas_ct:.1f} ct/kWh")
    source_label = (
        "GlobalPetrolPrices.com / Groq-Extraktion / Verivox (automatisch)"
        if sources_used else "unverändert"
    )

    update_config(elec_ct, gas_ct, source_label)
    log.info("✓ Referenzpreise aktualisiert")


if __name__ == "__main__":
    main()
