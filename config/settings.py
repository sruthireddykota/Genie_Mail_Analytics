from pydantic_settings import BaseSettings
from pydantic import ConfigDict

class Settings(BaseSettings):
    model_config=ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="allow"  
    )

    GENIE_MONGO_ROOT_USERNAME : str
    GENIE_MONGO_ROOT_PASSWORD  : str
    GENIE_MONGOEXPRESS_USERNAME : str
    GENIE_MONGOEXPRESS_PASSWORD : str
    MONGO_DB : str


    SMTP_PASSWORD : str
    SMTP_PORT : int
    SMTP_HOST : str
    SMTP_USER : str

    SCOPES  : str
    CREDENTIALS_FILE : str
    TOKEN_FILE  : str
    TARGET_LABEL  : str
    PROCESSED_FILE : str

    ADMIN_EMAIL  : str

    DATABRICKS_HOST  : str
    DATABRICKS_TOKEN : str
    GENIE_SPACE_ID : str

    MONGO_URI : str
    API_BASE_URL : str

    AZURE_AI_PROJECT_ENDPOINT : str
    AZURE_DEPLOYMENT_NAME : str


settings= Settings()

