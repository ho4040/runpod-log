"""CLI entry point for RunPod Log tool."""

import io
import json
import sys

import click
import httpx

from .api import fetch_logs
from .auth import clear_credentials, load_credentials, login_via_browser, save_credentials

# Fix Windows console encoding for Unicode output
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


MAIN_HELP = """
RunPod Log CLI - Fetch logs from RunPod GPU pods.

This tool allows you to retrieve logs from RunPod pods using the unofficial
RunPod API.

AUTHENTICATION:
  Before using this tool, you must authenticate with RunPod:

    runpod-log login

  This opens a browser window where you log into RunPod. After logging in
  and viewing any pod's logs, the CLI captures your credentials automatically.
  Credentials are saved locally for future use.

QUICK START:
  1. Login:           runpod-log login
  2. Fetch logs:      runpod-log logs <pod-id>

COMMANDS:
  login   - Authenticate with RunPod via browser
  logout  - Clear saved credentials and browser session
  logs    - Fetch pod logs once and print to stdout

EXIT CODES:
  0 - Success
  1 - Error (authentication failure, network error, etc.)
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

AI AGENTS:
  The browser session (cookies) is saved to disk. If you have logged in
  before, running this command again will open a browser that is ALREADY
  AUTHENTICATED - no manual interaction needed. The token is captured
  automatically within seconds and the browser closes itself.
  When you get a 401 error, just run 'runpod-log login' to refresh
  credentials. It is safe to run non-interactively after the first login.
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
        click.echo("\nYou can now use 'runpod-log logs <pod-id>'")
    except Exception as e:
        click.echo(f"Error during login: {e}", err=True)
        sys.exit(1)


LOGOUT_HELP = """
Clear saved credentials and browser session.

This command removes all locally stored authentication data:
  - credentials.json (JWT token, team ID, session ID)
  - browser_session/ (Playwright browser session data)

Use this command when you want to:
  - Log out from the current RunPod account
  - Switch to a different RunPod account
  - Clear sensitive data from this machine

After logout, you will need to run 'runpod-log login' again to use
the logs command.

STORAGE LOCATIONS:
  - Windows: %APPDATA%/runpod-log/
  - Linux/Mac: ~/.config/runpod-log/

EXAMPLE:
  runpod-log logout
"""


@cli.command(help=LOGOUT_HELP)
def logout():
    creds_deleted, session_deleted = clear_credentials()

    if creds_deleted or session_deleted:
        if creds_deleted:
            click.echo("Credentials cleared.")
        if session_deleted:
            click.echo("Browser session cleared.")
        click.echo("\nLogged out successfully.")
    else:
        click.echo("No credentials found. Already logged out.")


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


def extract_logs(result: dict | list, log_type: str = "all") -> list[str]:
    """Extract log lines from API response.

    Args:
        result: API response (dict with 'container' and/or 'system' keys, or list)
        log_type: Which logs to extract - 'container', 'system', or 'all' (default)

    Returns:
        List of log lines
    """
    if isinstance(result, dict):
        # Check if this is the expected RunPod format with container/system keys
        has_runpod_format = "container" in result or "system" in result

        if has_runpod_format:
            logs = []

            if log_type in ("all", "system") and result.get("system"):
                for line in result["system"]:
                    logs.append(f"[SYSTEM] {line}")

            if log_type in ("all", "container") and result.get("container"):
                for line in result["container"]:
                    logs.append(f"[CONTAINER] {line}")

            return logs  # Return empty list if no logs of requested type

        # Fallback for other response formats
        if "logs" in result:
            return result["logs"]

    elif isinstance(result, list):
        return result

    return [json.dumps(result)]


@cli.command(hidden=True)
@click.argument("args", nargs=-1)
def tail(args) -> None:
    """Deprecated: tail command has been removed."""
    click.echo("The 'tail' command has been removed.", err=True)
    click.echo("", err=True)
    click.echo("Please use 'runpod-log logs <pod-id>' instead:", err=True)
    click.echo("  runpod-log logs <pod-id> > output.log", err=True)
    sys.exit(1)


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
  --only            Filter to show only 'container' or 'system' logs (optional)
  -j, --json-output Print raw JSON response instead of parsed logs

LOG TYPES:
  RunPod pods have two types of logs:
  - container: Application logs from your container (stdout/stderr)
  - system: RunPod platform logs (volume creation, container events, etc.)

  By default, BOTH container and system logs are shown together.
  Each log line is prefixed with [CONTAINER] or [SYSTEM] to indicate its type.

OUTPUT:
  By default, prints one log line per line to stdout.
  With --json-output, prints the full API response as formatted JSON.

EXAMPLES:
  # Fetch and print all logs (RECOMMENDED - shows both container and system)
  runpod-log logs abc123xyz

  # Save to file
  runpod-log logs abc123xyz > /tmp/pod.log

  # Get raw JSON response
  runpod-log logs abc123xyz --json-output

  # Filter to only container logs (use only when you need to exclude system logs)
  runpod-log logs abc123xyz --only container

  # Filter to only system logs (use only when you need to exclude container logs)
  runpod-log logs abc123xyz --only system

  # With explicit credentials
  runpod-log logs abc123xyz -t "eyJ..." -i "team_xxx"

FOR AI AGENTS:
  IMPORTANT: Do NOT use --only flag unless specifically asked to filter logs.
  By default, both container and system logs are shown, which provides
  complete information for debugging.
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
    "--only",
    metavar="TYPE",
    type=click.Choice(["container", "system"], case_sensitive=False),
    default=None,
    help="Filter to show only 'container' or 'system' logs (default: show both)",
)
@click.option(
    "--json-output", "-j",
    is_flag=True,
    help="Output raw JSON response from API",
)
def logs(pod_id: str, token: str | None, team_id: str | None, only: str | None, json_output: bool) -> None:
    token, team_id = get_credentials(token, team_id)
    log_type = only if only else "all"

    try:
        result = fetch_logs(pod_id, token, team_id)

        if json_output:
            click.echo(json.dumps(result, indent=2))
        else:
            for log in extract_logs(result, log_type):
                click.echo(log)

    except httpx.HTTPStatusError as e:
        click.echo(f"Error: HTTP {e.response.status_code}", err=True)
        if e.response.status_code in (401, 404):
            click.echo("\nAuthentication expired. Attempting automatic re-authentication...", err=True)
            from .auth import login_via_browser, save_credentials
            try:
                creds = login_via_browser()
                save_credentials(creds["token"], creds["team_id"], creds.get("session_id"))
                click.echo("Re-authentication successful. Please retry the command.", err=True)
            except Exception as login_err:
                click.echo(f"Auto re-authentication failed: {login_err}", err=True)
                click.echo("Manual login required: run 'runpod-log login'", err=True)
        else:
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
