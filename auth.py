from google_auth_oauthlib.flow import InstalledAppFlow
import os
from dotenv import load_dotenv

load_dotenv()

SCOPES  = ["https://www.googleapis.com/auth/gmail.modify"]
CREDENTIALS_FILE = os.getenv("CREDENTIALS_FILE", "credentials.json")
TOKEN_FILE  = os.getenv("TOKEN_FILE", "token.json")

flow  = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
creds = flow.run_local_server(port=8080)

with open(TOKEN_FILE, "w") as token:
    token.write(creds.to_json())

print("token.json saved successfully.")