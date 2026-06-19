import uuid
from datetime import datetime
from pymongo import MongoClient

from config.settings import settings

class MongoStore:

    def __init__(self):
        self.client = MongoClient(settings.MONGO_URI)
        self.db = self.client[settings.MONGO_DB]

        self.sessions = self.db["sessions"]
        self.messages = self.db["messages"]
        self.chat_messages = self.db["chat_messages"]
        self.chat_sessions = self.db["chat_sessions"]
        self.pending_emails = self.db["pending_emails"]
        self.conversations = self.db["conversations"]
        

    # Sessions

    def create_session(self, customer_email, customer_name, domain, genie_conv_id, message_id):
        session_id = str(uuid.uuid4())
        self.sessions.insert_one({
            "session_id":     session_id,
            "customer_email": customer_email,
            "customer_name":  customer_name,
            "domain":         domain,
            "genie_conv_id":  genie_conv_id,
            "message_id":     message_id,
            "status":         "active",
            "created_at":     datetime.utcnow(),
            "updated_at":     datetime.utcnow(),
        })
        return session_id

    def get_session_by_domain(self, domain):
        return self.sessions.find_one({"domain": domain}, {"_id": 0})

    def get_session_by_reply(self, in_reply_to):
        doc = self.conversations.find_one({"message_id": in_reply_to})
        if not doc:
            return None
        return self.sessions.find_one({"session_id": doc["session_id"]}, {"_id": 0})

    def get_all_sessions(self):
        return list(self.sessions.find({}, {"_id": 0}).sort("created_at", -1))

    def update_session_message_id(self, session_id, message_id):
        self.sessions.update_one(
            {"session_id": session_id},
            {"$set": {"message_id": message_id, "updated_at": datetime.utcnow()}}
        )

    # Messages 

    def save_message(self, session_id, domain, role, content):
        self.messages.insert_one({
            "session_id": session_id,
            "domain":     domain,
            "role":       role,
            "content":    content,
            "timestamp":  datetime.utcnow(),
        })

    def get_messages(self, session_id):
        return list(
            self.messages.find({"session_id": session_id}, {"_id": 0})
            .sort("timestamp", 1)
        )

    def message_exists(self, session_id, role, content):
        return self.messages.find_one({
            "session_id": session_id,
            "role":       role,
            "content":    content
        }) is not None

    def get_recent_messages(self, session_id, limit=5):
        return self.get_messages(session_id)[-limit:]

    def build_context_string(self, session_id, limit=5):
        recent = self.get_recent_messages(session_id, limit)
        if not recent:
            return ""
        lines = ["Previous conversation:"]
        for msg in recent:
            role = "Customer" if msg["role"] == "customer" else "Agent"
            lines.append(f"{role}: {msg['content']}")
        return "\n".join(lines)
    
    def get_messages_by_domain(self, domain: str) -> list:
        sessions = [s for s in self.get_all_sessions() if s["domain"] == domain]
        all_messages = []
        for session in sessions:
            all_messages.extend(self.get_messages(session["session_id"]))
        all_messages.sort(key=lambda m: m["timestamp"])
        return all_messages

    # Conversations 

    def save_conversation(self, message_id, conversation_id, session_id="", sender="", question=""):
        self.conversations.insert_one({
            "message_id":      message_id,
            "conversation_id": conversation_id,
            "session_id":      session_id,
            "sender":          sender,
            "question":        question,
            "created_at":      datetime.utcnow(),
        })

    # Chat sessions 
    
    def create_chat(self, customer_email, title, genie_conv_id):
        chat_id = str(uuid.uuid4())
        self.chat_sessions.insert_one({
            "chat_id":        chat_id,
            "customer_email": customer_email,
            "title":          title,
            "genie_conv_id":  genie_conv_id,
            "created_at":     datetime.utcnow(),
        })
        return chat_id

    def get_chats_by_customer(self, customer_email):
        return list(
            self.chat_sessions.find(
                {"customer_email": {"$regex": customer_email, "$options": "i"}},
                {"_id": 0}
            ).sort("created_at", -1)
        )

    def get_chat(self, chat_id):
        return self.chat_sessions.find_one({"chat_id": chat_id}, {"_id": 0})

    def update_chat_conv_id(self, chat_id, genie_conv_id):
        self.chat_sessions.update_one(
            {"chat_id": chat_id},
            {"$set": {"genie_conv_id": genie_conv_id}}
        )

    def save_chat_message(self, chat_id, role, content):
        self.chat_messages.insert_one({
            "chat_id":   chat_id,
            "role":      role,
            "content":   content,
            "timestamp": datetime.utcnow(),
        })

    def get_chat_messages(self, chat_id):
        return list(
            self.chat_messages.find({"chat_id": chat_id}, {"_id": 0})
            .sort("timestamp", 1)
        )

    def get_recent_chat_messages(self, chat_id, limit=5):
        return self.get_chat_messages(chat_id)[-limit:]

    def build_chat_context(self, chat_id, limit=5):
        recent = self.get_recent_chat_messages(chat_id, limit)
        if not recent:
            return ""
        lines = ["Previous conversation:"]
        for msg in recent:
            role = "User" if msg["role"] == "user" else "Genie"
            lines.append(f"{role}: {msg['content']}")
        return "\n".join(lines)
    

    def clear_chat(self, chat_id):
        self.chat_messages.delete_many({"chat_id": chat_id})

    def delete_chat(self, chat_id):
        self.chat_messages.delete_many({"chat_id": chat_id})
        self.chat_sessions.delete_one({"chat_id": chat_id})


    # Pending mails

    def save_pending_email(self, email_data: dict) -> str:
        pending_id = str(uuid.uuid4())

        dataframe = email_data.get("dataframe")
        if dataframe is not None and not dataframe.empty:
            dataframe_records = dataframe.to_dict(orient="records")
            dataframe_columns = dataframe.columns.tolist()
        else:
            dataframe_records = []
            dataframe_columns = []

        self.pending_emails.insert_one({
            "pending_id":        pending_id,
            "sender":            email_data.get("sender", ""),
            "subject":           email_data.get("subject", ""),
            "domain":            email_data.get("domain", ""),
            "questions":         email_data.get("questions", []),
            "qa_pairs":          email_data.get("qa_pairs", []),
            "draft_email":       email_data.get("draft_email", ""),
            "conversation_id":   email_data.get("conversation_id", ""),
            "in_reply_to":       email_data.get("in_reply_to"),
            "references":        email_data.get("references"),
            "single_count":      email_data.get("single_count", False),
            "is_followup":       email_data.get("is_followup", False),
            "dataframe_records": dataframe_records,    
            "dataframe_columns": dataframe_columns,    
            "viz_spec":          email_data.get("viz_spec"), 
            "status":            "pending",
            "created_at":        datetime.utcnow(),
            "updated_at":        datetime.utcnow(),
        })
        print(f"MongoDB: Saved pending email {pending_id} [{email_data.get('domain')}]")
        return pending_id

    def get_pending_emails(self, domain: str = None) -> list:
        import pandas as pd

        query = {"status": "pending"}
        if domain and domain != "All":
            query["domain"] = domain

        docs = list(
            self.pending_emails.find(query, {"_id": 0})
            .sort("created_at", -1)
        )

        for doc in docs:
            records = doc.pop("dataframe_records", [])
            columns = doc.pop("dataframe_columns", [])

            if records:
                doc["dataframe"] = pd.DataFrame(records, columns=columns)
            else:
                doc["dataframe"] = pd.DataFrame()

        return docs

    def update_pending_status(self, pending_id: str, status: str):
        self.pending_emails.update_one(
            {"pending_id": pending_id},
            {"$set": {"status": status, "updated_at": datetime.utcnow()}}
        )

    def pending_email_exists(self, sender: str, domain: str, question: str) -> bool:
        return self.pending_emails.find_one({
            "sender": sender,
            "domain": domain,
            "questions": {"$in": [question]},
            "status": "pending"
        }) is not None
    
    #editable draft email

    def update_pending_draft(self, pending_id: str, draft_email: str):
        self.pending_emails.update_one(
            {"pending_id": pending_id},
            {"$set": {"draft_email": draft_email, "updated_at": datetime.utcnow()}}
        )
        