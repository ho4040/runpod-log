"""RunPod API client for fetching pod logs."""

import sys

import httpx

from .auth import load_credentials, refresh_token_headless, save_credentials


def _request_logs(pod_id: str, token: str, team_id: str) -> httpx.Response:
    """Make a single log request."""
    url = f"https://hapi.runpod.net/v1/pod/{pod_id}/logs"
    headers = {
        "accept": "*/*",
        "authorization": f"Bearer {token}",
        "content-type": "application/json",
        "x-team-id": team_id,
    }
    with httpx.Client() as client:
        return client.get(url, headers=headers, timeout=30.0)


def fetch_logs(pod_id: str, token: str, team_id: str) -> dict:
    """Fetch logs from a RunPod pod with automatic token refresh on 401.

    Args:
        pod_id: The RunPod pod ID
        token: JWT authentication token
        team_id: RunPod team ID

    Returns:
        API response as dictionary

    Raises:
        httpx.HTTPStatusError: If the API request fails after retry
    """
    response = _request_logs(pod_id, token, team_id)

    if response.status_code == 401:
        print("Token expired, refreshing via headless browser...", file=sys.stderr)
        new_creds = refresh_token_headless()
        if new_creds:
            save_credentials(
                new_creds["token"],
                new_creds["team_id"],
                new_creds.get("session_id"),
            )
            print("Token refreshed successfully.", file=sys.stderr)
            response = _request_logs(
                pod_id, new_creds["token"], new_creds["team_id"]
            )
        else:
            print(
                "Token refresh failed. Run 'runpod-log login' to re-authenticate.",
                file=sys.stderr,
            )

    response.raise_for_status()
    return response.json()
