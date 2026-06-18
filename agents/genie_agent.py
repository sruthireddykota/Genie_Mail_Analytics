import os
import time
import json
import requests
import pandas as pd 
from dotenv import load_dotenv

load_dotenv()


HOST  = os.getenv("DATABRICKS_HOST")
TOKEN  = os.getenv("DATABRICKS_TOKEN")
SPACE_ID = os.getenv("GENIE_SPACE_ID")
HEADERS  = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type":  "application/json"
}

def fetch_query_results(statement_id):


    while True:

        response=requests.get(
            f"{HOST}/api/2.0/sql/statements/{statement_id}",
            headers=HEADERS)
        
        response.raise_for_status()
        result=response.json()

        status=result.get("status", {}).get("state")
        print(f"Query status: {status}")

        if status == "SUCCEEDED":
            
            data_array= result.get("result", {}).get("data_array", [])
            columns= result.get("manifest", {}).get("schema", {}).get("columns", [])
            column_names=[col["name"] for col in columns]

            dataframe=pd.DataFrame(data_array, columns=column_names)
            
            for col in dataframe.columns:
                sample = dataframe[col].dropna()

                if not sample.empty and isinstance(sample.iloc[0], str) and sample.iloc[0].strip().startswith("["):
                    
                    try:
                        rows = []
                        for val in dataframe[col]:
                            parsed = json.loads(val)
                            rows.extend(parsed if isinstance(parsed, list) else [parsed])
                        dataframe = pd.DataFrame(rows).reset_index(drop=True)
                        dataframe.columns = [str(c) for c in dataframe.columns]

                        break

                    except (json.JSONDecodeError, ValueError):
                        pass

            return dataframe
        elif status in ["FAILED", "CANCELED"]:
            return pd.DataFrame()
        
        time.sleep(3)

def poll_message(conversation_id, message_id):
    """Poll Genie until the message is complete and return the result."""
 
    while True:
        result = requests.get(
            f"{HOST}/api/2.0/genie/spaces/{SPACE_ID}/conversations/{conversation_id}/messages/{message_id}",
            headers=HEADERS
        )
        result.raise_for_status()
        result_data = result.json()
        status  = result_data.get("status")
        print(f"Genie response status: {status}")
 
        if status == "COMPLETED":
            answer  = ""
            sql_query = ""
            statement_id = None
 
            for item in result_data.get("attachments", []):
                if "text" in item:
                    answer = item["text"]["content"]
                if "query" in item:
                    sql_query    = item["query"]["query"]
                    statement_id = item["query"].get("statement_id")
 
            return {
                "answer": answer,
                "sql": sql_query,
                "dataframe": fetch_query_results(statement_id) if statement_id else pd.DataFrame(),
                "conversation_id": conversation_id,
            }
 
        elif status in ["FAILED", "CANCELED"]:
            return {
                "answer": "Unable to process this question.",
                "sql": "",
                "dataframe": pd.DataFrame(),
                "conversation_id": conversation_id,
            }
 
        time.sleep(3)


def ask_genie(question):
    

    response=requests.post(
        f"{HOST}/api/2.0/genie/spaces/{SPACE_ID}/start-conversation", 
        json={"content": question},
        headers=HEADERS)
    
    if not response.ok:
        response.raise_for_status()
    
    data=response.json()
    return poll_message(data["message"]["conversation_id"], data["message"]["id"])
    
def continue_conversation(conversation_id, question):
    """Continue an existing Genie conversation with a follow-up question."""
 
    response = requests.post(
        f"{HOST}/api/2.0/genie/spaces/{SPACE_ID}/conversations/{conversation_id}/messages",
        json={"content": question},
        headers=HEADERS
    )
 
    if not response.ok:
        response.raise_for_status()
 
    return poll_message(conversation_id, response.json()["id"])