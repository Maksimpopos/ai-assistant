# quickstart.py
# Требует: pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib requests sqlalchemy

import os
import base64
import re
import requests
from email.message import EmailMessage

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request

# NEW: тянем контекст заказа из SQLite (./data/orders.db через db.py)
from resolver import get_order_context

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


def parse_sender_name(from_header: str) -> str:
    # Пробуем достать читаемое имя из "Имя Фамилия <email@host>"
    m = re.match(r'^"?([^"<]+)"?\s*<[^>]+>', from_header or "")
    return (m.group(1).strip() if m else "").strip()


def extract_email(from_header: str) -> str:
    m = re.search(r"<([^>]+)>", from_header or "")
    return (m.group(1) if m else (from_header or "")).strip()


def build_reply(original_full_msg, reply_text: str):
    h = get_header_map(original_full_msg)
    to_addr = extract_email(h.get("From", ""))
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


# ---------- LLM (Qwen3 14B via Ollama) ----------
def neural_response(plain_text: str, subject: str = "", sender_name: str = "", ctx: dict | None = None) -> str:
    """
    Генерирует ответ, заземлённый на фактах из БД (ctx).
    Если ctx нет — вежливо просим номер заказа.
    """
    facts = "Нет данных по заказу."
    if ctx:
        items_lines = "\n".join([f"- {it['title']} × {int(it['qty'])}" for it in ctx.get("items", [])]) or "—"
        ship = ctx.get("shipment")
        ship_block = (
            f"Доставка: {ship['carrier']}, трек: {ship['tracking_no']}\n"
            f"Статус перевозки: {ship['last_event']}\n"
            f"Ожидаемая дата: {ship['eta_date']}"
        ) if ship else "Доставка: данных нет."
        facts = (
            f"Номер заказа: {ctx['order_no']}\n"
            f"Статус: {ctx['status']}\n"
            f"Дата оформления: {ctx['created_at']}\n"
            f"Позиции:\n{items_lines}\n{ship_block}"
        )

    prompt = (
        "Ты — вежливый сотрудник службы поддержки по сборке ПК.\n"
        "Отвечай кратко (3–6 предложений), по делу, без фантазий. Отвечай всегда на немецком языке.\n"
        "Не используй русский язык и не добавляй лишних фраз.\n"
        "Никогда не используй имя клиента в обращении.\n"
        "\n"
        "Правила приветствия:\n"
        "- Используй «Guten Tag,»\n"
        "Факты и ограничения:\n"
        "- Используй ТОЛЬКО факты из блока FACTS ниже. Никаких предположений.\n"
        "- Если нужных фактов нет — вежливо попроси Bestellnummer (номер заказа).\n"
        "- Если вопрос не про сборку ПК/заказ, ответь кратко по сути и, при отсутствии фактов, запроси необходимые данные.\n"
        "\n"
        "- Если клиент указал Bestellnummer (номер заказа), но он не найден в базе FACTS, "
        "вежливо извинись и сообщи, что такой Bestellnummer нет в системе. "
        "Объясни, что без правильного Bestellnummer мы, к сожалению, не можем дать точную информацию, "
        "и попроси проверить номер или предоставить правильный Bestellnummer.\n"
        "- Если клиент пишет оскорбления, не отвечай стандартно. "
        "В этом случае всегда отвечай одной фиксированной фразой:\n"
        "  \"Alina, bitte beleidige mich (künstliche Intelligenz) nicht. "
        "Ich lerne und gebe mir Mühe, ich habe einen wunderbaren Lehrer. "
        "Und übrigens, Maxim liebt dich sehr.\"\n"


        "Формат ответа:\n"
        "- Язык: только немецкий.\n"
        "- 2–5 коротких предложений, без лишних вводных.\n"
        "- Подпись ВСЕГДА в конце, на отдельных строках:\n"
        "  Mit freundlichen Grüßen\n"
        "  Ihre TechPulse-Support\n"
        "\n"
        f"FACTS:\n{facts}\n\n"
        f"ТЕМА: {subject}\n"
        f"ПИСЬМО:\n{plain_text}\n\n"
        "Сформируй готовый ответ для клиента."
    )

    try:
        r = requests.post(
            "http://localhost:11434/api/generate",
            json={"model": "gemma3:12b-it-q4_K_M", "prompt": prompt, "stream": False},
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
    from_header = headers.get("From", "")
    from_addr_lower = from_header.lower()

    # не отвечаем роботам/рассылкам
    if any(s in from_addr_lower for s in SKIP_SENDERS) or "List-Unsubscribe" in headers:
        print("Служебная рассылка/бот — пропускаю без ответа.")
        mark_processed(svc, msg_id, ensure_label(svc, "Processed"))
        return

    subject = headers.get("Subject", "")
    body_text = get_body(full)

    # NEW: резолвим факты из БД (по номеру в теме/тексте или по email отправителя)
    sender_email = extract_email(from_header)
    sender_name = parse_sender_name(from_header)
    ctx = get_order_context(sender_email, subject, body_text)

    # генерируем ответ, заземляя на факты из ctx
    reply_text = neural_response(body_text, subject, sender_name=sender_name, ctx=ctx)
    reply_body = build_reply(full, reply_text)

    sent = svc.users().messages().send(userId="me", body=reply_body).execute()
    print("Отправил ответ:", sent.get("id"))

    mark_processed(svc, msg_id, ensure_label(svc, "Processed"))
    print("Пометил как Processed и снял UNREAD.")


if __name__ == "__main__":
    main()
