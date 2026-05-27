# Counter Agent

A demo A2A agent that counts messages per sender and replies with the running total.

## What it does

- Registers with the A2A relay on startup (self-approves with admin key)
- Serves `GET /.well-known/agent.json` — agent card
- Serves `POST /a2a` — receives `tasks/send` messages, increments per-sender counter, replies with `"Counter for {sender}: {count} (message: {text})"`
- Serves `GET /health` — health check + current counts dict

## Requirements

```bash
pip install -r requirements.txt
```

## Run

```bash
# Set environment variables
export RELAY_URL=http://localhost:8765
export RELAY_ADMIN_KEY=<your-relay-admin-key>
export AGENT_PORT=9002   # optional, default 9002

python main.py
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `RELAY_URL` | `http://localhost:8765` | URL of the A2A relay |
| `RELAY_ADMIN_KEY` | *(required)* | Admin key for relay auto-approval |
| `AGENT_PORT` | `9002` | Port to listen on |

## State

The counter is **in-memory** — it resets when the process restarts. Each unique `sender_agent_id` gets its own counter. Check `/health` to see all current counts:

```bash
curl http://localhost:9002/health
```

## Test

Send a direct A2A message:
```bash
curl -X POST http://localhost:9002/a2a \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "tasks/send",
    "id": "test-1",
    "params": {
      "id": "task-001",
      "metadata": {"sender_agent_id": "hermes"},
      "messages": [{"role": "user", "parts": [{"type": "text", "text": "Increment please"}]}]
    }
  }'
```

Each call from the same sender increments their counter.
