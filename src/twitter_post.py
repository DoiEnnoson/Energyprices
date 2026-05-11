"""
twitter_post.py – Optionales Twitter/X-Posting-Modul

Benötigt: X API Basic Tier (ca. $100/Monat) – kein Free-Tier-Posting.
Aktivierung: GitHub Secret TWITTER_API_KEY setzen (und die weiteren unten).

Postet 3 Tweets:
  1. Marktübersicht (Day-Ahead-Strom, TTF, Brent, Kohle)
  2. Fahrzeugvergleich Astra BEV vs. ICE
  3. Heizkosten-Snapshot

GitHub Secrets:
  TWITTER_API_KEY
  TWITTER_API_SECRET
  TWITTER_ACCESS_TOKEN
  TWITTER_ACCESS_SECRET
  TWITTER_BEARER_TOKEN   (optional, für v2 App-Auth)
"""

import json
import logging
import os
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent))
import config as C

log = logging.getLogger(__name__)


def build_tweets(data: dict) -> list[str]:
    meta  = data["meta"]
    elec  = data.get("electricity_dayahead", {})
    comm  = data.get("commodities", {})
    fuel  = data.get("fuel_prices") or {}
    vc    = data.get("vehicle_comparison", {})
    heat  = data.get("heating_costs", {})
    week  = meta["week"]

    tweets = []

    # ── Tweet 1: Marktübersicht ────────────────────────────────────
    strom = elec.get("week_avg", "–")
    ttf   = comm.get("ttf", {}).get("avg", "–")
    brent = comm.get("brent", {}).get("avg_eur_bbl", "–")
    coal  = comm.get("coal", {}).get("avg_eur_t", "–")
    e5    = fuel.get("e5", "–")

    t1 = (
        f"⚡ #Energiepreise Deutschland – {week}\n\n"
        f"🔵 Strom Day-Ahead:  {strom:.1f} EUR/MWh\n"
        f"🟢 Erdgas (TTF):     {ttf:.1f} EUR/MWh\n"
        f"🟠 Brent Rohöl:      {brent:.1f} EUR/bbl\n"
        f"🟣 Kohle API2 ARA:   {coal:.0f} EUR/t\n"
        f"⛽ Super E5:         {e5:.3f} EUR/L\n\n"
        f"#Strom #Gas #Erdöl #Kohle #Energiewende"
    )
    tweets.append(t1)

    # ── Tweet 2: BEV vs. ICE ──────────────────────────────────────
    ice    = vc.get("ice", {})
    bev_h  = vc.get("bev_home", {})
    bev_dc = vc.get("bev_public_dc", {})

    if ice and bev_h:
        ice_cost  = ice.get("cost_per_100km", "–")
        bev_cost  = bev_h.get("cost_per_100km", "–")
        bev_dc_c  = bev_dc.get("cost_per_100km", "–") if bev_dc else "–"
        save      = bev_h.get("savings_pct_vs_ice", "–")
        t2 = (
            f"🚗⚡ Opel Astra – {week}\n\n"
            f"Benziner (1.2T):      {ice_cost:.2f} €/100 km\n"
            f"Elektro Heimladen:    {bev_cost:.2f} €/100 km  "
            f"(–{save:.0f}% günstiger)\n"
            f"Elektro Schnellladen: {bev_dc_c:.2f} €/100 km\n\n"
            f"#ElektroAuto #EV #BEV #Laden #Benzin"
        )
        tweets.append(t2)

    # ── Tweet 3: Heizkosten ────────────────────────────────────────
    haus = heat.get("haus_150qm", {}).get("systems", {})
    gas  = haus.get("gas_boiler",     {}).get("weekly_cost_eur", "–")
    oil  = haus.get("oil_boiler",     {}).get("weekly_cost_eur", "–")
    hp   = haus.get("heat_pump",      {}).get("weekly_cost_eur", "–")
    el   = haus.get("direct_electric",{}).get("weekly_cost_eur", "–")

    if any(v != "–" for v in [gas, oil, hp, el]):
        def fmt(v): return f"{v:.2f} €" if isinstance(v, float) else str(v)
        t3 = (
            f"🏠 Heizkosten EFH 150 m² – {week}\n"
            f"(Wöchentliche Energiekosten)\n\n"
            f"🟢 Gasheizung:     {fmt(gas)}\n"
            f"🟠 Ölheizung:      {fmt(oil)}\n"
            f"🔵 Wärmepumpe:    {fmt(hp)}\n"
            f"🟣 Direktstrom:   {fmt(el)}\n\n"
            f"#Heizung #Wärmepumpe #Gas #Heizöl #Energiekosten"
        )
        tweets.append(t3)

    return tweets


def post_tweets(tweets: list[str]):
    try:
        import tweepy
    except ImportError:
        log.error("tweepy nicht installiert: pip install tweepy")
        raise

    client = tweepy.Client(
        bearer_token=os.environ.get("TWITTER_BEARER_TOKEN"),
        consumer_key=os.environ["TWITTER_API_KEY"],
        consumer_secret=os.environ["TWITTER_API_SECRET"],
        access_token=os.environ["TWITTER_ACCESS_TOKEN"],
        access_token_secret=os.environ["TWITTER_ACCESS_SECRET"],
    )

    last_id = None
    for i, tweet_text in enumerate(tweets):
        kwargs = {"text": tweet_text}
        if last_id and i > 0:
            kwargs["in_reply_to_tweet_id"] = last_id  # Thread

        response = client.create_tweet(**kwargs)
        last_id  = response.data["id"]
        log.info(f"Tweet {i+1}/{len(tweets)} gesendet (ID: {last_id})")


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s %(message)s")

    if not os.environ.get("TWITTER_API_KEY"):
        log.info("TWITTER_API_KEY nicht gesetzt – Twitter-Posting übersprungen")
        return

    latest_path = Path(C.DATA_DIR) / "latest.json"
    if not latest_path.exists():
        log.error(f"{latest_path} nicht gefunden")
        return

    with open(latest_path, encoding="utf-8") as f:
        data = json.load(f)

    tweets = build_tweets(data)
    log.info(f"{len(tweets)} Tweets vorbereitet …")

    for i, t in enumerate(tweets, 1):
        log.info(f"--- Tweet {i} ({len(t)} Zeichen) ---\n{t}\n")

    post_tweets(tweets)
    log.info("✓ Twitter-Posts abgeschlossen")


if __name__ == "__main__":
    main()
