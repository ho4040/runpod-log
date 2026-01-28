"""RunPod API client for fetching pod logs."""

import httpx


def fetch_logs(pod_id: str, token: str, team_id: str) -> dict:
    """Fetch logs from a RunPod pod.

    Args:
        pod_id: The RunPod pod ID
        token: JWT authentication token
        team_id: RunPod team ID

    Returns:
        API response as dictionary

    Raises:
        httpx.HTTPStatusError: If the API request fails
    """
    url = f"https://hapi.runpod.net/v1/pod/{pod_id}/logs"

    headers = {
        "accept": "*/*",
        "authorization": f"Bearer {token}",
        "content-type": "application/json",
        "x-team-id": team_id,
    }

    with httpx.Client() as client:
        response = client.get(url, headers=headers, timeout=30.0)
        response.raise_for_status()
        return response.json()
