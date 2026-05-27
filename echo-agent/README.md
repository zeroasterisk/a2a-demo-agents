# Echo Agent

A demo A2A agent that echoes messages back to the sender.

## What it does

- Registers with the A2A relay on startup (self-approves with admin key)
- Serves `GET /.well-known/agent.json` — agent card
- Serves `POST /a2a` — receives `tasks/send` messages and replies with `"Echo: <original text>"`
- Serves `GET /health` — health check

## Requirements

```bash
pip install -r requirements.txt
```

## Run

```bash
# Set environment variables
export RELAY_URL=http://localhost:8765
export RELAY_ADMIN_KEY=<your-relay-admin-key>
export AGENT_PORT=9001   # optional, default 9001

python main.py
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `RELAY_URL` | `http://localhost:8765` | URL of the A2A relay |
| `RELAY_ADMIN_KEY` | *(required)* | Admin key for relay auto-approval |
| `AGENT_PORT` | `9001` | Port to listen on |

## Test

After starting, verify health:
```bash
curl http://localhost:9001/health
```

Check agent card:
```bash
curl http://localhost:9001/.well-known/agent.json | python3 -m json.tool
```

Send a test A2A message (direct, bypassing relay):
```bash
curl -X POST http://localhost:9001/a2a \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "tasks/send",
    "id": "test-1",
    "params": {
      "id": "task-001",
      "metadata": {"sender_agent_id": "test-sender"},
      "messages": [{"role": "user", "parts": [{"type": "text", "text": "Hello!"}]}]
    }
  }'
```
