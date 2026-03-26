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

# ==================== KONFIGURÁCIÓ ====================
GROQ_API_KEY   = os.environ.get("GROQ_API_KEY", "").strip()
GMAIL_USER     = os.environ.get("GMAIL_USER", "galaczi.usa@gmail.com").strip()
GMAIL_APP_PASS = os.environ.get("GMAIL_APP_PASS", "").strip()

# ←←← IDE TEDD A SAJÁT EMAIL CÍMEIDET ←←←
TO_EMAILS      = ["galaczi.usa@gmail.com", "kata.gorcsi@gmail.com"]

ICONS      = {"econ":"📈","eu":"🇪🇺","war":"⚔️","spain":"🇪🇸"}
CAT_COLORS = {"econ":"#1a4a6b","eu":"#2d6a4f","war":"#7b2d2d","spain":"#8B0000"}


def fetch_google_news(query, max_results=10, hl="hu", gl="HU"):
    encoded = requests.utils.quote(query)
    url = f"https://news.google.com/rss/search?q={encoded}&hl={hl}&gl={gl}&ceid=HU:hu"
    
    print(f"→ Lekérés: {query}")
    try:
        feed = feedparser.parse(url)
        articles = []
        
        for entry in feed.entries[:max_results]:
            title = entry.get("title", "").strip()
            summary = entry.get("summary", "")[:280].strip()
            if title and "[Removed]" not in title and len(title) > 10:
                articles.append({
                    "title": title,
                    "desc": summary or "Nincs rövid leírás",
                    "source": "Google News"
                })
        
        print(f"   Talált cikkek: {len(articles)} db")
        return articles
    except Exception as e:
        print(f"   Hiba a Google News lekérésnél: {e}")
        return []


def fetch_all_news():
    print("Google News RSS lekérése indul...\n")
    
    queries = {
        "econ":  "gazdaság OR infláció OR ECB OR EKB OR kamat OR tőzsde OR eurozone",
        "eu":    "Európai Unió OR Ursula von der Leyen OR Brüsszel OR EU Bizottság",
        "war":   "Ukrajna háború OR Putyin OR Zelenszkij OR orosz-ukrán",
        "spain": "Spanyolország OR Sánchez OR Madrid OR PSOE OR spanyol kormány"
    }
    
    return {
        "econ":  fetch_google_news(queries["econ"],  max_results=12),
        "eu":    fetch_google_news(queries["eu"],    max_results=10),
        "war":   fetch_google_news(queries["war"],   max_results=10),
        "spain": fetch_google_news(queries["spain"], max_results=8, hl="es", gl="ES")
    }


def summarize_with_groq(articles, category_name, date_str):
    if not articles:
        print(f"   Nincs cikk → {category_name} kihagyva")
        return []

    articles_text = "\n".join([
        f"- {a['title']} | {a['desc'][:200]}" for a in articles[:7]
    ])

    prompt = f"""Készíts pontosan 4 magyar nyelvű hírösszefoglalót a "{category_name}" kategóriához a mai hírek alapján.
Dátum: {date_str}

Hírek:
{articles_text}

Szabályok:
- Pontosan 4 tétel
- Minden tétel: rövid magyar cím + 2 mondatos összefoglaló + forrás
- Válasz KIZÁRÓLAG érvényes JSON tömbként, semmi más szöveg nélkül!

Példa:
[{{"num":"01","title":"Cím","body":"Első mondat. Második mondat.","source":"Google News"}}]"""

    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 1000,
        "temperature": 0.4,
    }

    for attempt in range(3):
        try:
            resp = requests.post("https://api.groq.com/openai/v1/chat/completions",
                                 headers=headers, json=payload, timeout=45)
            resp.raise_for_status()
            text = resp.json()["choices"][0]["message"]["content"].strip()
            
            clean = re.sub(r"```json|```", "", text).strip()
            start = clean.find("[")
            end = clean.rfind("]") + 1
            if start >= 0 and end > start:
                clean = clean[start:end]
            
            result = json.loads(clean)
            print(f"   Groq sikeres: {len(result)} összefoglaló")
            return result
        except Exception as e:
            print(f"   Groq hiba ({attempt+1}/3): {e}")
            if attempt < 2:
                time.sleep(12)
    return []


def get_news(date_str):
    raw = fetch_all_news()
    total_raw = sum(len(v) for v in raw.values())
    print(f"\nÖsszes nyers cikk: {total_raw} db\n")

    cats = [
        ("econ",  "Gazdaság & Tőzsdés Hírek"),
        ("eu",    "EU & Európai Politika"),
        ("war",   "Háborús és Geopolitikai Hírek"),
        ("spain", "Spanyol Hírek")
    ]
    
    categories = []
    for idx, (cid, ctitle) in enumerate(cats):
        print(f"Feldolgozás: {ctitle}...")
        if idx > 0:
            time.sleep(10)
        
        news_items = summarize_with_groq(raw[cid], ctitle, date_str)
        for i, item in enumerate(news_items):
            item["num"] = str(i+1).zfill(2)
        
        categories.append({"id": cid, "title": ctitle, "news": news_items})
    
    return {"date": date_str, "categories": categories}


def build_html(data):
    print("build_html függvény elindult...")
    print(f"Beérkező adatok típusa: {type(data)}")
    print(f"Kategóriák száma: {len(data.get('categories', []))}")
    
    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="margin:0; padding:20px; background:#f5f0e8; font-family:Georgia, serif;">
    <h1 style="color:#1a1209;">Európai Hírlap – {data.get('date', 'Ismeretlen dátum')}</h1>
    <p>Összes összefoglaló: {sum(len(cat.get('news', [])) for cat in data.get('categories', []))} db</p>
    <hr>
"""

    for cat in data.get("categories", []):
        ctitle = cat.get("title", "Kategória")
        news_list = cat.get("news", [])
        
        print(f"   Kategória feldolgozása: {ctitle} | {len(news_list)} hír")
        
        html += f'<h2 style="color:#2a2015; margin-top:30px;">{ctitle}</h2>\n<ul style="line-height:1.7;">\n'
        
        for item in news_list:
            title = item.get("title") or item.get("Title") or "Nincs cím"
            body  = item.get("body")  or item.get("Body")  or "Nincs szöveg"
            source = item.get("source") or item.get("Source") or "Google News"
            
            html += f"""
            <li style="margin-bottom:18px;">
                <strong>{title}</strong><br>
                {body}<br>
                <small style="color:#666;">Forrás: {source}</small>
            </li>"""
        
        html += "</ul>\n<hr>\n"
    
    html += """
    <p style="color:#666; font-size:12px; margin-top:40px;">
        Európai Hírlap • Generálva: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}
    </p>
</body>
</html>"""
    
    print(f"build_html kész – generált HTML hossza: {len(html)} karakter")
    return html

def send_email(html_content, date_str):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Europai Hirlap – {date_str}"
    msg["From"]    = GMAIL_USER
    msg["To"]      = ", ".join(TO_EMAILS)
    msg.attach(MIMEText(html_content, "html", "utf-8"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_USER, GMAIL_APP_PASS)
            server.sendmail(GMAIL_USER, TO_EMAILS, msg.as_string())
        print(f"✅ Email sikeresen elküldve {len(TO_EMAILS)} címre!")
    except Exception as e:
        print(f"❌ Email küldési hiba: {e}")


def run():
    today  = datetime.date.today()
    days   = ["hétfő","kedd","szerda","csütörtök","péntek","szombat","vasárnap"]
    months = ["január","február","március","április","május","június","július","augusztus","szeptember","október","november","december"]
    
    date_str = f"{today.year}. {months[today.month-1]} {today.day}., {days[today.weekday()]}"
    
    print(f"Európai Hírlap napi futtatás indul... ({date_str})\n")
    
    news_data = get_news(date_str)
    
    total_final = sum(len(cat.get("news", [])) for cat in news_data.get("categories", []))
    print(f"\nVégső hír darabszám: {total_final} db\n")

    if total_final >= 5:        # legalább 5 összefoglaló kell az email küldéshez
        html_email = build_html(news_data)
        send_email(html_email, date_str)
        print("Email elküldve.")
    else:
        print("⚠️  TÚL KEVÉS HÍR – nem küldünk emailt (csak akkor, ha van legalább 5 összefoglaló).")
        # Opcionális: küldhetsz egy egyszerű értesítést magadnak
        # send_telegram(f"Európai Hírlap: csak {total_final} hír ma – nem küldtünk levelet.")

if __name__ == "__main__":
    run()
