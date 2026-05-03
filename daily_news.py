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
- Prioritás: aktív támadások > kritikus CVE / patch > általános biztonsági tanácsok
- Ha van konkrét CVE-szám, verziószám vagy IOC (IP, domain), mindenképpen szerepeljen a body mezőben
- Ne legyen hírismétlés; ha elfogynak a kritikus hírek, jöhetnek fontos általános biztonsági fejlemények
- Minden tétel KÖTELEZŐ mezői:
    "num"      – sorszám ("01"–"10")
    "title"    – rövid, tömör magyar cím, max 10 szó
    "body"     – 2-3 mondatos összefoglaló: mi történt, melyik szoftver/verzió érintett
    "action"   – 1-2 mondatos konkrét teendő magyarul (mit kell frissíteni, letiltani, ellenőrizni)
    "severity" – PONTOSAN egy ezek közül: "critical" | "medium" | "info"
                   critical = aktív támadás vagy azonnal kihasználható kritikus CVE
                   medium   = patch elérhető, de nincs aktív tömeges kihasználás
                   info     = általános figyelmeztetés, trendek, tanácsok
    "tags"     – JSON tömb, 1-3 elem, CSAK ezekből választhatsz:
                   "wordpress", "plugin", "theme", "server", "apache", "nginx",
                   "php", "mysql", "linux", "windows", "network", "email",
                   "browser", "cdn", "hosting", "general"
    "source"   – forrás neve (pl. "Bleeping Computer", "CISA", "CVE Database")
- Válaszolj KIZÁRÓLAG érvényes JSON tömbként, semmi más szöveg nélkül!

Példa formátum:
[{{
  "num":"01",
  "title":"Kritikus WordPress plugin sebezhetőség",
  "body":"A Contact Form 7 plugin 5.9.5-ös verziója előtt aktív RCE sebezhetőséget (CVE-2025-1234) találtak, amelyet már aktívan kihasználnak automatizált szkriptekkel.",
  "action":"Frissítsd a Contact Form 7 plugint azonnal 5.9.6-ra. Ha nem tudod, ideiglenesen deaktivítsd a Bővítmények menüben.",
  "severity":"critical",
  "tags":["wordpress","plugin"],
  "source":"Bleeping Computer"
}}]"""

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
        f"- {a['title']} | {a['desc'][:200]}" for a in articles[:15]
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
        "max_tokens": 2200 if category_id == "tech" else 1400,
        "temperature": 0.3,
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


# ── Tech badge segédfüggvények ─────────────────────────────────────────────────

SEVERITY_STYLE = {
    "critical": ("⚠ KRITIKUS", "#7b1a1a", "#fff",   "#c0392b"),
    "medium":   ("▲ KÖZEPES",  "#5a3a00", "#fff",   "#b8860b"),
    "info":     ("● INFO",     "#1a3a1a", "#fff",   "#2d6a4f"),
}

TAG_STYLE = {
    "wordpress": ("#fcebeb", "#791f1f", "WordPress"),
    "plugin":    ("#fcebeb", "#791f1f", "plugin"),
    "theme":     ("#faeeda", "#633806", "téma"),
    "server":    ("#e6f1fb", "#0c447c", "szerver"),
    "apache":    ("#e6f1fb", "#0c447c", "Apache"),
    "nginx":     ("#e6f1fb", "#0c447c", "Nginx"),
    "php":       ("#e6f1fb", "#0c447c", "PHP"),
    "mysql":     ("#e6f1fb", "#0c447c", "MySQL"),
    "linux":     ("#eaf3de", "#27500a", "Linux"),
    "windows":   ("#eaf3de", "#27500a", "Windows"),
    "network":   ("#eaf3de", "#27500a", "hálózat"),
    "email":     ("#faeeda", "#633806", "email"),
    "browser":   ("#faeeda", "#633806", "böngésző"),
    "cdn":       ("#eaf3de", "#27500a", "CDN"),
    "hosting":   ("#e6f1fb", "#0c447c", "hosting"),
    "general":   ("#f1efe8", "#444441", "általános"),
}

def _severity_badge(severity):
    label, bg_text, fg, bg = SEVERITY_STYLE.get(severity, SEVERITY_STYLE["info"])
    return (
        f'<span style="display:inline-block;background:{bg};color:{fg};'
        f'font-size:10px;font-weight:700;letter-spacing:0.5px;padding:2px 7px;'
        f'border-radius:3px;margin-right:6px;vertical-align:middle">{label}</span>'
    )

def _tag_badge(tag):
    bg, color, label = TAG_STYLE.get(tag, ("#f1efe8", "#444441", tag))
    return (
        f'<span style="display:inline-block;background:{bg};color:{color};'
        f'font-size:10px;padding:2px 6px;border-radius:3px;'
        f'margin-right:4px;vertical-align:middle">{label}</span>'
    )

def _tech_news_row(item, color):
    severity   = item.get("severity", "info")
    tags       = item.get("tags", [])
    action     = item.get("action", "")
    body       = item.get("body", "")
    title      = item.get("title", "")
    source     = item.get("source", "Google News")
    num        = item.get("num", "")

    sev_badge  = _severity_badge(severity)
    tag_badges = "".join(_tag_badge(t) for t in tags)

    # Teendő sáv csak ha van tartalom
    action_block = ""
    if action:
        action_block = (
            f'<div style="background:#f0f4f0;border-left:3px solid #2d6a4f;'
            f'padding:6px 10px;margin-top:8px;font-size:12px;color:#1a3a1a;'
            f'font-family:Georgia,serif;line-height:1.5;">'
            f'<strong>Teendő:</strong> {action}</div>'
        )

    return f"""
    <tr>
      <td style="width:28px;font-family:Georgia,serif;font-size:13px;color:{color};opacity:0.5;vertical-align:top;padding:14px 6px 14px 0">{num}</td>
      <td style="padding:14px 0;border-bottom:1px solid #e8e2d5;">
        <div style="margin-bottom:6px">{sev_badge}{tag_badges}</div>
        <strong style="font-family:Georgia,serif;font-size:14px;color:#1a1209">{title}</strong><br>
        <span style="font-family:Georgia,serif;font-size:13px;line-height:1.65;color:#2a2015">{body}</span>
        {action_block}
        <span style="display:block;font-size:11px;color:#999;font-style:italic;margin-top:6px">Forrás: {source}</span>
      </td>
    </tr>"""


def build_html(data):
    cats_html = ""
    for cat in data["categories"]:
        cid   = cat["id"]
        color = CAT_COLORS.get(cid, "#333333")
        icon  = ICONS.get(cid, "●")
        is_tech = (cid == "tech")

        news_rows = ""
        for item in cat.get("news", []):
            if is_tech:
                news_rows += _tech_news_row(item, color)
            else:
                news_rows += f"""
                <tr>
                  <td style="width:28px;font-family:Georgia,serif;font-size:13px;color:{color};opacity:0.5;vertical-align:top;padding:12px 6px 12px 0">{item['num']}</td>
                  <td style="padding:12px 0;border-bottom:1px solid #e8e2d5;font-family:Georgia,serif;font-size:14px;line-height:1.65;color:#2a2015">
                    <strong>{item.get('title', '')}</strong><br>
                    {item.get('body', '')}
                    <span style="display:block;font-size:11px;color:#999;font-style:italic;margin-top:4px">Forrás: {item.get('source', 'Google News')}</span>
                  </td>
                </tr>"""

        # Tech kategóriánál badge-magyarázó a fejléc alá
        legend_block = ""
        if is_tech:
            legend_block = """
            <tr><td style="padding:8px 32px 4px;background:#f0f4f0;font-size:10px;color:#5a7a5a;font-family:Georgia,serif;letter-spacing:0.5px;">
              <span style="background:#c0392b;color:#fff;padding:1px 5px;border-radius:3px;font-size:9px;margin-right:6px">⚠ KRITIKUS</span> azonnali beavatkozás &nbsp;·&nbsp;
              <span style="background:#b8860b;color:#fff;padding:1px 5px;border-radius:3px;font-size:9px;margin-right:6px">▲ KÖZEPES</span> frissítsd hamarosan &nbsp;·&nbsp;
              <span style="background:#2d6a4f;color:#fff;padding:1px 5px;border-radius:3px;font-size:9px;margin-right:6px">● INFO</span> érdemes tudni
            </td></tr>"""

        cats_html += f"""
        <tr><td colspan="2" style="padding:0">
          <table width="100%" cellpadding="0" cellspacing="0">
            <tr><td style="background:{color};padding:16px 32px;font-family:Georgia,serif">
              <span style="font-size:22px">{icon}</span>
              <span style="font-size:20px;font-weight:700;color:#fff;margin-left:12px">{cat['title']}</span>
              <span style="float:right;font-size:11px;color:rgba(255,255,255,0.6);letter-spacing:2px;padding-top:4px">10 HÍR</span>
            </td></tr>
            {legend_block}
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
