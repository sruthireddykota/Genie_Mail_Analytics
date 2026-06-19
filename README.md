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
├── docker-compose.yml               # Compose: FastAPI + MongoDB + Mongo Express
├── Dockerfile.fastapi               # Docker image for FastAPI service
├── requirements.txt                 # Python dependencies
├── Credentials.json                 # Gmail OAuth credentials (not committed)
├── token.json                       # Gmail OAuth token (not committed)
├── processed_emails.json            # Tracks already-processed message IDs
│
├── agents/
│   ├── __init__.py
│   ├── email_fetching_agent.py      # Gmail OAuth, label filtering
│   ├── email_sender_agent.py        # SMTP send + Excel attachment
│   ├── email_creator_agent.py       # Drafts reply email via Azure AI
│   ├── question_splitter_agent.py   # Splits multi-question emails by domain
│   ├── genie_agent.py               # Databricks Genie API calls
│   └── visualization_agent.py       # Determines chart type for Genie results
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
- MongoDB instance (local or Atlas)
- Databricks workspace with a Genie Space configured
- Gmail account with OAuth credentials
- Azure AI Foundry project (for email drafting and chat title generation)
- SMTP credentials for outbound email

---

## Setup

### 1. Clone and create a virtual environment

```bash
git clone <repo-url>
cd Genie_Mail_Analytics
python -m venv venv
source venv/bin/activate        # macOS/Linux
venv\Scripts\activate           # Windows
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment variables

Copy `.env.example` to `.env` and fill in all values:

```bash
cp .env.example .env
```

```env
# MongoDB
MONGO_URI=mongodb://localhost:27017
MONGO_DB=genie_email
GENIE_MONGO_ROOT_USERNAME=admin
GENIE_MONGO_ROOT_PASSWORD=secret
GENIE_MONGOEXPRESS_USERNAME=admin
GENIE_MONGOEXPRESS_PASSWORD=secret

# SMTP (outbound email)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=you@gmail.com
SMTP_PASSWORD=your-app-password

# Gmail OAuth (inbound email fetching)
CREDENTIALS_FILE=credentials.json
TOKEN_FILE=token.json
TARGET_LABEL=genie-queries
PROCESSED_FILE=processed_emails.json

# Databricks Genie
DATABRICKS_HOST=https://your-workspace.azuredatabricks.net
DATABRICKS_TOKEN=your-pat-token
GENIE_SPACE_ID=your-genie-space-id

# Azure AI Foundry
AZURE_AI_PROJECT_ENDPOINT=https://your-project.services.ai.azure.com
AZURE_DEPLOYMENT_NAME=gpt-4o

# App
ADMIN_EMAIL=admin@yourdomain.com
API_BASE_URL=http://localhost:8002
```

### 4. Set up Gmail OAuth

Download `credentials.json` from Google Cloud Console (OAuth 2.0 Desktop App credentials) and place it in the project root. Then run the auth flow once:

```bash
python auth.py
```

A browser window will open — sign in and grant access. This writes `token.json` and won't be needed again unless the token is revoked.

Also create a Gmail label called `genie-queries` and apply it to any inbound emails you want the system to process.

### 5. Initialise `processed_emails.json`

```bash
echo "[]" > processed_emails.json
```

---

## Running the App

Two services must run simultaneously — open two terminals with the venv activated.

**Terminal 1 — FastAPI service:**

```bash
uvicorn fastapi_genie:app --host 0.0.0.0 --port 8002 --reload
```

Verify it's up at [http://localhost:8002/health](http://localhost:8002/health). Interactive API docs are at [http://localhost:8002/docs](http://localhost:8002/docs).

**Terminal 2 — Streamlit UI:**

```bash
streamlit run app.py
```

Opens at [http://localhost:8501](http://localhost:8501).

---

## How It Works

### Email pipeline

1. Gmail is polled for emails with the `genie-queries` label that aren't in `processed_emails.json`.
2. The **Question Splitter Agent** detects the domain (`Sales`, `Franchise`, `Customer`, `Miscellaneous`) and splits multi-question emails.
3. Each question is sent to **Databricks Genie**, which returns a natural-language answer and optionally a DataFrame.
4. The **Email Creator Agent** (via Azure AI Foundry) drafts a reply combining all answers.
5. The draft is saved to MongoDB as a `pending` record and appears in the Approval UI.

### Approval UI (`/pages/approval.py`)

- Lists pending emails grouped by domain, with pending counts in the sidebar.
- Reviewers can edit the draft inline before approving.
- If Genie returned tabular data, a chart preview and `.xlsx` attachment are included automatically.
- **Approve** sends the reply via SMTP and saves the conversation to MongoDB.
- **Reject** discards the draft.
- Auto-fetch polls for new emails every 5 seconds (toggle in sidebar).

### Chatbot UI (`/pages/chatbot.py`)

- Direct conversational interface to Databricks Genie.
- Maintains per-user chat sessions with full history in MongoDB.
- Each session is titled automatically using Azure AI Foundry.

---

## API Reference

The FastAPI service runs on port `8002`. Key endpoints:

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/pipeline/run` | Fetch emails and run full pipeline |
| `GET` | `/pending?domain=Sales` | List pending drafts (optionally by domain) |
| `POST` | `/pending/approve` | Approve a pending draft |
| `POST` | `/pending/reject` | Reject a pending draft |
| `PATCH` | `/pending/draft` | Update draft text |
| `GET` | `/sessions` | All email sessions |
| `GET` | `/sessions/domain/{domain}` | Session for a specific domain |
| `GET` | `/sessions/{domain}/messages` | Full message history for a domain |
| `POST` | `/chat/create` | Create a new chatbot session |
| `GET` | `/chat/{chat_id}/messages` | Get chat history |
| `POST` | `/chat/message` | Save a chat message |
| `DELETE` | `/chat/{chat_id}` | Delete a chat session |

Full interactive docs: [http://localhost:8002/docs](http://localhost:8002/docs)

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

## Running with Docker

A `Dockerfile.fastapi` and `docker-compose.yml` are included if you prefer to run the FastAPI service, MongoDB, and Mongo Express in containers.

```bash
docker-compose up --build
```

This starts:

| Service | Port |
|---------|------|
| FastAPI | `8002` |
| MongoDB | `27017` |
| Mongo Express (DB UI) | `8081` |

The Streamlit UI still runs locally:

```bash
streamlit run app.py
```

Make sure `API_BASE_URL=http://localhost:8002` and `MONGO_URI=mongodb://localhost:27017` in your `.env` match the exposed ports.

---

## Troubleshooting

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
The error message will name the missing field.

**`JSONDecodeError` from approval page**
FastAPI isn't running, or crashed mid-request. Check the uvicorn terminal for the traceback and restart:
```bash
uvicorn fastapi_genie:app --host 0.0.0.0 --port 8002
```
Drop `--reload` if file-write events (token.json, processed_emails.json) are causing unexpected restarts.

**No emails appearing after fetch**
- Confirm the email in Gmail has the `genie-queries` label applied.
- Check `processed_emails.json` — if the message ID is already there, reset it: `echo "[]" > processed_emails.json`

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
| Config | Pydantic Settings |