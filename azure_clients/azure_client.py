from agent_framework.foundry import FoundryChatClient
from azure.identity.aio import ClientSecretCredential

from config.settings import settings


def get_client() -> FoundryChatClient:
    credential = ClientSecretCredential(
        tenant_id=settings.AZURE_TENANT_ID,
        client_id=settings.AZURE_CLIENT_ID,
        client_secret=settings.AZURE_CLIENT_SECRET,
    )

    client = FoundryChatClient(
        project_endpoint=settings.AZURE_AI_PROJECT_ENDPOINT,
        model=settings.AZURE_DEPLOYMENT_NAME,
        credential=credential
    )
    return client