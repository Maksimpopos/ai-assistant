from __future__ import annotations
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request

import os, base64, re
from email.message import EmailMessage

# права: читать + отправлять + помечать
SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

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
        with open("token.json", "w") as token:
            token.write(creds.to_json())
    return build("gmail", "v1", credentials=creds)

# достаём заголовки письма
def get_header_map(msg):
    return {h["name"]: h["value"] for h in msg["payload"].get("headers", [])}

# простая заглушка вместо нейронки
def neural_response(plain_text: str) -> str:
    return "Спасибо! Мы получили ваше письмо и ответим по сути в ближайшее время."

# собираем reply-письмо
def build_reply(original_full_msg, reply_text):
    h = get_header_map(original_full_msg)
    to_addr = re.sub(r".*<(.+?)>.*", r"\1", h.get("From",""))
    subj = h.get("Subject","")
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

# создаём ярлык "Processed", если его нет
def ensure_label(svc, name="Processed"):
    labels = svc.users().labels().list(userId="me").execute().get("labels", [])
    for lb in labels:
        if lb["name"] == name:
            return lb["id"]
    created = svc.users().labels().create(
        userId="me",
        body={"name": name, "labelListVisibility":"labelShow","messageListVisibility":"show"}
    ).execute()
    return created["id"]

# ставим ярлык и убираем UNREAD
def mark_processed(svc, msg_id, label_id):
    svc.users().messages().modify(
        userId="me", id=msg_id,
        body={"removeLabelIds":["UNREAD"], "addLabelIds":[label_id]}
    ).execute()

def main():
    svc = get_service()

    # берём одно непрочитанное письмо
    res = svc.users().messages().list(userId="me", labelIds=["INBOX"], q="is:unread", maxResults=1).execute()
    msgs = res.get("messages", [])
    if not msgs:
        print("Нет непрочитанных писем.")
        return

    msg_id = msgs[0]["id"]
    full = svc.users().messages().get(userId="me", id=msg_id, format="full").execute()

    # формируем текст ответа (пока заглушка)
    reply_text = neural_response("(сюда позже подставим текст письма)")

    # строим и отправляем reply
    reply_body = build_reply(full, reply_text)
    sent = svc.users().messages().send(userId="me", body=reply_body).execute()
    print("Отправлен ответ, id:", sent.get("id"))

    # помечаем письмо как обработанное
    processed_id = ensure_label(svc, "Processed")
    mark_processed(svc, msg_id, processed_id)
    print("Помечено как Processed и снят UNREAD.")

if __name__ == "__main__":
    main()
