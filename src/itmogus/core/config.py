from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    bot_token: str
    owner_ids: set[int] = set()
    google_credentials_path: str = "credentials.json"
    users_table_id: str = ""
    github_token: str = ""
    github_org: str = ""
    github_branch: str = "main"
    storage_dir: str = "state"

    @field_validator("owner_ids", mode="before")
    @classmethod
    def parse_owner_ids(cls, v: str | set[int] | int) -> set[int]:
        if isinstance(v, set):
            return v
        if isinstance(v, int):
            return {v}
        if isinstance(v, str):
            if not v.strip():
                return set()
            return {int(x.strip()) for x in v.split(",") if x.strip().isdigit()}
        return set()


config = Config()  # type: ignore[missing-argument]
