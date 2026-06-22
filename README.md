# Genie Mail Analytics

An intelligent, email-driven analytics workflow. Business users send questions via email, the system automatically fetches them, queries Databricks Genie for answers, drafts a reply, and routes it through a human-approval UI before sending.

---

## Architecture Overview

```
Incoming Email (Gmail)
        │
        ▼
Email Fetching Agent
        │
        ▼
Question Splitter Agent  ──►  Databricks Genie API
        │                            │
        ▼                            ▼
Email Creator Agent  ◄──────  Genie Answers + DataFrames
        │
        ▼
MongoDB (pending_emails)
        │
        ▼
Streamlit Approval UI  ──►  Human reviews & approves
        │
        ▼
SMTP Send  ──►  Reply to sender
```

**Key design principle:** All MongoDB persistence goes through the FastAPI service. Agent/LLM calls (Genie, Azure AI Foundry, chat title generation) stay as direct local imports — no HTTP round-trip for those.

---

## Project Structure

```
Genie_Mail_Analytics/
├── app.py                           # Streamlit entry point & login
├── fastapi_genie.py                 # FastAPI service (all MongoDB ops)
├── pipeline.py                      # Orchestrates fetch → split → genie → draft
├── auth.py                          # Gmail OAuth first-time auth flow
├── docker-compose.yml               # Compose: FastAPI + MongoDB + Mongo Express + Streamlit
├── Dockerfile.fastapi               # Docker image for FastAPI service
├── Dockerfile.streamlit             # Docker image for Streamlit service
├── requirements.txt                 # Python dependencies
├── Credentials.json                 # Gmail OAuth credentials (not committed)
├── token.json                       # Gmail OAuth token (not committed)
│
├── agents/
│   ├── __init__.py
│   ├── email_creator_agent.py       # Drafts reply email via Azure AI
│   ├── genie_agent.py               # Databricks Genie API calls
│   ├── question_splitter_agent.py   # Splits multi-question emails by domain
│   └── visualization_agent.py       # Determines chart type for Genie results
│
├── gmail/
│   ├── __init__.py
│   ├── email_fetch.py               # Gmail OAuth, label filtering, PDF extraction
│   └── email_sender.py              # SMTP send + Excel attachment
│
├── pages/
│   ├── __init__.py
│   ├── approval.py                  # Human review UI (approve / reject / edit)
│   └── chatbot.py                   # Direct Genie chat interface
│
├── mongodb/
│   ├── __init__.py
│   └── mongo_store.py               # All MongoDB read/write logic
│
├── azure_clients/
│   ├── __init__.py
│   └── azure_client.py              # FoundryChatClient factory
│
├── config/
│   ├── __init__.py
│   └── settings.py                  # Pydantic settings (single .env source)
│
├── utils/
│   └── chat_title.py                # Auto-generates chat session titles
│
└── tests/                           # Test suite
```

---

## Prerequisites

- Python 3.12+
- Docker & Docker Compose
- Databricks workspace with a Genie Space configured
- Gmail account with OAuth credentials
- Azure AI Foundry project (for email drafting and chat title generation)
- SMTP credentials for outbound email

---

## Setup

### 1. Clone the repository

```bash
git clone <repo-url>
cd Genie_Mail_Analytics
```

### 2. Configure environment variables

Copy `env.example` to `.env` and fill in all values:

```bash
cp env.example .env
```

> **Note:** When running with Docker, `MONGO_URI` must use the container name `genie-mongodb` and `API_BASE_URL` must use `genie-fastapi` — not `localhost`.

### 3. Set up Gmail OAuth

Download `Credentials.json` from Google Cloud Console (OAuth 2.0 Desktop App credentials) and place it in the project root. Then run the auth flow once locally:

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python auth.py
```

A browser window will open — sign in and grant access. This writes `token.json` and won't be needed again unless the token is revoked.

Also create a Gmail label called `genie-queries` and apply it to inbound emails you want the system to process.

## Running with Docker

```bash
docker-compose up --build -d
```

| Service | URL |
|---------|-----|
| Streamlit UI | http://localhost:8502 |
| FastAPI | http://localhost:8002 |
| FastAPI Docs | http://localhost:8002/docs |
| Mongo Express | http://localhost:8082 |
| MongoDB | localhost:27018 |

To stop all containers:

```bash
docker-compose down
```

To stop and remove all data volumes:

```bash
docker-compose down -v
```

---

## Running Locally (without Docker)

Install dependencies and activate the venv, then open two terminals:

**Terminal 1 — FastAPI service:**

```bash
uvicorn fastapi_genie:app --host 0.0.0.0 --port 8002 --reload
```

**Terminal 2 — Streamlit UI:**

```bash
streamlit run app.py
```

> When running locally, set `API_BASE_URL=http://localhost:8002` and `MONGO_URI=mongodb://localhost:27017` in `.env`.

---

## How It Works

### Email pipeline

1. Gmail is polled for emails with the `genie-queries` label. Processed message IDs are tracked in MongoDB (`processed_emails` collection) to prevent reprocessing.
2. The **Question Splitter Agent** detects the domain (`Sales`, `Franchise`, `Customer`, `Miscellaneous`) and splits multi-question emails.
3. Each question is sent to **Databricks Genie**, which returns a natural-language answer and optionally a DataFrame.
4. The **Email Creator Agent** (via Azure AI Foundry) drafts a reply combining all answers.
5. The draft is saved to MongoDB as a `pending` record and appears in the Approval UI.

### Approval UI (`pages/approval.py`)

- Lists pending emails grouped by domain, with pending counts in the sidebar.
- Reviewers can edit the draft inline before approving.
- If Genie returned tabular data, a chart preview and `.xlsx` attachment are included automatically.
- **Approve** sends the reply via SMTP and saves the conversation to MongoDB.
- **Reject** discards the draft.
- Auto-fetch polls for new emails every 60 seconds (toggle in sidebar).

### Chatbot UI (`pages/chatbot.py`)

- Direct conversational interface to Databricks Genie.
- Maintains per-user chat sessions with full history in MongoDB.
- Each session is titled automatically using Azure AI Foundry.

---

## API Reference

The FastAPI service runs on port `8002`. Key endpoints:

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check |
| `POST` | `/pipeline/run` | Fetch emails and run full pipeline |
| `GET` | `/pending?domain=Sales` | List pending drafts (optionally by domain) |
| `POST` | `/pending/approve` | Approve a pending draft |
| `POST` | `/pending/reject` | Reject a pending draft |
| `PATCH` | `/pending/draft` | Update draft text |
| `GET` | `/sessions` | All email sessions |
| `GET` | `/sessions/domain/{domain}` | Session for a specific domain |
| `GET` | `/sessions/{domain}/messages` | Full message history for a domain |
| `GET` | `/processed/exists` | Check if a message ID has been processed |
| `POST` | `/processed/mark` | Mark a message ID as processed |
| `POST` | `/chat/create` | Create a new chatbot session |
| `GET` | `/chat/{chat_id}/messages` | Get chat history |
| `POST` | `/chat/message` | Save a chat message |
| `DELETE` | `/chat/{chat_id}` | Delete a chat session |

Full interactive docs: http://localhost:8002/docs

---

## Domain Routing

Emails are automatically routed to one of four domains based on keywords in the question:

| Domain | Trigger keywords |
|--------|-----------------|
| Sales | Sale, Sales |
| Franchise | Franchise, Franchises |
| Customer | Customer, Customers |
| Miscellaneous | Everything else |

---

## Troubleshooting

**Container name conflict on `docker-compose up`**
```bash
docker rm -f genie-mongodb genie-mongo-express genie-fastapi genie-streamlit
docker-compose up --build -d
```

**`invalid_grant` / Gmail token expired**
```bash
rm token.json
python auth.py
```

**`ValidationError` on startup**
A required field is missing from `.env`. Run:
```bash
python -c "from config.settings import settings; print('OK')"
```

**`JSONDecodeError` from approval page**
FastAPI isn't running or crashed. Check logs:
```bash
docker logs genie-fastapi
```

**Old emails being reprocessed after migration to MongoDB**
The `processed_emails` MongoDB collection is empty. Seed it from your existing `processed_emails.json`:
```bash
python -c "
import json
from mongodb.mongo_store import MongoStore
store = MongoStore()
with open('processed_emails.json', 'r') as f:
    ids = json.load(f)
for msg_id in ids:
    store.mark_processed(msg_id)
print(f'Seeded {len(ids)} IDs')
"
```

**No emails appearing after fetch**
- Confirm the email in Gmail has the `genie-queries` label applied.
- Check the `processed_emails` MongoDB collection via Mongo Express at http://localhost:8082.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Streamlit |
| Backend API | FastAPI + Uvicorn |
| Database | MongoDB (via PyMongo) |
| Analytics | Databricks Genie |
| AI / LLM | Azure AI Foundry (`FoundryChatClient`) |
| Email inbound | Gmail API (OAuth 2.0) |
| Email outbound | SMTP (smtplib) |
| Containerisation | Docker + Docker Compose |
| Config | Pydantic Settings |