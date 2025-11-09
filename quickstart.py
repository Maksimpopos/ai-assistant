# quickstart.py — доставка: поддержка тредов без ключевых слов
import os
import base64
import re
import requests
from email.message import EmailMessage

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request

from resolver import get_order_context

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]
SKIP_SENDERS = ("noreply", "no-reply", "mailer-daemon")

# Лейблы и поведение
NON_DELIVERY_LABEL = "Skipped-NonDelivery"
DELIVERY_HANDLED_LABEL = "Delivery-Handled"
DELIVERY_THREAD_LABEL = "Delivery-Conversation"
KEEP_UNREAD_FOR_NON_DELIVERY = True  # нерелевантные письма не помечаем прочитанными

# Ключевые фразы «вопрос о доставке» (DE/EN)
DELIVERY_PATTERNS = [
    r"\bwann\s+(kommt|erhalte|bekomme)\b",
    r"\bwo\s+(ist|bleibt)\s+(mein(e|) )?(paket|bestellung)\b",
    r"\bbestell(status|ung.*(nicht|noch)\s*angekommen)\b",
    r"\bliefer(status|termin|zeit|datum|verzögerung|verspätung)\b",
    r"\bversand(status|t)?\b",
    r"\bsendungsverfolgung\b|\bsendungsnummer\b",
    r"\bzustellung\b|\bankunft\b",
    r"\btracking(\s*nummer|\s*id)?\b",
    r"\b(dhl|hermes|dpd|gls|ups|fedex|deutsche\s*post)\b",
    r"\bwhere\s+is\s+my\s+(order|package)\b",
    r"\bwhen\s+will\s+it\s+arrive\b",
    r"\bexpected\s+delivery\b",
    r"\b(delivery|shipping)\s+status\b",
]
def is_delivery_question(text: str) -> bool:
    t = (text or "").lower()
    return any(re.search(p, t) for p in DELIVERY_PATTERNS)

# ---------- PROMPT loader ----------
def load_prompt_template(path: str = "prompt.txt") -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return (
            "Du bist ein höflicher deutschsprachiger PC-Support-Assistent.\n"
            "Antworte kurz (3–6 Sätze), faktenbasiert. Wenn Daten fehlen, frage nach der Bestellnummer.\n"
            "Beende jede Antwort mit:\nMit freundlichen Grüßen\nIhre TechPulse-Support"
        )

PROMPT_TEMPLATE = load_prompt_template(os.environ.get("PROMPT_PATH", "prompt.txt"))

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
    if "parts" in payload:
        for p in payload["parts"]:
            yield from _find_text_parts(p)
    else:
        if payload.get("mimeType", "").startswith("text/plain") and "data" in payload.get("body", {}):
            yield payload["body"]["data"]

def get_body(msg) -> str:
    for data in _find_text_parts(msg["payload"]):
        try:
            return base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
        except Exception:
            pass
    data = msg["payload"].get("body", {}).get("data")
    if data:
        return base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
    return ""

def parse_sender_name(from_header: str) -> str:
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

def mark_with_label(svc, msg_id, label_name: str, keep_unread: bool = False):
    label_id = ensure_label(svc, label_name)
    body = {"addLabelIds": [label_id]}
    if not keep_unread:
        body["removeLabelIds"] = ["UNREAD"]
    svc.users().messages().modify(userId="me", id=msg_id, body=body).execute()

def thread_has_label(svc, thread_id: str, label_id: str) -> bool:
    th = svc.users().threads().get(userId="me", id=thread_id).execute()
    # labelIds лежат на каждом сообщении треда; считаем, что наличие на одном из них достаточно
    for m in th.get("messages", []):
        if label_id in m.get("labelIds", []):
            return True
    return False

def add_label_to_thread(svc, thread_id: str, label_name: str):
    lid = ensure_label(svc, label_name)
    svc.users().threads().modify(
        userId="me", id=thread_id, body={"addLabelIds": [lid]}
    ).execute()
    return lid

# ---------- LLM ----------
def neural_response(plain_text: str, subject: str = "", sender_name: str = "", ctx: dict | None = None) -> str:
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
        PROMPT_TEMPLATE
        + "\n\n"
        + f"FACTS:\n{facts}\n\n"
        + f"TEMA: {subject}\n"
        + f"PISMO:\n{plain_text}\n\n"
        + "Сформируй готовый ответ для клиента."
    )

    try:
        r = requests.post(
            "http://localhost:11434/api/generate",
            json={"model": "gemma3:12b-it-q4_K_M", "prompt": prompt, "stream": False},
            timeout=120,
        )
        text = r.json().get("response", "").strip()
        return text if text else "Danke! Bitte teilen Sie mir die Bestellnummer mit, dann prüfe ich den Lieferstatus."
    except Exception as e:
        print("LLM error:", e)
        return "Danke! Bitte teilen Sie mir die Bestellnummer mit, dann prüfe ich den Lieferstatus."

# ---------- Main ----------
def main():
    svc = get_service()

    # Берём все непрочитанные, чтобы ловить фоллоу-апы в активных тредах
    res = svc.users().messages().list(userId="me", q='is:unread in:inbox', maxResults=15).execute()
    msgs = res.get("messages", [])
    if not msgs:
        print("Нет непрочитанных писем.")
        return

    # Подготовим ID нужных лейблов (создадутся при отсутствии)
    non_delivery_id = ensure_label(svc, NON_DELIVERY_LABEL)
    handled_id = ensure_label(svc, DELIVERY_HANDLED_LABEL)
    delivery_thread_id = ensure_label(svc, DELIVERY_THREAD_LABEL)

    for m in msgs:
        msg_id = m["id"]
        full = svc.users().messages().get(userId="me", id=msg_id, format="full").execute()

        headers = get_header_map(full)
        from_header = headers.get("From", "")
        from_addr_lower = from_header.lower()

        # не отвечаем роботам/рассылкам
        if any(s in from_addr_lower for s in SKIP_SENDERS) or "List-Unsubscribe" in headers:
            print("[SKIP Bot/Mailing]", extract_email(from_header))
            # можно пометить и снять UNREAD:
            svc.users().messages().modify(
                userId="me", id=msg_id,
                body={"removeLabelIds": ["UNREAD"]}
            ).execute()
            continue

        subject = headers.get("Subject", "")
        body_text = get_body(full)
        thread_id = full.get("threadId")

        in_delivery_thread = thread_has_label(svc, thread_id, delivery_thread_id)

        # Фильтр: либо явный вопрос про доставку, либо это активный доставочный тред
        if not (in_delivery_thread or is_delivery_question(subject) or is_delivery_question(body_text)):
            print("[SKIP NonDelivery]", extract_email(from_header), "|", subject[:100])
            # Вешаем лейбл, UNREAD оставляем по настройке
            mark_with_label(svc, msg_id, NON_DELIVERY_LABEL, keep_unread=KEEP_UNREAD_FOR_NON_DELIVERY)
            continue

        # Резолвим факты из БД и формируем ответ
        sender_email = extract_email(from_header)
        sender_name = parse_sender_name(from_header)
        ctx = get_order_context(sender_email, subject, body_text)

        reply_text = neural_response(body_text, subject, sender_name=sender_name, ctx=ctx)
        reply_body = build_reply(full, reply_text)

        try:
            sent = svc.users().messages().send(userId="me", body=reply_body).execute()
            print("[REPLY Sent]", sent.get("id"))
        except Exception as e:
            print("[Send error]", e)
            # даже если не отправили — помечать тред “доставочным” не нужно
            continue

        # Помечаем: тред — как "Delivery-Conversation", письмо — как "Delivery-Handled"
        add_label_to_thread(svc, thread_id, DELIVERY_THREAD_LABEL)
        mark_with_label(svc, msg_id, DELIVERY_HANDLED_LABEL, keep_unread=False)

if __name__ == "__main__":
    main()


