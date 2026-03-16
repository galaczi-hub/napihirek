#!/usr/bin/env python3
"""
Europai Hirlap – Napi automatikus kuldo
NewsAPI (valos hirek) + Groq llama (magyar forditas) - INGYENES
Javított verzió 2026-ra (kezeli a [Removed] cikkeket és üres válaszokat)
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

# KONFIGURÁCIÓ
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()
NEWS_API_KEY = os.environ.get("NEWS_API_KEY", "").strip()
GMAIL_USER = os.environ.get("GMAIL_USER", "galaczi.usa@gmail.com").strip()
GMAIL_APP_PASS = os.environ.get("GMAIL_APP_PASS", "").strip()
TO_EMAILS = ["galaczi.usa@gmail.com", "kata.gorcsi@gmail.com"]

ICONS = {"econ": "📈", "eu": "🇪🇺", "war": "⚔️", "spain": "🇪🇸"}
CAT_COLORS = {"econ": "#1a4a6b", "eu": "#2d6a4f", "war": "#7b2d2d", "spain": "#8B0000"}

def fetch_articles(query, language="en", page_size=10):  # ↑ page_size 8→10, több esély
    """NewsAPI-tól lekér cikkeket – lazább szűrő"""
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
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        results = []
        for a in data.get("articles", []):
            title = (a.get("title") or "").strip()
            desc = (a.get("description") or "").strip()
            source = a.get("source", {}).get("name", "Ismeretlen forrás")
            url = a.get("url", "#")

            # Ha title [Removed] vagy üres → description-ből mentünk ha van
            if "[Removed]" in title or not title:
                if desc:
                    title = desc[:80] + "..." if len(desc) > 80 else desc
                else:
                    continue  # mindkettő hiányzik → skip

            results.append({"title": title, "desc": desc[:250], "source": source, "url": url})
        print(f"[{query}] Letöltve {len(results)} cikk (nyelv: {language})")
        return results
    except Exception as e:
        print(f"NewsAPI hiba ({query}): {e}")
        return []

def fetch_all_news():
    print("NewsAPI hírek letöltése...")
    return {
        "econ": fetch_articles("european stock market economy finance OR euribor OR ECB", page_size=10),
        "eu": fetch_articles("European Union EU politics Brussels OR von der Leyen OR EU Commission", page_size=10),
        "war": fetch_articles("Ukraine war conflict Middle East OR Gaza OR Israel OR Russia Ukraine", page_size=10),
        "spain": fetch_articles("Spain España politics economy OR Sánchez OR PP OR Vox", language="es", page_size=10),
    }

def summarize_with_groq(articles, category_name, date_str):
    """Groq összefoglaló – rugalmasabb prompt"""
    if not articles:
        return [{"num": "01", "title": f"Nincs friss hír a(z) {category_name} kategóriában", "body": "Ma nem érkezett releváns cikk.", "source": "NewsAPI"}]

    articles_text = "\n".join([
        f"- {a['title']} | {a['desc']} | Forrás: {a['source']}"
        for a in articles
    ])

    prompt = f"""Mai hírek alapján készíts **legfeljebb 5**, de lehetőleg 3-5 db magyar nyelvű hírösszefoglalót a "{category_name}" kategóriához.
Dátum: {date_str}

Hírek:
{articles_text}

Szabályok:
- Legfeljebb 5 tétel (ha kevesebb releváns van, kevesebbet adj vissza)
- Minden tétel: rövid, figyelemfelkeltő magyar cím + 2 mondatos magyar összefoglaló + forrás neve
- Legyenek pontosak, ne találj ki semmit
- Válaszolj **KIZÁRÓLAG** valid JSON tömbként, semmi mással:
[{{"num":"01","title":"Magyar cím","body":"Két mondatos összefoglaló magyarul.","source":"Reuters"}}]
Csak a JSON tömböt add vissza!"""

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 1800,
        "temperature": 0.4,
    }

    for attempt in range(4):
        try:
            resp = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers=headers, json=payload, timeout=70
            )
            resp.raise_for_status()
            text = resp.json()["choices"][0]["message"]["content"].strip()

            # Jobb clean-olás
            text = re.sub(r'^```json\s*|\s*```$', '', text).strip()
            text = re.sub(r'\\n', '\n', text)

            # JSON keresés robusztusabban
            start = text.find('[')
            end = text.rfind(']') + 1
            if start == -1 or end <= start:
                print("Groq nem adott JSON-t:\n", text[:300])
                continue

            clean_json = text[start:end]
            result = json.loads(clean_json)

            print(f"Groq sikeres: {len(result)} elem a '{category_name}' kategóriában")
            return result[:5]  # biztonsági max 5

        except Exception as e:
            print(f"Groq hiba ({attempt+1}/4) [{category_name}]: {e}")
            if attempt < 3:
                import time
                time.sleep(12 + attempt * 5)  # exponenciális backoff

    # Ha minden próbálkozás elbukott
    return [{"num": "01", "title": f"Hiba az összefoglaló készítésekor ({category_name})", "body": "Próbáld újra később vagy ellenőrizd az API kulcsokat.", "source": "Rendszer"}]

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
            time.sleep(10)  # rate limit védelem
        news_items = summarize_with_groq(raw[cid], ctitle, date_str)
        for i, item in enumerate(news_items):
            item["num"] = str(i+1).zfill(2)
        categories.append({"id": cid, "title": ctitle, "news": news_items})
    return {"date": date_str, "categories": categories}

# build_html és send_email változatlan, de hozzáadtam fallback-et
def build_html(data):
    cats_html = ""
    for cat in data["categories"]:
        cid = cat["id"]
        color = CAT_COLORS.get(cid, "#333333")
        icon = ICONS.get(cid, "●")
        news_rows = ""
        news_list = cat.get("news", [])
        if not news_list:
            news_rows = '<tr><td colspan="2" style="padding:20px;text-align:center;color:#777;">Nincs elérhető hír ezen a napon ebben a kategóriában.</td></tr>'
        else:
            for item in news_list:
                news_rows += f"""
                <tr>
                  <td style="width:28px;font-family:Georgia,serif;font-size:13px;color:{color};opacity:0.5;vertical-align:top;padding:12px 6px 12px 0">{item['num']}</td>
                  <td style="padding:12px 0;border-bottom:1px solid #e8e2d5;font-family:Georgia,serif;font-size:14px;line-height:1.65;color:#2a2015">
                    <strong>{item['title']}</strong><br>
                    {item['body']}
                    <span style="display:block;font-size:11px;color:#999;font-style:italic;margin-top:4px">Forrás: {item['source']}</span>
                  </td>
                </tr>"""

        cats_html += f"""
        <tr><td colspan="2" style="padding:0">
          <table width="100%" cellpadding="0" cellspacing="0">
            <tr><td style="background:{color};padding:16px 32px;font-family:Georgia,serif">
              <span style="font-size:22px">{icon}</span>
              <span style="font-size:20px;font-weight:700;color:#fff;margin-left:12px">{cat['title']}</span>
              <span style="float:right;font-size:11px;color:rgba(255,255,255,0.6);letter-spacing:2px;padding-top:4px">Hírek száma: {len(news_list) if news_list else 0}</span>
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
    <div style="font-size:38px;font-weight:900;color:#f5f0e8">Europai<span style="color:#b8922a"> Hírlap</span></div>
    <div style="color:#8a7d68;font-size:10px;letter-spacing:4px;text-transform:uppercase;margin-top:8px">Minden reggel · Minden ami számít</div>
    <div style="color:#c5b99a;font-size:13px;font-style:italic;border-top:1px solid #3d3428;padding-top:10px;margin-top:10px">{data['date']} · Reggeli kiadás · 09:00 CET</div>
  </td></tr>
  <tr><td colspan="2" style="background:#b8922a;padding:8px 40px;font-size:10px;letter-spacing:3px;text-transform:uppercase;color:#1a1209;text-align:center;font-weight:700">
    4 KATEGÓRIA · FRISS HÍREK
  </td></tr>
  {cats_html}
  <tr><td colspan="2" style="background:#1a1209;padding:18px 40px;text-align:center">
    <p style="color:#5a5040;font-size:10px;line-height:1.9;margin:0">
      <span style="color:#b8922a;font-weight:700">Europai Hírlap</span> · NewsAPI + Groq AI<br>
      Minden nap 09:00 CET · galaczi.usa@gmail.com
    </p>
  </td></tr>
</table>
</body></html>"""

# send_email változatlan
def send_email(html_content, date_str):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Europai Hírlap – {date_str}"
    msg["From"] = GMAIL_USER
    msg["To"] = ", ".join(TO_EMAILS)
    msg.attach(MIMEText(html_content, "html", "utf-8"))
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_USER, GMAIL_APP_PASS)
            server.sendmail(GMAIL_USER, TO_EMAILS, msg.as_string())
        print(f"Email elküldve: {', '.join(TO_EMAILS)}")
    except Exception as e:
        print(f"Email küldés hiba: {e}\n{traceback.format_exc()}")

def run():
    today = datetime.date.today()
    days = ["hétfő", "kedd", "szerda", "csütörtök", "péntek", "szombat", "vasárnap"]
    months = ["január", "február", "március", "április", "május", "június",
              "július", "augusztus", "szeptember", "október", "november", "december"]
    date_str = f"{today.year}. {months[today.month-1]} {today.day}., {days[today.weekday()]}"
    print(f"Hírek összegyűjtése: {date_str}")
    news_data = get_news(date_str)
    html_email = build_html(news_data)
    send_email(html_email, date_str)

if __name__ == "__main__":
    run()
