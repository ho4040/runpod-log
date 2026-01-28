"""Browser-based authentication for RunPod."""

import json
import os
from pathlib import Path

from playwright.sync_api import sync_playwright


def get_config_dir() -> Path:
    """Get the config directory for storing credentials."""
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home()))
    else:
        base = Path.home() / ".config"
    config_dir = base / "runpod-log"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def get_credentials_path() -> Path:
    """Get the path to the credentials file."""
    return get_config_dir() / "credentials.json"


def get_session_path() -> Path:
    """Get the path to browser session storage."""
    return get_config_dir() / "browser_session"


def save_credentials(token: str, team_id: str, session_id: str | None = None) -> None:
    """Save credentials to local file."""
    creds = {"token": token, "team_id": team_id}
    if session_id:
        creds["session_id"] = session_id
    get_credentials_path().write_text(json.dumps(creds, indent=2))


def load_credentials() -> dict | None:
    """Load credentials from local file."""
    path = get_credentials_path()
    if path.exists():
        return json.loads(path.read_text())
    return None


def clear_credentials() -> tuple[bool, bool]:
    """Clear all stored credentials and browser session.

    Returns:
        Tuple of (credentials_deleted, session_deleted)
    """
    import shutil

    creds_deleted = False
    session_deleted = False

    creds_path = get_credentials_path()
    if creds_path.exists():
        creds_path.unlink()
        creds_deleted = True

    session_path = get_session_path()
    if session_path.exists():
        shutil.rmtree(session_path)
        session_deleted = True

    return creds_deleted, session_deleted


def extract_session_id_from_token(token: str) -> str | None:
    """Extract session ID from JWT token payload."""
    import base64
    try:
        # JWT format: header.payload.signature
        payload = token.split(".")[1]
        # Add padding if needed
        payload += "=" * (4 - len(payload) % 4)
        decoded = base64.urlsafe_b64decode(payload)
        data = json.loads(decoded)
        return data.get("sid")  # session ID is in 'sid' field
    except Exception:
        return None


def login_via_browser() -> dict:
    """Open browser for user to login and capture credentials.

    Returns:
        dict with 'token', 'team_id', and 'session_id' keys
    """
    token = None
    team_id = None
    session_id = None
    session_path = get_session_path()

    with sync_playwright() as p:
        # Use persistent context to save session
        browser = p.chromium.launch_persistent_context(
            user_data_dir=str(session_path),
            headless=False,
        )
        page = browser.new_page()

        # Intercept network requests to capture the auth token
        def handle_request(request):
            nonlocal token, team_id, session_id
            auth_header = request.headers.get("authorization", "")
            if auth_header.startswith("Bearer ") and "hapi.runpod.net" in request.url:
                token = auth_header.replace("Bearer ", "")
                team_id = request.headers.get("x-team-id", "")
                session_id = extract_session_id_from_token(token)

        page.on("request", handle_request)

        # Navigate to RunPod console
        page.goto("https://www.runpod.io/console/pods")

        print("Please login to RunPod in the browser window.")
        print("After logging in, click on any pod to view its logs.")
        print("The CLI will automatically capture your credentials.")

        # Wait for user to login and make a request that contains the token
        while not token or not team_id:
            page.wait_for_timeout(1000)

        print("\nCredentials captured successfully!")
        browser.close()

    return {"token": token, "team_id": team_id, "session_id": session_id}


def refresh_token_headless() -> dict | None:
    """Refresh token using headless browser with saved session.

    Returns:
        dict with new 'token', 'team_id', 'session_id' or None if failed
    """
    session_path = get_session_path()
    if not session_path.exists():
        return None

    token = None
    team_id = None
    session_id = None

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch_persistent_context(
                user_data_dir=str(session_path),
                headless=True,  # Headless mode for refresh
            )
            page = browser.new_page()

            # Intercept network requests to capture the new token
            def handle_request(request):
                nonlocal token, team_id, session_id
                auth_header = request.headers.get("authorization", "")
                if auth_header.startswith("Bearer ") and "hapi.runpod.net" in request.url:
                    token = auth_header.replace("Bearer ", "")
                    team_id = request.headers.get("x-team-id", "")
                    session_id = extract_session_id_from_token(token)

            page.on("request", handle_request)

            # Navigate to pods page - this will trigger token refresh if session valid
            page.goto("https://www.runpod.io/console/pods", wait_until="networkidle")

            # Wait a bit for any API calls
            page.wait_for_timeout(3000)

            # Click on a pod if available to trigger logs API call
            try:
                # Try to find and click on a pod row
                pod_link = page.locator('a[href*="/pod/"]').first
                if pod_link:
                    pod_link.click()
                    page.wait_for_timeout(3000)
            except Exception:
                pass

            browser.close()

        if token and team_id:
            return {"token": token, "team_id": team_id, "session_id": session_id}
    except Exception:
        pass

    return None
