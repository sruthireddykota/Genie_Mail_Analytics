from fastapi import FastAPI
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel
from typing import Optional
import pandas as pd

from mongodb.mongo_store import MongoStore
from pipeline import run_pipeline

app   = FastAPI()
store = MongoStore()


class ApprovePendingRequest(BaseModel):
    pending_id: str
    edited_draft: Optional[str] = None

class RejectPendingRequest(BaseModel):
    pending_id: str

class UpdateDraftRequest(BaseModel):
    pending_id: str
    draft_email: str

class CreateChatRequest(BaseModel):
    customer_email: str
    title: str
    genie_conv_id: str

class ChatMessageRequest(BaseModel):
    chat_id: str
    role: str
    content: str

class UpdateChatConvRequest(BaseModel):
    chat_id: str
    genie_conv_id: str

class CreateSessionRequest(BaseModel):
    customer_email: str
    customer_name: str
    domain: str
    genie_conv_id: str
    message_id: str

class UpdateSessionMessageIdRequest(BaseModel):
    session_id: str
    message_id: str

class SaveConversationRequest(BaseModel):
    message_id: str
    conversation_id: str
    session_id: str
    sender: str
    question: str

class SaveMessageRequest(BaseModel):
    session_id: str
    domain: str
    role: str
    content: str

@app.get("/")
def read_root():
    return {"message": "Genie Mail Analytics API"}

@app.get("/health")
def health_check():
    return {"status": "healthy"}


# Pipeline

@app.post("/pipeline/run")
def trigger_pipeline():
    results = run_pipeline()
    if not results:
        return {"status": "no_emails", "results": []}
    return {"status": "success", "count": len(results)}


# Pending emails

@app.get("/pending")
def get_pending(domain: Optional[str] = None):
    data = store.get_pending_emails(domain)
    result = []
    for p in data:
        item = {k: v for k, v in p.items() if k != "dataframe"}
        df = p.get("dataframe")
        if isinstance(df, pd.DataFrame) and not df.empty:
            item["dataframe_records"] = df.to_dict(orient="records")
            item["dataframe_columns"] = list(df.columns)
        else:
            item["dataframe_records"] = []
            item["dataframe_columns"] = []
        result.append(item)
    return jsonable_encoder(result)

@app.post("/pending/approve")
def approve_pending(req: ApprovePendingRequest):
    if req.edited_draft:
        store.update_pending_draft(req.pending_id, req.edited_draft)
    store.update_pending_status(req.pending_id, "approved")
    return {"status": "approved"}

@app.post("/pending/reject")
def reject_pending(req: RejectPendingRequest):
    store.update_pending_status(req.pending_id, "rejected")
    return {"status": "rejected"}

@app.patch("/pending/draft")
def update_draft(req: UpdateDraftRequest):
    store.update_pending_draft(req.pending_id, req.draft_email)
    return {"status": "updated"}


# Sessions

@app.get("/sessions")
def get_all_sessions():
    return jsonable_encoder(store.get_all_sessions())

@app.get("/sessions/{domain}/messages")
def get_domain_messages(domain: str):
    return jsonable_encoder(store.get_messages_by_domain(domain))

@app.get("/sessions/domain/{domain}")
def get_session_by_domain(domain: str):
    session = store.get_session_by_domain(domain)
    return jsonable_encoder(session) if session else None

@app.post("/sessions/create")
def create_session(req: CreateSessionRequest):
    session_id = store.create_session(
        req.customer_email, req.customer_name, req.domain, req.genie_conv_id, req.message_id
    )
    return {"session_id": session_id}

@app.patch("/sessions/message-id")
def update_session_message_id(req: UpdateSessionMessageIdRequest):
    store.update_session_message_id(req.session_id, req.message_id)
    return {"status": "updated"}


# Conversations 

@app.post("/conversations")
def save_conversation(req: SaveConversationRequest):
    store.save_conversation(
        req.message_id, req.conversation_id, req.session_id, req.sender, req.question
    )
    return {"status": "saved"}


# Messages 

@app.post("/messages")
def save_message(req: SaveMessageRequest):
    store.save_message(req.session_id, req.domain, req.role, req.content)
    return {"status": "saved"}

@app.get("/messages/exists")
def message_exists(session_id: str, role: str, content: str):
    return {"exists": store.message_exists(session_id, role, content)}


# Chatbot 

@app.post("/chat/create")
def create_chat(req: CreateChatRequest):
    chat_id = store.create_chat(req.customer_email, req.title, req.genie_conv_id)
    return {"chat_id": chat_id}

@app.get("/chat/{customer_email}/sessions")
def get_chat_sessions(customer_email: str):
    return jsonable_encoder(store.get_chats_by_customer(customer_email))

@app.get("/chat/{chat_id}/messages")
def get_chat_messages(chat_id: str):
    return jsonable_encoder(store.get_chat_messages(chat_id))

@app.post("/chat/message")
def save_chat_message(req: ChatMessageRequest):
    store.save_chat_message(req.chat_id, req.role, req.content)
    return {"status": "saved"}

@app.patch("/chat/conv")
def update_chat_conv(req: UpdateChatConvRequest):
    store.update_chat_conv_id(req.chat_id, req.genie_conv_id)
    return {"status": "updated"}

@app.delete("/chat/{chat_id}")
def delete_chat(chat_id: str):
    store.delete_chat(chat_id)
    return {"status": "deleted"}

@app.delete("/chat/{chat_id}/messages")
def clear_chat(chat_id: str):
    store.clear_chat(chat_id)
    return {"status": "cleared"}

@app.get("/chat/{chat_id}")
def get_chat(chat_id: str):
    chat = store.get_chat(chat_id)
    if not chat:
        return {"status": "error", "detail": "Chat not found"}
    return jsonable_encoder(chat)

@app.get("/chat/{chat_id}/context")
def get_chat_context(chat_id: str, limit: int = 5):
    context = store.build_chat_context(chat_id, limit=limit)
    return {"chat_id": chat_id, "context": context}

# Processed emails

@app.get("/processed/exists")
def is_processed(message_id: str):
    return {"exists": store.is_processed(message_id)}

@app.post("/processed/mark")
def mark_processed(message_id: str):
    store.mark_processed(message_id)
    return {"status": "marked"}