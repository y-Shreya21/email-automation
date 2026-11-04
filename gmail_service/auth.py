"""
Gmail API OAuth 2.0 Authentication Manager
"""
import os
import json
import socket
from pathlib import Path
from typing import Optional, Any
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build, Resource

# Prevent macOS/ISP timeouts by prioritizing IPv4 when IPv6 routing is non-functional
_orig_getaddrinfo = socket.getaddrinfo

def _ipv4_first_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    if family == 0:
        family = socket.AF_INET
    return _orig_getaddrinfo(host, port, family, type, proto, flags)

socket.getaddrinfo = _ipv4_first_getaddrinfo

class GmailAuthenticator:
    """Handles OAuth 2.0 flow, token caching, and Gmail API service creation."""

    def __init__(self, credentials_path: Path, token_path: Path, scopes: list):
        self.credentials_path = Path(credentials_path)
        if not self.credentials_path.exists():
            candidates = list(self.credentials_path.parent.glob("client_secret_*.json"))
            if candidates:
                self.credentials_path = candidates[0]
        self.token_path = Path(token_path)
        self.scopes = scopes
        self.creds: Optional[Credentials] = None

    def is_credentials_file_present(self) -> bool:
        """Check if client credentials.json or client_secret_*.json exists."""
        return self.credentials_path.exists() and self.credentials_path.stat().st_size > 0

    def get_service(self) -> Resource:
        """
        Authenticate and return Gmail Resource service.
        Launches browser for initial authorization if token.json is absent or invalid.
        """
        if self.token_path.exists():
            try:
                self.creds = Credentials.from_authorized_user_file(str(self.token_path), self.scopes)
            except Exception as e:
                self.creds = None

        # If credentials are not valid or not present, refresh or re-authenticate
        if not self.creds or not self.creds.valid:
            if self.creds and self.creds.expired and self.creds.refresh_token:
                try:
                    self.creds.refresh(Request())
                except Exception:
                    self.creds = None

            if not self.creds:
                if not self.is_credentials_file_present():
                    raise FileNotFoundError(
                        f"OAuth credentials file not found at: {self.credentials_path}\n\n"
                        "To obtain this file:\n"
                        "1. Visit Google Cloud Console: https://console.cloud.google.com/\n"
                        "2. Enable Gmail API (APIs & Services > Library > Gmail API)\n"
                        "3. Go to APIs & Services > Credentials > Create Credentials > OAuth Client ID\n"
                        "4. Select Application Type: 'Desktop App'\n"
                        "5. Download the JSON file and save it as 'credentials.json' in this project folder."
                    )

                flow = InstalledAppFlow.from_client_secrets_file(
                    str(self.credentials_path), self.scopes
                )
                self.creds = flow.run_local_server(port=0)

            # Save the credentials token for subsequent runs
            with open(self.token_path, "w", encoding="utf-8") as token_file:
                token_file.write(self.creds.to_json())

        return build("gmail", "v1", credentials=self.creds)


class MockGmailService:
    """Mock Gmail API service for local testing and dry-run demonstrations."""

    class MockUsers:
        class MockDrafts:
            def create(self, userId: str, body: dict):
                class MockRequest:
                    def execute(self):
                        return {
                            "id": f"mock_draft_{os.urandom(4).hex()}",
                            "message": {"id": f"mock_msg_{os.urandom(4).hex()}"}
                        }
                return MockRequest()

        class MockMessages:
            def send(self, userId: str, body: dict):
                class MockRequest:
                    def execute(self):
                        return {
                            "id": f"mock_sent_{os.urandom(4).hex()}",
                            "threadId": f"thread_{os.urandom(4).hex()}"
                        }
                return MockRequest()

        def drafts(self):
            return self.MockDrafts()

        def messages(self):
            return self.MockMessages()

    def users(self):
        return self.MockUsers()
