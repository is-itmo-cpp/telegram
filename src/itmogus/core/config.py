from typing import Annotated, Any
from pydantic import BeforeValidator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


def parse_owner_ids(value: Any) -> set[int]:
    if not value:
        return set()
    if isinstance(value, str):
        return {int(x.strip()) for x in value.split(",") if x.strip()}
    return value


OwnerIds = Annotated[set[int], NoDecode, BeforeValidator(parse_owner_ids)]


class Config(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    bot_token: str
    owner_ids: OwnerIds = set()
    google_credentials_path: str = "credentials.json"
    users_table_id: str = ""
    github_token: str = ""
    github_org: str = ""
    github_branch: str = "main"
    storage_dir: str = "state"
    log_dir: str = "logs"


config = Config()  # type: ignore[missing-argument]
