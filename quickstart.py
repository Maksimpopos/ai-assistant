# quickstart.py
# Требует: pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib requests

import os
import base64
import re
import requests
from email.message import EmailMessage

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]
SKIP_SENDERS = ("noreply", "no-reply", "mailer-daemon")

# ---------- Gmail auth ----------
def get_service():
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("client_secret.json", SCOPES)
            creds = flow.run_local_server(port=0)
        with open("token.json", "w") as f:
            f.write(creds.to_json())
    return build("gmail", "v1", credentials=creds)

# ---------- Helpers ----------
def get_header_map(msg):
    return {h["name"]: h["value"] for h in msg["payload"].get("headers", [])}

def _find_text_parts(payload):
    # обходит multipart и достаёт text/plain (если есть)
    if "parts" in payload:
        for p in payload["parts"]:
            yield from _find_text_parts(p)
    else:
        if payload.get("mimeType", "").startswith("text/plain") and "data" in payload.get("body", {}):
            yield payload["body"]["data"]

def get_body(msg) -> str:
    # сначала пытаемся достать text/plain
    for data in _find_text_parts(msg["payload"]):
        try:
            return base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
        except Exception:
            pass
    # фоллбэк: иногда текст лежит прямо в body
    data = msg["payload"].get("body", {}).get("data")
    if data:
        return base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
    return ""

def build_reply(original_full_msg, reply_text: str):
    h = get_header_map(original_full_msg)
    # достаём чистый email из поля From
    m = re.search(r"<([^>]+)>", h.get("From", ""))
    to_addr = m.group(1) if m else h.get("From", "")
    subj = h.get("Subject", "")
    if not subj.lower().startswith("re:"):
        subj = "Re: " + subj
    msg_id = h.get("Message-Id") or h.get("Message-ID")

    em = EmailMessage()
    em["To"] = to_addr
    em["Subject"] = subj
    if msg_id:
        em["In-Reply-To"] = msg_id
        em["References"] = msg_id
    em.set_content(reply_text)

    raw = base64.urlsafe_b64encode(em.as_bytes()).decode("utf-8")
    return {"raw": raw, "threadId": original_full_msg.get("threadId")}

def ensure_label(svc, name="Processed"):
    labels = svc.users().labels().list(userId="me").execute().get("labels", [])
    for lb in labels:
        if lb["name"] == name:
            return lb["id"]
    created = svc.users().labels().create(
        userId="me",
        body={"name": name, "labelListVisibility": "labelShow", "messageListVisibility": "show"},
    ).execute()
    return created["id"]

def mark_processed(svc, msg_id, label_id):
    svc.users().messages().modify(
        userId="me",
        id=msg_id,
        body={"removeLabelIds": ["UNREAD"], "addLabelIds": [label_id]},
    ).execute()

# ---------- LLM (LLaMA 3 8B via Ollama) ----------
def neural_response(plain_text: str, subject: str = "") -> str:
    prompt = (
        "Ты — вежливый сотрудник службы поддержки по сборке ПК. "
        "Отвечай кратко (2–5 предложений), по делу, без фантазий. "
        "Пиши на языке письма (DE/RU/EN). Если нет номера заказа — вежливо попроси его. "
        "Не обещай точные сроки, если их нет.\n\n"
        f"ТЕМА: {subject}\n"
        f"ПИСЬМО:\n{plain_text}\n\n"
        "Сформируй готовый ответ для клиента."
    )
    try:
        r = requests.post(
            "http://localhost:11434/api/generate",
            json={"model": "llama3:8b", "prompt": prompt, "stream": False},
            timeout=30,
        )
        text = r.json().get("response", "").strip()
        return text if text else "Спасибо! Получили ваше письмо. Подскажите номер заказа — проверим статус и ответим по сути."
    except Exception as e:
        print("LLM error:", e)
        return "Спасибо! Получили ваше письмо. Подскажите номер заказа — проверим статус и ответим по сути."

# ---------- Main ----------
def main():
    svc = get_service()

    # берём одно непрочитанное из INBOX
    res = svc.users().messages().list(userId="me", labelIds=["INBOX"], q="is:unread", maxResults=1).execute()
    msgs = res.get("messages", [])
    if not msgs:
        print("Нет непрочитанных писем.")
        return

    msg_id = msgs[0]["id"]
    full = svc.users().messages().get(userId="me", id=msg_id, format="full").execute()

    headers = get_header_map(full)
    from_addr = headers.get("From", "").lower()
    # не отвечаем роботам/рассылкам
    if any(s in from_addr for s in SKIP_SENDERS) or "List-Unsubscribe" in headers:
        print("Служебная рассылка/бот — пропускаю без ответа.")
        mark_processed(svc, msg_id, ensure_label(svc, "Processed"))
        return

    subject = headers.get("Subject", "")
    body_text = get_body(full)

    reply_text = neural_response(body_text, subject)
    reply_body = build_reply(full, reply_text)

    sent = svc.users().messages().send(userId="me", body=reply_body).execute()
    print("Отправил ответ:", sent.get("id"))

    mark_processed(svc, msg_id, ensure_label(svc, "Processed"))
    print("Пометил как Processed и снял UNREAD.")

if __name__ == "__main__":
    main()
