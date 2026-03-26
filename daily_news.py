#!/usr/bin/env python3
"""
Európai Hírlap – Napi automatikus küldés
Google News RSS + Groq Llama (magyar összefoglaló)
"""

import os
import json
import re
import smtplib
import datetime
import time
import requests
import feedparser
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# KONFIGURÁCIÓ
GROQ_API_KEY   = os.environ.get("GROQ_API_KEY", "").strip()
GMAIL_USER     = os.environ.get("GMAIL_USER", "galaczi.usa@gmail.com").strip()
GMAIL_APP_PASS = os.environ.get("GMAIL_APP_PASS", "").strip()
TO_EMAILS      = ["galaczi.usa@gmail.com", "gorsi.kata@gmail.com"]

ICONS      = {"econ":"📈","eu":"🇪🇺","war":"⚔️","spain":"🇪🇸"}
CAT_COLORS = {"econ":"#1a4a6b","eu":"#2d6a4f","war":"#7b2d2d","spain":"#8B0000"}


def fetch_google_news(query, max_results=10, hl="hu", gl="HU"):
    """Google News RSS lekérése"""
    encoded = requests.utils.quote(query)
    url = f"https://news.google.com/rss/search?q={encoded}&hl={hl}&gl={gl}&ceid=HU:hu"
    
    print(f"→ Lekérés: {query}")
    feed = feedparser.parse(url)
    articles = []
    
    for entry in feed.entries[:max_results]:
        title = entry.get("title", "").strip()
        summary = entry.get("summary", "")[:250].strip()
        link = entry.get("link", "")
        published = entry.get("published", "")
        
        if title and "[Removed]" not in title:
            articles.append({
                "title": title,
                "desc": summary,
                "source": "Google News",
                "link": link
            })
    
    print(f"   talált cikkek: {len(articles)} db")
    return articles


def fetch_all_news():
    print("Google News RSS lekérése indul...\n")
    
    queries = {
        "econ":  "gazdaság OR infláció OR ECB OR EKB OR eurozone OR kamat OR tőzsde",
        "eu":    "Európai Unió OR Ursula von der Leyen OR Brüsszel OR EU Bizottság",
        "war":   "Ukrajna háború OR Putyin OR Zelenszkij OR orosz-ukrán",
        "spain": "Spanyolország OR Sánchez OR Madrid OR PSOE OR spanyol kormány"
    }
    
    return {
        "econ":  fetch_google_news(queries["econ"], max_results=12),
        "eu":    fetch_google_news(queries["eu"], max_results=10),
        "war":   fetch_google_news(queries["war"], max_results=10),
        "spain": fetch_google_news(queries["spain"], max_results=8, hl="es", gl="ES")
    }


def summarize_with_groq(articles, category_name, date_str):
    """Groq összefoglaló magyarul"""
    if not articles:
        print(f"   Nincs cikk a {category_name} kategóriában")
        return []

    articles_text = "\n".join([
        f"- {a['title']} | {a['desc'][:180]} | Forrás: {a['source']}"
        for a in articles[:8]
    ])

    prompt = f"""Az alábbi mai hírek alapján készíts **pontosan 4-5** magyar nyelvű hírösszefoglalót a "{category_name}" kategóriához.
Dátum: {date_str}

Hírek:
{articles_text}

Szabályok:
- Pontosan 4 vagy 5 tétel
- Minden tétel: rövid magyar cím + 2 mondatos magyar összefoglaló + forrás
- Válaszolj KIZÁRÓLAG érvényes JSON tömbként, semmi más szöveg nélkül:
[{{"num":"01","title":"Magyar cím","body":"Két mondatos összefoglaló magyarul.","source":"Forrás neve"}}]

CSAK a JSON tömböt add vissza!"""

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 1200,
        "temperature": 0.4,
    }

    for attempt in range(3):
        try:
            resp = requests.post("https://api.groq.com/openai/v1/chat/completions",
                                 headers=headers, json=payload, timeout=50)
            resp.raise_for_status()
            text = resp.json()["choices"][0]["message"]["content"].strip()
            
            # JSON tisztítás
            clean = re.sub(r"```json|```", "", text).strip()
            start = clean.find("[")
            end = clean.rfind("]") + 1
            if start >= 0 and end > start:
                clean = clean[start:end]
            
            result = json.loads(clean)
            print(f"   Groq összefoglaló kész: {len(result)} elem")
            return result
        except Exception as e:
            print(f"   Groq hiba ({attempt+1}/3): {e}")
            if attempt < 2:
                time.sleep(12)
    return []


def get_news(date_str):
    raw = fetch_all_news()
    cats = [
        ("econ",  "Gazdaság & Tőzsdés Hírek"),
        ("eu",    "EU & Európai Politika"),
        ("war",   "Háborús és Geopolitikai Hírek"),
        ("spain", "Spanyol Hírek")
    ]
    
    categories = []
    for idx, (cid, ctitle) in enumerate(cats):
        print(f"\nFeldolgozás: {ctitle}...")
        if idx > 0:
            time.sleep(10)  # Groq rate limit védelem
        
        news_items = summarize_with_groq(raw[cid], ctitle, date_str)
        for i, item in enumerate(news_items):
            item["num"] = str(i+1).zfill(2)
        
        categories.append({"id": cid, "title": ctitle, "news": news_items})
    
    return {"date": date_str, "categories": categories}


# A build_html és send_email függvények maradnak ugyanazok (csak másold be őket a régi kódodból)

# ... (ide másold be a régi build_html és send_email függvényeket változtatás nélkül)

def run():
    today  = datetime.date.today()
    days   = ["hétfő","kedd","szerda","csütörtök","péntek","szombat","vasárnap"]
    months = ["január","február","március","április","május","június","július","augusztus","szeptember","október","november","december"]
    
    date_str = f"{today.year}. {months[today.month-1]} {today.day}., {days[today.weekday()]}"
    
    print(f"Európai Hírlap napi futtatás indul... ({date_str})\n")
    
    news_data  = get_news(date_str)
    html_email = build_html(news_data)      # <-- ezt a függvényt a régi kódból másold be
    send_email(html_email, date_str)


if __name__ == "__main__":
    run()
