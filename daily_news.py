#!/usr/bin/env python3
"""
Europai Hirlap – Napi automatikus küldő
Javított 2026.03 verzió
"""
import os
import json
import re
import smtplib
import datetime
import requests
import traceback
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# KONFIGURÁCIÓ (titkosítva GitHub Secrets-ben)
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()
NEWS_API_KEY = os.environ.get("NEWS_API_KEY", "").strip()
GMAIL_USER = os.environ.get("GMAIL_USER", "galaczi.usa@gmail.com").strip()
GMAIL_APP_PASS = os.environ.get("GMAIL_APP_PASS", "").strip()
TO_EMAILS = ["galaczi.usa@gmail.com", "kata.gorcsi@gmail.com"]

ICONS = {"econ": "📈", "eu": "🇪🇺", "war": "⚔️", "spain": "🇪🇸"}
CAT_COLORS = {"econ": "#1a4a6b", "eu": "#2d6a4f", "war": "#7b2d2d", "spain": "#8B0000"}

# fetch_articles függvény (korábbi verzió)
def fetch_articles(query, language="en", page_size=15):
    today = datetime.date.today().isoformat()
    url = "https://newsapi.org/v2/everything"
    params = {
        "q": query,
        "from": today,
        "to": today,
        "language": language,
        "sortBy": "publishedAt",
        "pageSize": page_size,
        "apiKey": NEWS_API_KEY
    }
    try:
        resp = requests.get(url, params=params, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        results = []
        for a in data.get("articles", []):
            title = (a.get("title") or "").strip()
            desc = (a.get("description") or "").strip()
            source = a.get("source", {}).get("name", "Ismeretlen")
            url_link = a.get("url", "#")

            if "[Removed]" in title or not title:
                if desc and len(desc) > 30:
                    title = desc[:100] + "..." if len(desc) > 100 else desc
                elif url_link != "#":
                    title = "Cikk: " + source
                else:
                    continue

            if title:
                results.append({"title": title, "desc": desc[:300], "source": source, "url": url_link})

        print(f"[{query}] Letöltve {len(results)} használható cikk")
        return results
    except Exception as e:
        print(f"NewsAPI hiba ({query}): {e}")
        return []

def fetch_all_news():
    print("NewsAPI hírek letöltése...")
    return {
        "econ": fetch_articles("Europe economy OR stock market OR ECB OR inflation OR eurozone finance OR EU GDP", page_size=15),
        "eu": fetch_articles("European Union OR EU politics OR Brussels OR Ursula von der Leyen OR EU Commission OR EU summit", page_size=15),
        "war": fetch_articles("Ukraine war OR Russia Ukraine OR Gaza OR Israel Hamas OR Middle East conflict", page_size=15),
        "spain": fetch_articles("España OR Spain politics OR Pedro Sánchez OR PP OR Vox OR Spanish economy", language="es", page_size=15),
    }

def summarize_with_groq(articles, category_name, date_str):
    if not articles:
        return [{"num": "01", "title": f"Ma nincs kiemelt hír – {category_name}", "body": "A nap folyamán nem érkezett elegendő releváns friss hír ehhez a témához.", "source": "NewsAPI"}]

    articles_text = "\n".join([f"- {a['title']} | {a['desc']} | Forrás: {a['source']}" for a in articles])

    prompt = f"""Mai hírek alapján készíts legfeljebb 5, de legalább 2-5 releváns magyar hírösszefoglalót a "{category_name}" kategóriához.
Dátum: {date_str}

Hírek:
{articles_text}

Szabályok:
- Legfeljebb 5 tétel (ha kevesebb jó van, kevesebbet adj)
- Minden tétel: rövid magyar cím + 2 mondatos összefoglaló + forrás
- Válaszolj KIZÁRÓLAG valid JSON tömbbel:
[{{"num":"01","title":"Cím","body":"Mondat1. Mondat2.","source":"Forrás"}}]
Csak JSON!"""

    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 2000,
        "temperature": 0.35,
    }

    for attempt in range(5):
        try:
            resp = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=80)
            resp.raise_for_status()
            text = resp.json()["choices"][0]["message"]["content"].strip()
            text = re.sub(r'^[^[]*\[', '[', text)
            text = re.sub(r'\][^]]*$', ']', text)
            text = re.sub(r'```json|```', '', text).strip()
            result = json.loads(text)
            print(f"Groq OK: {len(result)} elem '{category_name}'")
            return result[:5]
        except Exception as e:
            print(f"Groq hiba ({attempt+1}/5) [{category_name}]: {e}")
            if attempt < 4:
                import time
                time.sleep(15 * (attempt + 1))

    return [{"num": "01", "title": f"Hiba – {category_name}", "body": "Technikai probléma, próbáld újra.", "source": "Rendszer"}]

# A hiányzó függvény – tedd be ide, ha nincs
def get_news(date_str):
    raw = fetch_all_news()
    cats = [
        ("econ", "Gazdaság & Tőzsdei Hírek"),
        ("eu", "EU & Európai Közösség"),
        ("war", "Háborús & Geopolitikai Hírek"),
        ("spain", "Spanyol Hírek"),
    ]
    categories = []
    for idx, (cid, ctitle) in enumerate(cats):
        print(f"Feldolgozás: {ctitle}...")
        if idx > 0:
            import time
            time.sleep(10)
        news_items = summarize_with_groq(raw[cid], ctitle, date_str)
        for i, item in enumerate(news_items):
            item["num"] = str(i+1).zfill(2)
        categories.append({"id": cid, "title": ctitle, "news": news_items})
    return {"date": date_str, "categories": categories}

# build_html (részlet, tedd be a teljes verziót ha kell)
def build_html(data):
    # ... (a korábbi build_html kódod, ami fallback-et kezel)
    # Ha nincs, használd az előző üzenetemből a build_html-t
    pass  # cseréld ki a sajátoddal

def send_email(html_content, date_str):
    # ... (a korábbi send_email kódod)
    pass  # cseréld ki

def run():
    today = datetime.date.today()
    days = ["hétfő", "kedd", "szerda", "csütörtök", "péntek", "szombat", "vasárnap"]
    months = ["január", "február", "március", "április", "május", "június", "július", "augusztus", "szeptember", "október", "november", "december"]
    date_str = f"{today.year}. {months[today.month-1]} {today.day}., {days[today.weekday()]}"
    print(f"Indítás: {date_str}")
    news_data = get_news(date_str)  # Itt hívódik – most már definiálva van fent
    html_email = build_html(news_data)
    send_email(html_email, date_str)

if __name__ == "__main__":
    run()
