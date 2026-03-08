#!/usr/bin/env python3
"""
Európai Hírlap – Napi automatikus küldő
Minden reggel 09:00 CET (08:00 UTC) lefut, lekéri az aktuális híreket
az Anthropic API-n keresztül, és elküldi HTML emailben.

Futtatás: python3 daily_news.py
Ütemezés: cron, GitHub Actions, vagy render.com free cron job

BEÁLLÍTÁSOK:
  1. pip install anthropic requests schedule smtplib
  2. Állítsd be a környezeti változókat (lásd lent)
  3. Futtasd, vagy tedd fel GitHub Actions-re (workflow lent)
"""

import os
import smtplib
import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import anthropic

# ── KONFIGURÁCIÓ ──────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")   # kötelező
GMAIL_USER        = os.environ.get("GMAIL_USER",  "galaczi.usa@gmail.com")
GMAIL_APP_PASS    = os.environ.get("GMAIL_APP_PASS", "")       # Google App Password
TO_EMAIL          = "galaczi.usa@gmail.com"
# ─────────────────────────────────────────────────────────


SYSTEM_PROMPT = """
Te egy professzionális európai hírszerkesztő vagy. A feladatod: 
minden nap reggel összegyűjtöd a legfrissebb híreket kb. 10 különböző
fontosabb európai hírcsatornából (Reuters, CNBC, BBC, Euronews, 
Al Jazeera, Financial Times, Der Spiegel, Le Monde, Corriere della Sera, 
La Vanguardia, stb.), lefordítod magyarra, és három kategóriában 
pontosan 10-10 rövid hírösszefoglalót készítesz (2 mondatonként).

Kategóriák:
1. 📈 Gazdaság & Tőzsde (európai tőzsdék, makrogazdaság, céges hírek)
2. 🇪🇺 EU & Európai Közösség (EU intézmények, politika, bővítés, választások)
3. ⚔️ Háborús Hírek (Ukrajna, Közel-Kelet, egyéb konfliktusok)

Minden hírhez adj: rövid cím (bold), 2 mondatos összefoglaló, forrás.

Válaszolj KIZÁRÓLAG valid JSON formátumban, semmi más:
{
  "date": "2026. március 8., vasárnap",
  "categories": [
    {
      "id": "econ",
      "icon": "📈",
      "title": "Gazdaság & Tőzsde",
      "news": [
        {"num": "01", "title": "Cím", "body": "Összefoglaló 2 mondat.", "source": "Reuters"},
        ...10 db...
      ]
    },
    {
      "id": "eu",
      "icon": "🇪🇺", 
      "title": "EU & Európai Közösség",
      "news": [...10 db...]
    },
    {
      "id": "war",
      "icon": "⚔️",
      "title": "Háborús Hírek", 
      "news": [...10 db...]
    }
  ]
}
"""

def get_news_from_claude(date_str: str) -> dict:
    """Lekéri a napi híreket Claude-tól web search segítségével."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    
    user_prompt = f"""
    Ma van: {date_str}
    
    Kérlek keresd meg a mai legfrissebb európai híreket és állítsd össze
    a napi hírlevelünket a megadott JSON formátumban.
    Keress aktívan: European stock markets today, EU news today, 
    Ukraine war today, Middle East conflict today – mind a mai dátummal.
    """
    
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4000,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}]
    )
    
    # Kigyűjti a szöveges választ
    full_text = ""
    for block in response.content:
        if hasattr(block, "text"):
            full_text += block.text
    
    import json, re
    # Tisztítja a JSON-t
    clean = re.sub(r"```json|```", "", full_text).strip()
    return json.loads(clean)


def build_html(data: dict) -> str:
    """Összerakja a HTML emailt a JSON adatokból."""
    
    cat_colors = {
        "econ": ("#1a4a6b", "#e8f0f7"),
        "eu":   ("#2d6a4f", "#e8f5ee"),
        "war":  ("#7b2d2d", "#f7e8e8"),
    }
    
    cats_html = ""
    for cat in data["categories"]:
        cid = cat["id"]
        color, bg = cat_colors.get(cid, ("#333", "#f5f5f5"))
        
        news_rows = ""
        for item in cat["news"]:
            news_rows += f"""
            <tr>
              <td style="width:28px;font-family:Georgia,serif;font-size:13px;
                         color:{color};opacity:0.5;vertical-align:top;
                         padding:12px 6px 12px 0">{item['num']}</td>
              <td style="padding:12px 0;border-bottom:1px solid #e8e2d5;
                         font-family:Georgia,serif;font-size:14px;
                         line-height:1.65;color:#2a2015">
                <strong>{item['title']}</strong><br>
                {item['body']}
                <span style="display:block;font-size:11px;color:#999;
                             font-style:italic;margin-top:4px">
                  Forrás: {item['source']}
                </span>
              </td>
            </tr>"""
        
        cats_html += f"""
        <tr>
          <td colspan="2" style="padding:0">
            <table width="100%" cellpadding="0" cellspacing="0">
              <tr>
                <td style="background:{color};padding:16px 32px;
                           font-family:Georgia,serif">
                  <span style="font-size:22px">{cat['icon']}</span>
                  <span style="font-size:20px;font-weight:700;color:#fff;
                               margin-left:12px">{cat['title']}</span>
                  <span style="float:right;font-size:11px;color:rgba(255,255,255,0.6);
                               letter-spacing:2px;padding-top:4px">10 HÍR</span>
                </td>
              </tr>
              <tr>
                <td style="padding:4px 32px 16px">
                  <table width="100%" cellpadding="0" cellspacing="0">
                    {news_rows}
                  </table>
                </td>
              </tr>
            </table>
          </td>
        </tr>
        <tr><td colspan="2" style="height:4px;background:repeating-linear-gradient(90deg,#e8e2d5 0,#e8e2d5 6px,transparent 6px,transparent 10px)"></td></tr>
        """
    
    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#2a2015;font-family:Georgia,serif">
<table width="680" cellpadding="0" cellspacing="0" align="center"
       style="background:#f5f0e8;margin:20px auto">
  <!-- MASTHEAD -->
  <tr>
    <td colspan="2" style="background:#1a1209;padding:28px 40px 20px;
                            text-align:center;border-bottom:4px solid #b8922a">
      <div style="font-size:38px;font-weight:900;color:#f5f0e8;letter-spacing:-1px">
        Európai<span style="color:#b8922a">&nbsp;Hírlap</span>
      </div>
      <div style="color:#8a7d68;font-size:10px;letter-spacing:4px;
                  text-transform:uppercase;margin-top:8px">
        Minden reggel · Minden ami számít
      </div>
      <div style="color:#c5b99a;font-size:13px;font-style:italic;
                  border-top:1px solid #3d3428;padding-top:10px;margin-top:10px">
        {data['date']} &nbsp;·&nbsp; Reggeli kiadás &nbsp;·&nbsp; 09:00 CET
      </div>
    </td>
  </tr>
  <tr>
    <td colspan="2" style="background:#b8922a;padding:8px 40px;
                            font-size:10px;letter-spacing:3px;
                            text-transform:uppercase;color:#1a1209;
                            text-align:center;font-weight:700">
      10 + 10 + 10 legfontosabb hír · 3 kategória
    </td>
  </tr>
  
  {cats_html}
  
  <!-- FOOTER -->
  <tr>
    <td colspan="2" style="background:#1a1209;padding:18px 40px;text-align:center">
      <p style="color:#5a5040;font-size:10px;letter-spacing:1px;line-height:1.9;margin:0">
        <span style="color:#b8922a;font-weight:700">Európai Hírlap</span>
        · Automatikusan generálva az Anthropic Claude által<br>
        Minden nap 09:00 CET · galaczi.usa@gmail.com
      </p>
    </td>
  </tr>
</table>
</body></html>"""


def send_email(html_content: str, date_str: str):
    """Gmail SMTP-n keresztül elküldi az emailt."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"📰 Európai Hírlap – {date_str}"
    msg["From"]    = GMAIL_USER
    msg["To"]      = TO_EMAIL
    
    msg.attach(MIMEText(html_content, "html", "utf-8"))
    
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_USER, GMAIL_APP_PASS)
        server.sendmail(GMAIL_USER, TO_EMAIL, msg.as_string())
    
    print(f"✅ Email elküldve: {TO_EMAIL}")


def run():
    today = datetime.date.today()
    hungarian_days = ["hétfő","kedd","szerda","csütörtök","péntek","szombat","vasárnap"]
    hungarian_months = ["január","február","március","április","május","június",
                        "július","augusztus","szeptember","október","november","december"]
    
    day_name  = hungarian_days[today.weekday()]
    month_str = hungarian_months[today.month - 1]
    date_str  = f"{today.year}. {month_str} {today.day}., {day_name}"
    
    print(f"🗞️  Hírek összegyűjtése: {date_str}")
    
    news_data  = get_news_from_claude(date_str)
    html_email = build_html(news_data)
    send_email(html_email, date_str)


if __name__ == "__main__":
    run()
