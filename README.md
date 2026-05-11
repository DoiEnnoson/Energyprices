# ⚡ Energie-Newsletter Deutschland

Automatischer wöchentlicher Report mit deutschen Energiepreisen – Strom, Gas, Öl, Kohle, Kraftstoff, Fahrzeugvergleich und Heizkosten. Läuft vollständig über GitHub Actions ohne eigenen Server.

---

## Was kommt im Newsletter?

| Modul | Quelle | Update |
|---|---|---|
| Strom Day-Ahead DE-LU | Energy-Charts API (Fraunhofer ISE) | täglich |
| Erdgas (TTF Futures) | Yahoo Finance `TTF=F` | börsentäglich |
| Brent Rohöl | Yahoo Finance `BZ=F` | börsentäglich |
| Kohle API2 CIF ARA | Yahoo Finance `MTF=F` (EU-Benchmark) | börsentäglich |
| Heizöl (Retail-Proxy) | Yahoo Finance `HO=F` + DE-Aufschlag | börsentäglich |
| Kraftstoff DE (E5/E10/Diesel) | Tankerkönig / MTS-K | täglich |
| Haushaltstrom- & Gaspreis | BDEW (statisch, quartalsweise) | manuell |
| Opel Astra BEV vs. ICE | berechnet aus obigen Preisen | wöchentlich |
| Heizkosten (Haus/Wohnung) | berechnet aus obigen Preisen | wöchentlich |

**Ausgaben:** HTML-E-Mail (Charts eingebettet) · `data/latest.json` (für Webseite) · `data/historical.csv` (Zeitreihe) · optional 3 X/Twitter-Tweets

---

## Setup in 5 Schritten

### 1. Repository forken / klonen

```bash
git clone https://github.com/DEIN-USERNAME/energy-newsletter.git
cd energy-newsletter
```

### 2. GitHub Secrets anlegen

`Settings → Secrets and variables → Actions → New repository secret`

#### Pflicht

| Secret | Wert |
|---|---|
| `EMAIL_FROM` | Absender-Adresse |
| `EMAIL_TO` | Empfänger (kommagetrennt für mehrere) |
| `EMAIL_PROVIDER` | `smtp` oder `sendgrid` |

#### SMTP (z. B. Gmail)

| Secret | Wert |
|---|---|
| `SMTP_HOST` | `smtp.gmail.com` |
| `SMTP_PORT` | `587` |
| `SMTP_USER` | deine Gmail-Adresse |
| `SMTP_PASS` | [Gmail App-Passwort](https://myaccount.google.com/apppasswords) |

> **Gmail:** 2FA muss aktiviert sein, dann App-Passwort unter *Google-Konto → Sicherheit → App-Passwörter* erzeugen.

#### SendGrid (Alternative)

| Secret | Wert |
|---|---|
| `EMAIL_PROVIDER` | `sendgrid` |
| `SENDGRID_API_KEY` | `SG.xxxxx` |

#### Kraftstoffpreise (optional, empfohlen)

Kostenloser API-Key: https://creativecommons.tankerkoenig.de/

| Secret | Wert |
|---|---|
| `TANKERKOENIG_API_KEY` | dein Key |

Ohne diesen Key fehlen die Kraftstoffpreise im Newsletter; alle anderen Module laufen trotzdem.

#### Twitter/X (optional)

Benötigt **Basic Tier** (~$100/Monat) – kein Free-Tier-Posting möglich.

| Secret | Wert |
|---|---|
| `TWITTER_API_KEY` | Consumer Key |
| `TWITTER_API_SECRET` | Consumer Secret |
| `TWITTER_ACCESS_TOKEN` | Access Token |
| `TWITTER_ACCESS_SECRET` | Access Token Secret |
| `TWITTER_BEARER_TOKEN` | Bearer Token |

Ohne diese Secrets wird das Twitter-Modul automatisch übersprungen.

### 3. Workflow aktivieren

Der Workflow läuft automatisch **jeden Montag um 07:00 UTC** (08:00 / 09:00 MEZ/MESZ).

Für einen sofortigen Test: `Actions → Weekly Energy Newsletter → Run workflow`

### 4. Lokal testen

```bash
pip install -r requirements.txt
cp .env.example .env        # Werte ausfüllen

# Einzeln oder in Reihenfolge:
python src/fetch_prices.py
python src/generate_charts.py
python src/generate_newsletter.py
# python src/send_email.py   # nur wenn .env korrekt gesetzt
```

### 5. BDEW-Preise quartalsweise aktualisieren

In `src/config.py` die Werte `BDEW["electricity_ct_kwh"]` und `BDEW["gas_ct_kwh"]` aktualisieren, wenn BDEW neue Zahlen veröffentlicht (typisch: April und Oktober).

Quellen:
- https://www.bdew.de/energie/strom-und-gaspreis-analysen/
- https://www.bundesnetzagentur.de → Monitoringbericht

---

## Ausgabedateien

```
data/
  historical.csv          # Wöchentliche Zeitreihe, automatisch befüllt
  latest.json             # Aktuelle Woche als JSON (für Webseite)
  weekly_YYYY-KWxx.json   # Archiv jeder Woche

output/
  newsletter_YYYY-KWxx.html   # HTML-E-Mail (Charts inline als Base64)
  chart_prices.png            # Energiepreisverlauf (26 Wochen)
  chart_vehicle.png           # Opel Astra BEV vs. ICE
  chart_heating.png           # Heizkosten Vergleich
  web_data.json               # Strukturiert für Webseite
```

Die `data/`-Dateien werden nach jedem Lauf automatisch per Git committed.

---

## Fahrzeugmodell & Verbrauchsannahmen

**Opel Astra** – beide Varianten gleiche Karosserie, EMP2-Plattform:

| | Astra 1.2 Turbo 130 PS | Astra Electric 156 PS |
|---|---|---|
| Verbrauch WLTP | 5,8 L/100 km | 15,8 kWh/100 km |
| Verbrauch real (angesetzt) | **6,5 L/100 km** | **18,0 kWh/100 km** |
| Kraftstoff | Super E5 | — |

Ladepreise öffentlich (Verivox/BDEW Ø DE 2025): AC 54 ct/kWh · DC Schnellladen 64 ct/kWh

Kein kostenfreier Live-API für öffentliche Ladepreise verfügbar; Werte werden in `config.py` quartalsweise aktualisiert.

---

## Heizungsmodell

| System | Effizienz / COP |
|---|---|
| Gasheizung | 87 % (Brennwert) |
| Ölheizung | 85 % |
| Wärmepumpe | COP 3,5 |
| Direktstromheizung | 100 % |

Jahresbedarf: Einfamilienhaus 150 m² → 15.000 kWh · Wohnung 100 m² → 8.000 kWh

---

## Quellen

- **Strom Day-Ahead:** https://api.energy-charts.info (Fraunhofer ISE / ENTSO-E)
- **Rohstoffe:** Yahoo Finance (yfinance) – keine Registrierung nötig
- **Kohle:** API2 CIF ARA ist der europäische Import-Benchmark (Argus/McCloskey via CME, Ticker `MTF=F`)
- **Heizöl:** NY Harbor ULSD Futures (`HO=F`) als Proxy; Retail-Aufschlag +0,12 EUR/L
- **Kraftstoff:** Tankerkönig / MTS-K (Markttransparenzstelle für Kraftstoffe)
- **Haushaltsenergiepreise:** BDEW Strompreisanalyse, Bundesnetzagentur Monitoringbericht

---

## Lizenz

MIT
