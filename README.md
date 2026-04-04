# runpod-log

CLI tool for fetching logs from RunPod GPU pods.

Since the official RunPod CLI (`runpodctl`) doesn't support log viewing, this tool uses the unofficial RunPod API to fetch pod logs.

## Features

- Fetch pod logs (one-time)
- Browser-based authentication (Playwright)
- Automatic token refresh using headless browser

## Requirements

- Python 3.10+
- [uv](https://github.com/astral-sh/uv) (recommended) or pip

## Installation

```bash
# Clone the repository
git clone https://github.com/ho4040/runpod-log.git
cd runpod-log

# Create virtual environment and install
uv venv
uv pip install -e .

# Install Playwright browser
uv run playwright install chromium
```

## Usage

### 1. Login

First, authenticate with RunPod. This opens a browser window:

```bash
runpod-log login
```

1. Log in to your RunPod account
2. Navigate to any pod and click to view its logs
3. The CLI automatically captures your credentials

Credentials are saved locally, and browser session is preserved for automatic token refresh.

> **Note (for AI agents):** The browser session (cookies) is persisted to disk via Playwright's `launch_persistent_context`. If you have logged in before, running `runpod-log login` again will open a browser that is **already authenticated** — no manual interaction is needed. The CLI will capture the token automatically within seconds and close the browser. So when credentials expire (401), just run `runpod-log login` again; it is safe to execute non-interactively after the first login.

### 2. Fetch Logs

```bash
# Print all logs (container + system) to stdout
runpod-log logs <pod-id>

# Only container logs (your application stdout/stderr)
runpod-log logs <pod-id> --only container

# Only system logs (RunPod platform events)
runpod-log logs <pod-id> --only system

# Save to file
runpod-log logs <pod-id> > output.log

# Output as JSON
runpod-log logs <pod-id> --json-output
```

## Logout

To clear saved credentials and browser session:

```bash
runpod-log logout
```

This removes:
- `credentials.json` - Token and team ID
- `browser_session/` - Browser session data

Use this when switching accounts or clearing sensitive data from the machine.

## Command Reference

```
runpod-log --help
runpod-log login --help
runpod-log logout --help
runpod-log logs --help
```

## Log Types

RunPod pods produce two types of logs:

- **Container logs**: Application output from your container (stdout/stderr)
- **System logs**: RunPod platform events (volume creation, container lifecycle, etc.)

By default, both types are fetched and prefixed with `[CONTAINER]` or `[SYSTEM]`.

## How It Works

1. **Authentication**: Uses Playwright's persistent browser context (`launch_persistent_context`) to open a Chromium browser. The browser session (cookies, localStorage, IndexedDB) is saved to disk, so subsequent logins will already be authenticated. JWT tokens are captured by intercepting requests to `hapi.runpod.net`.

2. **Token Refresh**: RunPod JWT tokens expire in ~60 seconds. When a 401 error occurs, the tool launches a headless browser using the saved session to automatically obtain a fresh token without user interaction.

3. **Log API**: Calls `https://hapi.runpod.net/v1/pod/{pod_id}/logs` with JWT token and team ID headers.

## Storage Locations

- **Windows**: `%APPDATA%\runpod-log\`
- **Linux/Mac**: `~/.config/runpod-log/`

Files:
- `credentials.json` - Token and team ID
- `browser_session/` - Browser session data for token refresh

## License

MIT
