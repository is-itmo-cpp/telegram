import os
from pathlib import Path

import pytest
from dotenv import load_dotenv


load_dotenv()

os.environ.setdefault("BOT_TOKEN", "test-bot-token")
os.environ.setdefault("OWNER_IDS", "1")
os.environ.setdefault("USERS_TABLE_ID", "test-users-table")
os.environ.setdefault("GOOGLE_CREDENTIALS_PATH", "credentials.json")


@pytest.fixture(scope="session")
def credentials_path() -> Path:
    path = Path(os.environ["TEST_GOOGLE_CREDENTIALS_PATH"])
    assert path.exists(), f"Credentials file not found: {path}"
    return path


@pytest.fixture
async def sheets_client(credentials_path: Path):
    from itmogus.sheets.sheet import SheetsClient

    client = await SheetsClient.create(str(credentials_path))
    try:
        yield client
    finally:
        await client.close()
