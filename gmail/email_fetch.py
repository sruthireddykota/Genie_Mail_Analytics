import base64
import io
import re
import os

import PyPDF2
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from config.settings import settings
from mongodb.mongo_store import MongoStore
from utils.logger import get_logger

logger=get_logger()
store = MongoStore()

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]
CREDENTIALS_FILE = settings.CREDENTIALS_FILE
TOKEN_FILE = settings.TOKEN_FILE
TARGET_LABEL = settings.TARGET_LABEL


def get_gmail_service():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            creds = InstalledAppFlow.from_client_secrets_file(
                CREDENTIALS_FILE, SCOPES
            ).run_local_server(port=8080)
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
    return build("gmail", "v1", credentials=creds)


def get_label_id(service):
    labels = service.users().labels().list(userId="me").execute()
    for label in labels.get("labels", []):
        if label["name"].lower() == TARGET_LABEL:
            return label["id"]
    return None


def get_body(payload):
    if "parts" in payload:
        for part in payload["parts"]:
            if part["mimeType"] == "text/plain":
                data = part["body"].get("data", "")
                if data:
                    return base64.urlsafe_b64decode(data).decode("utf-8")
    else:
        data = payload["body"].get("data", "")
        if data:
            return base64.urlsafe_b64decode(data).decode("utf-8")
    return ""


def clean_body(body: str) -> str:
    lines = []
    for line in body.splitlines():
        if line.startswith(">") or (line.startswith("On ") and "wrote:" in line):
            break
        if line.strip() == "--":
            break
        lines.append(line)
    return "\n".join(lines).strip()


def extract_domain_from_subject(subject: str) -> str | None:
    match = re.search(r'\[(\w+)\]', subject)
    if match:
        domain = match.group(1).capitalize()
        if domain in ("Sales", "Franchise", "Customer"):
            return domain
    return None


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    text = ""
    try:
        reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
        total_pages = len(reader.pages)
        logger.info(f"PDF: {total_pages} pages found")

        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"

    except PyPDF2.errors.PdfReadError as e:
        logger.info(f"PDF read error — file may be corrupted or encrypted: {e}")
    except Exception as e:
        logger.info(f"PDF extraction error: {e}")

    return text.strip()


def get_pdf_attachments(service, msg_id: str) -> list[dict]:
    """
    Scans all parts of a Gmail message for PDF attachments.
    Downloads each one and extracts text using PyPDF2.
    Returns list of {"filename": ..., "text": ...}
    """
    attachments = []

    try:
        msg = service.users().messages().get(
            userId="me", id=msg_id, format="full"
        ).execute()

        def get_all_parts(payload):
            parts = []
            if "parts" in payload:
                for part in payload["parts"]:
                    parts.append(part)
                    parts.extend(get_all_parts(part))
            return parts

        all_parts = get_all_parts(msg["payload"])

        for part in all_parts:
            filename  = part.get("filename", "")
            mime_type = part.get("mimeType", "")

            is_pdf = (
                mime_type == "application/pdf"
                or mime_type == "application/octet-stream"
                or filename.lower().endswith(".pdf")
            )

            if not is_pdf:
                continue

            attachment_id = part["body"].get("attachmentId")

            if not attachment_id:
                inline_data = part["body"].get("data", "")
                if inline_data:
                    pdf_bytes = base64.urlsafe_b64decode(inline_data)
                    text      = extract_text_from_pdf(pdf_bytes)
                    if text:
                        attachments.append({
                            "filename": filename or "attachment.pdf",
                            "text":     text
                        })
                continue

            try:
                attachment = service.users().messages().attachments().get(
                    userId="me",
                    messageId=msg_id,
                    id=attachment_id
                ).execute()

                pdf_bytes = base64.urlsafe_b64decode(attachment["data"])
                text      = extract_text_from_pdf(pdf_bytes)

                if text:
                    attachments.append({
                        "filename": filename,
                        "text":     text
                    })

            except Exception as e:
                logger.info(f"Failed to fetch attachment {filename}: {e}")

    except Exception as e:
        logger.info(f"Error scanning attachments: {e}")

    return attachments



def fetch_new_email():
    service  = get_gmail_service()
    label_id = get_label_id(service)

    if not label_id:
        return None

    messages = service.users().messages().list(
        userId="me",
        labelIds=[label_id],
        maxResults=20
    ).execute().get("messages", [])

    if not messages:
        return None

    unprocessed = [m for m in messages if not store.is_processed(m["id"])]

    if not unprocessed:
        return None

    msg_id = unprocessed[0]["id"]

    msg = service.users().messages().get(
        userId="me", id=msg_id, format="full"
    ).execute()

    headers     = msg["payload"]["headers"]
    sender      = next((h["value"] for h in headers if h["name"] == "From"), "")
    subject     = next((h["value"] for h in headers if h["name"] == "Subject"), "")
    in_reply_to = next((h["value"] for h in headers if h["name"] == "In-Reply-To"), None)
    references  = next((h["value"] for h in headers if h["name"] == "References"), None)
    message_id  = next((h["value"] for h in headers if h["name"] == "Message-ID"), None)        
    body        = clean_body(get_body(msg["payload"]))


    # Skip our own sent emails
    smtp_user = settings.SMTP_USER
    if smtp_user and smtp_user.lower() in sender.lower():
        store.mark_processed(msg_id)
        return None

    #Extract PDF
    pdf_attachments = get_pdf_attachments(service, msg_id)

    combined_body = body

    if pdf_attachments:
        for pdf in pdf_attachments:
            combined_body += (
                f"\n\n--- Questions from {pdf['filename']} ---\n"
                f"{pdf['text']}"
            )
    else:
        logger.info("No PDF attachments found")

    store.mark_processed(msg_id)

    return {
        "sender":      sender,
        "subject":     subject,
        "body":        combined_body,
        "in_reply_to": in_reply_to,
        "references":  references,      
        "message_id":  message_id,  
        "domain_hint": extract_domain_from_subject(subject),
        "has_pdf":     len(pdf_attachments) > 0,
        "pdf_files":   [p["filename"] for p in pdf_attachments],
    }