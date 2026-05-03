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

ICONS      = {"econ":"📈","eu":"🇪🇺","war":"⚔️","spain":"🇪🇸","tech":"🛡️"}
CAT_COLORS = {"econ":"#1a4a6b","eu":"#2d6a4f","war":"#7b2d2d","spain":"#8B0000","tech":"#1a3a2a"}


def fetch_google_news(query, max_results=15, hl="en", gl="US"):
    """Csak nemzetközi top források (Reuters, BBC, AP, Bloomberg, Politico, Euronews, FT, Guardian stb.)"""
    encoded = requests.utils.quote(query)
    url = f"https://news.google.com/rss/search?q={encoded}&hl={hl}&gl={gl}&ceid=US:en"
    
    print(f"→ Lekérés (CSAK NEMZETKÖZI): {query}")
    try:
        feed = feedparser.parse(url)
        articles = []
        
        for entry in feed.entries[:max_results]:
            title = entry.get("title", "").strip()
            summary = entry.get("summary", "")[:300].strip()
            if title and len(title) > 20 and "[Removed]" not in title:
                articles.append({
                    "title": title,
                    "desc": summary or "Nincs leírás",
                    "source": "Google News International"
                })
        
        print(f"   Talált cikkek: {len(articles)} db")
        return articles
    except Exception as e:
        print(f"   Hiba: {e}")
        return []


def fetch_all_news():
    print("Google News RSS – CSAK NEMZETKÖZI TOP FORRÁSOK lekérése...\n")
    
    queries = {
        "econ":  "inflation OR ECB OR interest rate OR stock market OR eurozone OR Fed OR Bundesbank OR FTSE OR DAX",
        "eu":    "Ursula von der Leyen OR European Commission OR EU politics OR Brussels OR EU summit",
        "war":   "Ukraine war OR Russia Ukraine OR Putin OR Zelenskyy OR Russia-Ukraine conflict",
        "spain": "Pedro Sánchez OR Spain government OR Spanish politics OR PSOE",
        # Kiberbiztonság: aktív fenyegetések, CVE-k, patch-ek, CMS támadások, malware kampányok
        "tech":  (
            "CVE vulnerability OR WordPress exploit OR cybersecurity attack OR"
            " ransomware OR zero-day OR patch Tuesday OR data breach OR"
            " malware campaign OR DDoS attack OR phishing campaign OR"
            " security advisory OR Cisco vulnerability OR Microsoft patch OR"
            " WordPress plugin vulnerability OR web skimmer OR supply chain attack"
        ),
    }
    
    return {
        "econ":  fetch_google_news(queries["econ"],  max_results=18),
        "eu":    fetch_google_news(queries["eu"],    max_results=15),
        "war":   fetch_google_news(queries["war"],   max_results=15),
        "spain": fetch_google_news(queries["spain"], max_results=12),
        "tech":  fetch_google_news(queries["tech"],  max_results=20),
    }


# ── Kategória-specifikus Groq promptok ─────────────────────────────────────────

TECH_PROMPT_TEMPLATE = """Az alábbi mai kibervédelmi és technikai biztonsági hírek alapján készíts pontosan 10 magyar nyelvű összefoglalót a "Tech & Kiberbiztonság" kategóriához.
Dátum: {date_str}

Hírek:
{articles_text}

Célközönség: webfejlesztők, rendszergazdák, WordPress / CMS üzemeltetők.

Szabályok:
- Pontosan 10 tétel
- Minden tétel felépítése:
    • Rövid, tömör magyar cím (max 10 szó)
    • 2-3 mondatos összefoglaló: mi történt, melyik szoftver/verzió érintett (ha ismert), és mit kell tenni (frissítés, plugin letiltása, tűzfalszabály, jelszócsere stb.)
- Prioritás: aktív támadások > kritikus CVE / patch > általános biztonsági tanácsok
- Ha van konkrét CVE-szám, verziószám vagy IOC (IP, domain), mindenképpen szerepeljen
- Ne legyen hírismétlés; ha elfogynak a kritikus hírek, jöhetnek fontos általános biztonsági fejlemények
- Válaszolj KIZÁRÓLAG érvényes JSON tömbként, semmi más szöveg nélkül!

Példa formátum:
[{{"num":"01","title":"Kritikus WordPress plugin sebezhetőség","body":"A Contact Form 7 plugin 5.9.5-ös verziója előtt aktív remote code execution (CVE-2025-XXXXX) sebezhetőséget találtak. Azonnal frissíts 5.9.6-ra, vagy deaktiváld a plugint a javítás telepítéséig.","source":"Bleeping Computer"}}]"""

DEFAULT_PROMPT_TEMPLATE = """Az alábbi mai nemzetközi hírek alapján készíts pontosan 10 magyar nyelvű, jó minőségű hírösszefoglalót a "{category_name}" kategóriához.
Dátum: {date_str}

Hírek:
{articles_text}

Szabályok:
- Pontosan 10 tétel
- Minden tétel: rövid, ütős magyar cím + maximum 2 mondatos összefoglaló
- Csak a legfontosabb, legjellemzőbb híreket válaszd ki
- Ne legyen hírismétlés,amennyiben elfogynak az új hírek,lehetnek benne másod sorból fontosnak számító hírek is,de ne ismételjünk
- Válaszolj KIZÁRÓLAG érvényes JSON tömbként, semmi más szöveg nélkül!

Példa formátum:
[{{"num":"01","title":"Cím","body":"Első mondat. Második mondat.","source":"Reuters"}}]"""


def summarize_with_groq(articles, category_id, category_name, date_str):
    if not articles:
        print(f"   Nincs cikk → {category_name} kihagyva")
        return []

    articles_text = "\n".join([
        f"- {a['title']} | {a['desc'][:200]}" for a in articles[:10]
    ])

    if category_id == "tech":
        prompt = TECH_PROMPT_TEMPLATE.format(
            date_str=date_str,
            articles_text=articles_text,
        )
    else:
        prompt = DEFAULT_PROMPT_TEMPLATE.format(
            category_name=category_name,
            date_str=date_str,
            articles_text=articles_text,
        )

    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 1400,
        "temperature": 0.3,  # tech kategóriánál alacsonyabb hőmérséklet = pontosabb adatok
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
        ("spain", "Spanyol Hírek"),
        ("tech",  "Tech & Kiberbiztonság"),
    ]
    
    categories = []
    for idx, (cid, ctitle) in enumerate(cats):
        print(f"Feldolgozás: {ctitle}...")
        if idx > 0:
            time.sleep(10)
        
        news_items = summarize_with_groq(raw[cid], cid, ctitle, date_str)
        for i, item in enumerate(news_items):
            item["num"] = str(i+1).zfill(2)
        
        categories.append({"id": cid, "title": ctitle, "news": news_items})
    
    return {"date": date_str, "categories": categories}


def build_html(data):
    cats_html = ""
    for cat in data["categories"]:
        cid   = cat["id"]
        color = CAT_COLORS.get(cid, "#333333")
        icon  = ICONS.get(cid, "●")

        # Tech kategóriánál a hírsorok kicsit más stílusú (monospace font a CVE-khez, warning badge)
        is_tech = (cid == "tech")

        news_rows = ""
        for item in cat.get("news", []):
            body_style = (
                "font-family:monospace,monospace;font-size:13px;line-height:1.7;color:#1a2e1a"
                if is_tech else
                "font-family:Georgia,serif;font-size:14px;line-height:1.65;color:#2a2015"
            )
            badge = (
                '<span style="display:inline-block;background:#c0392b;color:#fff;'
                'font-size:9px;letter-spacing:1px;padding:1px 5px;border-radius:2px;'
                'margin-right:6px;vertical-align:middle">⚠ TECH</span>'
                if is_tech else ""
            )
            news_rows += f"""
            <tr>
              <td style="width:28px;font-family:Georgia,serif;font-size:13px;color:{color};opacity:0.5;vertical-align:top;padding:12px 6px 12px 0">{item['num']}</td>
              <td style="padding:12px 0;border-bottom:1px solid #e8e2d5;{body_style}">
                <strong>{badge}{item.get('title', '')}</strong><br>
                {item.get('body', '')}
                <span style="display:block;font-size:11px;color:#999;font-style:italic;margin-top:4px">Forrás: {item.get('source', 'Google News')}</span>
              </td>
            </tr>"""
        
        cats_html += f"""
        <tr><td colspan="2" style="padding:0">
          <table width="100%" cellpadding="0" cellspacing="0">
            <tr><td style="background:{color};padding:16px 32px;font-family:Georgia,serif">
              <span style="font-size:22px">{icon}</span>
              <span style="font-size:20px;font-weight:700;color:#fff;margin-left:12px">{cat['title']}</span>
              <span style="float:right;font-size:11px;color:rgba(255,255,255,0.6);letter-spacing:2px;padding-top:4px">10 HÍR</span>
            </td></tr>
            <tr><td style="padding:4px 32px 16px">
              <table width="100%" cellpadding="0" cellspacing="0">{news_rows}</table>
            </td></tr>
          </table>
        </td></tr>
        <tr><td colspan="2" style="height:4px;background:repeating-linear-gradient(90deg,#e8e2d5 0,#e8e2d5 6px,transparent 6px,transparent 10px)"></td></tr>"""

    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#2a2015">
<table width="680" cellpadding="0" cellspacing="0" align="center" style="background:#f5f0e8;margin:20px auto">
  <tr><td colspan="2" style="background:#1a1209;padding:28px 40px 20px;text-align:center;border-bottom:4px solid #b8922a">
    <div style="font-size:38px;font-weight:900;color:#f5f0e8">Európai<span style="color:#b8922a"> Hírlap</span></div>
    <div style="color:#8a7d68;font-size:10px;letter-spacing:4px;text-transform:uppercase;margin-top:8px">Minden reggel · A világ legfontosabb hírei</div>
    <div style="color:#c5b99a;font-size:13px;font-style:italic;border-top:1px solid #3d3428;padding-top:10px;margin-top:10px">{data['date']} &nbsp;·&nbsp; Reggeli kiadás &nbsp;·&nbsp; 09:00 CET</div>
  </td></tr>
  <tr><td colspan="2" style="background:#b8922a;padding:8px 40px;font-size:10px;letter-spacing:3px;text-transform:uppercase;color:#1a1209;text-align:center;font-weight:700">
    5 KATEGÓRIA · 50 FRISS HÍR · 🛡️ KIBERVÉDELMI FIGYELMEZTETÉSEK
  </td></tr>
  {cats_html}
  <tr><td colspan="2" style="background:#1a1209;padding:18px 40px;text-align:center">
    <p style="color:#5a5040;font-size:10px;line-height:1.9;margin:0">
      Európai Hírlap • Top nemzetközi források + Groq AI<br>
      Minden nap 09:00 CET • galaczi.usa@gmail.com
    </p>
  </td></tr>
</table>
</body></html>"""


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

    if total_final >= 5:
        html_email = build_html(news_data)
        send_email(html_email, date_str)
        print("Email elküldve.")
    else:
        print("⚠️  TÚL KEVÉS HÍR – nem küldünk emailt (csak akkor, ha van legalább 5 összefoglaló).")

if __name__ == "__main__":
    run()
