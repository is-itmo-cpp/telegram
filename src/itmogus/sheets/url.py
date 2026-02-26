import re


RE_SPREADSHEET = re.compile(r"/spreadsheets/d/([a-zA-Z0-9-_]+)/.*?gid=(\d+)")


def parse_sheets_url(url: str) -> tuple[str, int] | None:
    match = RE_SPREADSHEET.search(url)
    if not match:
        return None
    return match.group(1), int(match.group(2))
