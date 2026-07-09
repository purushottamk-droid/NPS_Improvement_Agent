"""
auth/auth.py — Runtime OAuth credential loader for Gmail + Calendar APIs

Reads oauth_final.json (generated once by auth_setup.py).
Auto-refreshes the access_token if expired, and persists the refreshed
token back to oauth_final.json so future runs don't re-refresh unnecessarily.
"""

import os
import json

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

OAUTH_FILE = os.path.join(os.path.dirname(__file__), "oauth_final.json")

GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
]
CALENDAR_SCOPES = [
    "https://www.googleapis.com/auth/calendar",
]


def _load_oauth_data() -> dict:
    if not os.path.exists(OAUTH_FILE):
        raise FileNotFoundError(
            f"{OAUTH_FILE} not found. Run auth/auth_setup.py first to authorize."
        )
    with open(OAUTH_FILE, "r") as f:
        return json.load(f)


def _save_oauth_data(data: dict) -> None:
    with open(OAUTH_FILE, "w") as f:
        json.dump(data, f, indent=2)


def _get_credentials(scopes: list[str]) -> Credentials:
    """
    Loads credentials from oauth_final.json, refreshing if expired,
    and persisting the refreshed access_token back to the file.
    """
    oauth_data = _load_oauth_data()

    creds = Credentials(
        token=oauth_data["access_token"],
        refresh_token=oauth_data["refresh_token"],
        token_uri=oauth_data.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=oauth_data["client_id"],
        client_secret=oauth_data["client_secret"],
        scopes=scopes,
    )

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())

        # Persist refreshed token back to oauth_final.json
        oauth_data["access_token"] = creds.token
        _save_oauth_data(oauth_data)

    return creds


def build_gmail_service():
    creds = _get_credentials(GMAIL_SCOPES)
    return build("gmail", "v1", credentials=creds)


def build_calendar_service():
    creds = _get_credentials(CALENDAR_SCOPES)
    return build("calendar", "v3", credentials=creds)