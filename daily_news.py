#!/usr/bin/env python3
"""
Europai Hirlap – Napi automatikus kuldo (Groq verzio - INGYENES)
Minden reggel 09:00 CET lefut, lekeri az aktualis hireket
Groq API-n keresztul, es elkuldei HTML emailben.
"""

import os
import json
import re
import smtplib
import datetime
import requests
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# KONFIGURÁCIÓ
GROQ_API_KEY   = os.environ.get("GROQ_API_KEY", "").strip()
GMAIL_USER     = os.environ.get("GMAIL_USER", "galaczi.usa@gmail.com").strip()
GMAIL_APP_PASS = os.environ.get("GMAIL_APP_PASS", "").strip()
TO_EMAILS      = ["galaczi.usa@gmail.com", "gorcsi.kata@gmail.com"]

SYSTEM_PROMPT = """
Te egy professzionalis europai hirszerkeszto vagy. A feladatod:
minden nap reggel osszegyujtod a legfrissebb hireket fontos europai
hircsatornabol (Reuters, CNBC, BBC, Euronews, Al Jazeera, Financial Times,
Der Spiegel, Le Monde, La Vanguardia, El Pais, El Mundo, RTVE stb.),
leforditod magyarra, es NEGY kategoriban pontosan 10-10 rovid
hiroszefoglalot keszitesz (2 mondatonkent).

Kategoriak:
1. Gazdasag Tozsdei hirek (europai tozsdek, makrogazdasag, ceges hirek)
2. EU Europai Kozosseg (EU intezmenyek, politika, bovites, valasztasok)
3. Haborus Hirek (Ukrajna, Kozel-Kelet, egyeb konfliktusok)
4. Spanyol Hirek (KIZAROLAG spanyolorszagi hirek: belpolitika, gazdasag, kultura, sport, tarsadalom)

Minden hirhez adj: rovid cim, 2 mondatos osszefoglalo, forras nev.

Valaszolj KIZAROLAG valid JSON formatumban, semmi mas szoveg:
{"date":"DATUM","categories":[{"id":"econ","title":"Gazdasag Tozsdei Hirek","news":[{"num":"01","title":"Cim","body":"Osszefoglalo mondat.","source":"Reuters"}]},{"id":"eu","title":"EU Europai Kozosseg","news":[{"num":"01","title":"Cim","body":"Osszefoglalo.","source":"Euronews"}]},{"id":"war","title":"Haborus Hirek","news":[{"num":"01","title":"Cim","body":"Osszefoglalo.","source":"BBC"}]},{"id":"spain","title":"Spanyol Hirek","news":[{"num":"01","title":"Cim","body":"Osszefoglalo.","source":"El Pais"}]}]}

Pontosan 10 hirt adj minden kategoriban. CSAK JSON, semmi mas.
"""

ICONS      = {"econ":"📈","eu":"🇪🇺","war":"⚔️","spain":"🇪🇸"}
CAT_COLORS = {"econ":"#1a4a6b","eu":"#2d6a4f","war":"#7b2d2d","spain":"#8B0000"}


def get_news_from_groq(date_str):
    user_prompt = f"""
    Ma van: {date_str}
    Keresd meg a mai legfrissebb hireket es allitsd ossze a napi hirlevelet JSON formatumban.
    Keress aktivan:
    - European stock markets today
    - EU politics news today
    - Ukraine war news today
    - Middle East conflict today
    - Spain news today noticias espana hoy
    """

    payload = {
        "model": "openai/gpt-oss-120b",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user_prompt}
        ],
        "tools": [{"type": "browser_search"}],
        "tool_choice": "required",
        "max_completion_tokens": 8000,
        "temperature": 1,
    }

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    response = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers=headers,
        json=payload,
        timeout=180
    )
    response.raise_for_status()
    data = response.json()

    message = data["choices"][0]["message"]
    full_text = message.get("content", "") or ""

    print(f"Response length: {len(full_text)} chars")
    print(f"First 300 chars: {full_text[:300]}")

    clean = re.sub(r"```json|```", "", full_text).strip()
    start = clean.find("{")
    end   = clean.rfind("}") + 1
    if start >= 0 and end > start:
        clean = clean[start:end]

    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        last = clean.rfind('"}')
        if last > 0:
            try:
                return json.loads(clean[:last+2] + "]}]}")
            except Exception:
                pass
        raise


def build_html(data):
    cats_html = ""
    for cat in data["categories"]:
        cid   = cat["id"]
        color = CAT_COLORS.get(cid, "#333333")
        icon  = ICONS.get(cid, "●")
        news_rows = ""
        for item in cat.get("news", []):
            news_rows += f"""
            <tr>
              <td style="width:28px;font-family:Georgia,serif;font-size:13px;color:{color};opacity:0.5;vertical-align:top;padding:12px 6px 12px 0">{item['num']}</td>
              <td style="padding:12px 0;border-bottom:1px solid #e8e2d5;font-family:Georgia,serif;font-size:14px;line-height:1.65;color:#2a2015">
                <strong>{item['title']}</strong><br>
                {item['body']}
                <span style="display:block;font-size:11px;color:#999;font-style:italic;margin-top:4px">Forras: {item['source']}</span>
              </td>
            </tr>"""
        cats_html += f"""
        <tr><td colspan="2" style="padding:0">
          <table width="100%" cellpadding="0" cellspacing="0">
            <tr><td style="background:{color};padding:16px 32px;font-family:Georgia,serif">
              <span style="font-size:22px">{icon}</span>
              <span style="font-size:20px;font-weight:700;color:#fff;margin-left:12px">{cat['title']}</span>
              <span style="float:right;font-size:11px;color:rgba(255,255,255,0.6);letter-spacing:2px;padding-top:4px">10 HIR</span>
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
    <div style="font-size:38px;font-weight:900;color:#f5f0e8">Europai<span style="color:#b8922a"> Hirlap</span></div>
    <div style="color:#8a7d68;font-size:10px;letter-spacing:4px;text-transform:uppercase;margin-top:8px">Minden reggel · Minden ami szamit</div>
    <div style="color:#c5b99a;font-size:13px;font-style:italic;border-top:1px solid #3d3428;padding-top:10px;margin-top:10px">{data['date']} &nbsp;·&nbsp; Reggeli kiadas &nbsp;·&nbsp; 09:00 CET</div>
  </td></tr>
  <tr><td colspan="2" style="background:#b8922a;padding:8px 40px;font-size:10px;letter-spacing:3px;text-transform:uppercase;color:#1a1209;text-align:center;font-weight:700">
    4 KATEGORIA · 40 FRISS HIR
  </td></tr>
  {cats_html}
  <tr><td colspan="2" style="background:#1a1209;padding:18px 40px;text-align:center">
    <p style="color:#5a5040;font-size:10px;line-height:1.9;margin:0">
      <span style="color:#b8922a;font-weight:700">Europai Hirlap</span> · Groq AI (ingyenes)<br>
      Minden nap 09:00 CET · galaczi.usa@gmail.com
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
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_USER, GMAIL_APP_PASS)
        server.sendmail(GMAIL_USER, TO_EMAILS, msg.as_string())
    print(f"Email elkuldve: {', '.join(TO_EMAILS)}")


def run():
    today  = datetime.date.today()
    days   = ["hetfo","kedd","szerda","csutortok","pentek","szombat","vasarnap"]
    months = ["januar","februar","marcius","aprilis","majus","junius",
              "julius","augusztus","szeptember","oktober","november","december"]
    date_str = f"{today.year}. {months[today.month-1]} {today.day}., {days[today.weekday()]}"
    print(f"Hirek osszegyujtese: {date_str}")
    news_data  = get_news_from_groq(date_str)
    html_email = build_html(news_data)
    send_email(html_email, date_str)


if __name__ == "__main__":
    run()
