# runpod-log

CLI tool for fetching and tailing logs from RunPod GPU pods.

Since the official RunPod CLI (`runpodctl`) doesn't support log viewing, this tool uses the unofficial RunPod API to fetch pod logs.

## Features

- Fetch pod logs (one-time)
- Tail logs continuously to a file
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

### 2. Fetch Logs (One-time)

```bash
# Print logs to stdout
runpod-log logs <pod-id>

# Save to file
runpod-log logs <pod-id> > output.log

# Output as JSON
runpod-log logs <pod-id> --json-output
```

### 3. Tail Logs (Continuous)

Continuously poll for new logs and append to a file:

```bash
runpod-log tail <pod-id> output.log

# Custom polling interval (default: 5 seconds)
runpod-log tail <pod-id> output.log --interval 10
```

The `tail` command:
- Runs continuously until interrupted with Ctrl+C
- Automatically refreshes tokens when they expire
- Deduplicates logs to avoid duplicates

## For AI Agents

This tool is designed to be used by AI agents for log monitoring:

```bash
# Start tailing in background
runpod-log tail <pod-id> /tmp/logs.txt &

# Read the log file periodically to analyze
cat /tmp/logs.txt

# Kill the process when done
kill %1
```

## Command Reference

```
runpod-log --help
runpod-log login --help
runpod-log logs --help
runpod-log tail --help
```

## How It Works

1. **Authentication**: Uses Playwright to open a browser for RunPod login. Captures JWT token from API requests.

2. **Token Refresh**: Saves browser session data. When token expires, uses headless browser to refresh automatically.

3. **Log API**: Calls `https://hapi.runpod.net/v1/pod/{pod_id}/logs` with JWT token.

## Storage Locations

- **Windows**: `%APPDATA%\runpod-log\`
- **Linux/Mac**: `~/.config/runpod-log/`

Files:
- `credentials.json` - Token and team ID
- `browser_session/` - Browser session data for token refresh

## License

MIT
