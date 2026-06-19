from agent_framework.foundry import FoundryChatClient
from azure.identity.aio import DefaultAzureCredential

from config.settings import settings


def get_client() -> FoundryChatClient:
    credential = DefaultAzureCredential()

    client = FoundryChatClient(
        project_endpoint=settings.AZURE_AI_PROJECT_ENDPOINT,
        model=settings.AZURE_DEPLOYMENT_NAME,
        credential=credential
    )
    return client