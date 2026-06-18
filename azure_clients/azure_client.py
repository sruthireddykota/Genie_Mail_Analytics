import os

from dotenv import load_dotenv

from agent_framework.azure import AzureAIAgentClient
from azure.identity.aio import DefaultAzureCredential

load_dotenv()

def get_client() -> AzureAIAgentClient:
    credential = DefaultAzureCredential()

    client = AzureAIAgentClient(
        project_endpoint=os.getenv("AZURE_AI_PROJECT_ENDPOINT"),
        model_deployment_name=os.getenv("AZURE_DEPLOYMENT_NAME"),
        credential=credential
    )
    return client