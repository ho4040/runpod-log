"""CLI entry point for RunPod Log tool."""

import io
import json
import sys
import time
from pathlib import Path

import click
import httpx

from .api import fetch_logs
from .auth import load_credentials, login_via_browser, refresh_token_headless, save_credentials

# Fix Windows console encoding for Unicode output
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


MAIN_HELP = """
RunPod Log CLI - Fetch and tail logs from RunPod GPU pods.

This tool allows you to retrieve logs from RunPod pods using the unofficial
RunPod API. It supports both one-time log fetching and continuous tailing
to a file.

AUTHENTICATION:
  Before using this tool, you must authenticate with RunPod:

    runpod-log login

  This opens a browser window where you log into RunPod. After logging in
  and viewing any pod's logs, the CLI captures your credentials automatically.
  Credentials are saved locally for future use.

QUICK START:
  1. Login:           runpod-log login
  2. Fetch logs:      runpod-log logs <pod-id>
  3. Tail to file:    runpod-log tail <pod-id> output.log

COMMANDS:
  login   - Authenticate with RunPod via browser
  logs    - Fetch pod logs once and print to stdout
  tail    - Continuously poll for new logs and append to a file

EXIT CODES:
  0 - Success
  1 - Error (authentication failure, network error, etc.)

For AI agents: Use 'tail' command to write logs to a file, then read that
file to analyze the logs. The 'tail' command runs continuously until
interrupted with Ctrl+C.
"""


@click.group(help=MAIN_HELP)
@click.version_option(version="1.0.0", prog_name="runpod-log")
def cli():
    pass


LOGIN_HELP = """
Authenticate with RunPod via browser.

This command opens a Chromium browser window and navigates to the RunPod
console. You need to:

  1. Log in to your RunPod account (if not already logged in)
  2. Navigate to any pod and click to view its logs
  3. The CLI will automatically capture your JWT token and team ID

The credentials are saved to:
  - Windows: %APPDATA%/runpod-log/credentials.json
  - Linux/Mac: ~/.config/runpod-log/credentials.json

You only need to login once. The token may expire after some time,
requiring you to login again.

EXAMPLE:
  runpod-log login

NOTES:
  - Requires a display (cannot run in headless mode)
  - Uses Playwright with Chromium browser
  - The browser window will close automatically after capturing credentials
"""


@cli.command(help=LOGIN_HELP)
def login():
    click.echo("Opening browser for RunPod login...")
    click.echo("Please log in to RunPod and view any pod's logs.")
    try:
        creds = login_via_browser()
        save_credentials(creds["token"], creds["team_id"], creds.get("session_id"))
        click.echo("\nCredentials saved successfully!")
        click.echo(f"Team ID: {creds['team_id']}")
        click.echo(f"Session saved for automatic token refresh.")
        click.echo("\nYou can now use 'runpod-log logs <pod-id>' or 'runpod-log tail <pod-id> <file>'")
    except Exception as e:
        click.echo(f"Error during login: {e}", err=True)
        sys.exit(1)


def get_credentials(token: str | None, team_id: str | None) -> tuple[str, str]:
    """Get credentials from args or saved file."""
    if not token or not team_id:
        creds = load_credentials()
        if creds:
            token = token or creds.get("token")
            team_id = team_id or creds.get("team_id")
        else:
            click.echo("Error: No credentials found.", err=True)
            click.echo("Run 'runpod-log login' to authenticate first.", err=True)
            sys.exit(1)

    if not token or not team_id:
        click.echo("Error: Missing token or team-id.", err=True)
        click.echo("Provide via --token and --team-id options, or run 'runpod-log login'.", err=True)
        sys.exit(1)

    return token, team_id


def extract_logs(result: dict | list) -> list[str]:
    """Extract log lines from API response."""
    if isinstance(result, dict):
        # API returns {"container": [...]} for container logs
        if "container" in result:
            return result["container"]
        elif "logs" in result:
            return result["logs"]
    elif isinstance(result, list):
        return result
    return [json.dumps(result)]


TAIL_HELP = """
Continuously tail logs from a RunPod pod and write to a file.

This command polls the RunPod API at regular intervals and appends any
new log lines to the specified output file. It also prints new logs to
stdout in real-time.

ARGUMENTS:
  POD_ID       The RunPod pod identifier (e.g., 'abc123xyz')
               Find this in the RunPod console URL or pod list.

  OUTPUT_FILE  Path to the output file. New logs are appended.
               The file is created if it doesn't exist.

OPTIONS:
  -t, --token     JWT token (optional if logged in via 'runpod-log login')
  -i, --team-id   Team ID (optional if logged in via 'runpod-log login')
  -n, --interval  Seconds between API polls (default: 5)

BEHAVIOR:
  - Runs continuously until interrupted with Ctrl+C
  - Deduplicates logs: each unique log line is written only once
  - If the output file exists, its contents are loaded to avoid duplicates
  - New log counts are printed to stderr: [+N new lines]
  - On HTTP 401 (token expired), exits with code 1

EXAMPLES:
  # Basic usage (uses saved credentials)
  runpod-log tail abc123xyz /tmp/pod.log

  # Poll every 10 seconds
  runpod-log tail abc123xyz /tmp/pod.log --interval 10

  # With explicit credentials
  runpod-log tail abc123xyz /tmp/pod.log -t "eyJ..." -i "team_xxx"

FOR AI AGENTS:
  Run this command in the background, then read the output file to analyze
  logs. Example workflow:
    1. Start: runpod-log tail <pod-id> /tmp/logs.txt &
    2. Wait a few seconds for logs to accumulate
    3. Read /tmp/logs.txt to analyze the logs
    4. Kill the background process when done
"""


@cli.command(help=TAIL_HELP)
@click.argument("pod_id", metavar="POD_ID")
@click.argument("output_file", metavar="OUTPUT_FILE", type=click.Path())
@click.option(
    "--token", "-t",
    metavar="TOKEN",
    help="JWT authentication token (uses saved credentials if not provided)",
)
@click.option(
    "--team-id", "-i",
    metavar="TEAM_ID",
    help="RunPod team ID (uses saved credentials if not provided)",
)
@click.option(
    "--interval", "-n",
    metavar="SECONDS",
    default=5,
    show_default=True,
    help="Polling interval in seconds",
)
def tail(pod_id: str, output_file: str, token: str | None, team_id: str | None, interval: int) -> None:
    token, team_id = get_credentials(token, team_id)
    output_path = Path(output_file)

    click.echo(f"Tailing logs from pod '{pod_id}' to '{output_file}'")
    click.echo(f"Polling every {interval} seconds. Press Ctrl+C to stop.")

    seen_logs: set[str] = set()

    # Load existing logs from file to avoid duplicates
    if output_path.exists():
        with open(output_path, "r", encoding="utf-8") as f:
            for line in f:
                seen_logs.add(line.rstrip("\n"))
        click.echo(f"Loaded {len(seen_logs)} existing log lines from file.")

    try:
        while True:
            try:
                result = fetch_logs(pod_id, token, team_id)
                logs = extract_logs(result)

                new_logs = []
                for log in logs:
                    if log not in seen_logs:
                        seen_logs.add(log)
                        new_logs.append(log)

                if new_logs:
                    with open(output_path, "a", encoding="utf-8") as f:
                        for log in new_logs:
                            f.write(log + "\n")
                            click.echo(log)

                    click.echo(f"[+{len(new_logs)} new lines]", err=True)

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 401:
                    click.echo("[Token expired, refreshing...]", err=True)
                    new_creds = refresh_token_headless()
                    if new_creds:
                        token = new_creds["token"]
                        team_id = new_creds["team_id"]
                        save_credentials(token, team_id, new_creds.get("session_id"))
                        click.echo("[Token refreshed successfully]", err=True)
                    else:
                        click.echo("Token refresh failed. Run 'runpod-log login' to re-authenticate.", err=True)
                        sys.exit(1)
                else:
                    click.echo(f"Error: HTTP {e.response.status_code}", err=True)
            except httpx.RequestError as e:
                click.echo(f"Request error: {e}", err=True)

            time.sleep(interval)

    except KeyboardInterrupt:
        click.echo(f"\nStopped. Total unique logs: {len(seen_logs)}")


LOGS_HELP = """
Fetch logs from a RunPod pod (one-time).

This command fetches the current logs from a RunPod pod and prints them
to stdout. Use this for a quick snapshot of logs.

ARGUMENTS:
  POD_ID  The RunPod pod identifier (e.g., 'abc123xyz')
          Find this in the RunPod console URL or pod list.

OPTIONS:
  -t, --token       JWT token (optional if logged in via 'runpod-log login')
  -i, --team-id     Team ID (optional if logged in via 'runpod-log login')
  -j, --json-output Print raw JSON response instead of parsed logs

OUTPUT:
  By default, prints one log line per line to stdout.
  With --json-output, prints the full API response as formatted JSON.

EXAMPLES:
  # Fetch and print logs
  runpod-log logs abc123xyz

  # Save to file
  runpod-log logs abc123xyz > /tmp/pod.log

  # Get raw JSON response
  runpod-log logs abc123xyz --json-output

  # With explicit credentials
  runpod-log logs abc123xyz -t "eyJ..." -i "team_xxx"

FOR AI AGENTS:
  Use 'logs' for a one-time snapshot. For continuous monitoring,
  use 'tail' instead which writes to a file you can read periodically.
"""


@cli.command(help=LOGS_HELP)
@click.argument("pod_id", metavar="POD_ID")
@click.option(
    "--token", "-t",
    metavar="TOKEN",
    help="JWT authentication token (uses saved credentials if not provided)",
)
@click.option(
    "--team-id", "-i",
    metavar="TEAM_ID",
    help="RunPod team ID (uses saved credentials if not provided)",
)
@click.option(
    "--json-output", "-j",
    is_flag=True,
    help="Output raw JSON response from API",
)
def logs(pod_id: str, token: str | None, team_id: str | None, json_output: bool) -> None:
    token, team_id = get_credentials(token, team_id)

    try:
        result = fetch_logs(pod_id, token, team_id)

        if json_output:
            click.echo(json.dumps(result, indent=2))
        else:
            for log in extract_logs(result):
                click.echo(log)

    except httpx.HTTPStatusError as e:
        click.echo(f"Error: HTTP {e.response.status_code}", err=True)
        click.echo(f"Response: {e.response.text}", err=True)
        sys.exit(1)
    except httpx.RequestError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


def main():
    """Entry point."""
    cli()


if __name__ == "__main__":
    main()
