from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    DAZN_API_BASE_URL: str = "https://rail-router.discovery.indazn.com/eu/v10"
    DAZN_LOCALE: str = "it"
    DAZN_COUNTRY: str = "it"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()