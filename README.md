# A2A Demo Agents

> **⚠️ Personal Hobby Project** — This is an independent, personal project by [Alan Blount](https://github.com/zeroasterisk). It is **not affiliated with, endorsed by, or supported by any employer, company, or organization**. No warranty; use at your own risk.


Two minimal demo agents showcasing the **Agent-to-Agent (A2A)** protocol pattern:
auto-registration with a relay, message receipt, and relay-based replies.

## Agents

### echo-agent (port 9001)

Echoes every message back to the sender with `"Echo: <original text>"`.

- Simple stateless request-reply pattern
- Good for verifying relay connectivity end-to-end

### counter-agent (port 9002)

Counts messages per `sender_agent_id` and replies with the running total:
`"Counter for {sender}: {count} (message: {text})"`.

- Demonstrates in-memory state accumulation per sender
- Each unique sender gets their own independent counter
- Counter resets on process restart (in-memory only)
- Check `/health` to see all current counts

## Architecture

```
[Sender] --POST /a2a--> [Relay] --POST /a2a--> [Echo/Counter Agent]
                                                       |
                          [Relay] <--POST /a2a---------+
                             |
                    [Sender mailbox]
```

Each agent:
1. On startup: revokes old registration, requests auth token, self-approves with admin key
2. Stores Bearer key to authenticate relay calls
3. Receives messages on `POST /a2a`
4. Replies by posting to `{RELAY_URL}/a2a` with the Bearer key and target agent ID

## Prerequisites

```bash
pip install fastapi uvicorn[standard] httpx
```

Or install from each agent directory:
```bash
pip install -r echo-agent/requirements.txt
pip install -r counter-agent/requirements.txt
```

## Run Order

**1. Start the relay first** (must be running before agents register):
```bash
# Relay should already be running at http://localhost:8765
```

**2. Start echo-agent:**
```bash
cd echo-agent/
RELAY_URL=http://localhost:8765 RELAY_ADMIN_KEY=xxx python main.py
```

**3. Start counter-agent (separate terminal):**
```bash
cd counter-agent/
RELAY_URL=http://localhost:8765 RELAY_ADMIN_KEY=xxx python main.py
```

## Test Script

### 1. Register hermes as a sender

```bash
# Revoke any old hermes key
curl -s -X DELETE http://localhost:8765/admin/revoke/hermes \
  -H "X-Admin-Key: $RELAY_ADMIN_KEY"

# Request token
HERMES_TOKEN=$(curl -s -X POST http://localhost:8765/auth/request \
  -H "Content-Type: application/json" \
  -d '{"agent_id":"hermes","name":"Hermes","description":"Test sender"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['request_token'])")

# Approve
HERMES_KEY=$(curl -s -X POST "http://localhost:8765/admin/approve/$HERMES_TOKEN" \
  -H "X-Admin-Key: $RELAY_ADMIN_KEY" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['agent_key'])")

echo "Hermes key: $HERMES_KEY"
```

### 2. Send a message to echo-agent

```bash
curl -s -X POST http://localhost:8765/a2a \
  -H "Authorization: Bearer $HERMES_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "tasks/send",
    "id": "test-1",
    "params": {
      "id": "task-001",
      "metadata": {
        "relay_target_agent_id": "echo-agent",
        "sender_agent_id": "hermes"
      },
      "messages": [{"role": "user", "parts": [{"type": "text", "text": "hello echo!"}]}]
    }
  }'
```

### 3. Poll hermes inbox for the echo reply

```bash
sleep 1
curl -s http://localhost:8765/mailbox/hermes \
  -H "Authorization: Bearer $HERMES_KEY" \
  | python3 -m json.tool
```

You should see a message from `echo-agent` with text `"Echo: hello echo!"`.

### 4. Test counter-agent accumulation

```bash
# Send 3 messages
for i in 1 2 3; do
  curl -s -X POST http://localhost:8765/a2a \
    -H "Authorization: Bearer $HERMES_KEY" \
    -H "Content-Type: application/json" \
    -d "{\"jsonrpc\":\"2.0\",\"method\":\"tasks/send\",\"id\":\"cnt-$i\",\"params\":{\"id\":\"t-$i\",\"metadata\":{\"relay_target_agent_id\":\"counter-agent\",\"sender_agent_id\":\"hermes\"},\"messages\":[{\"role\":\"user\",\"parts\":[{\"type\":\"text\",\"text\":\"count me $i\"}]}]}}" > /dev/null
done

# Poll inbox
sleep 2
curl -s http://localhost:8765/mailbox/hermes \
  -H "Authorization: Bearer $HERMES_KEY" \
  | python3 -m json.tool
# Should show counters 1, 2, 3
```

## Directory Structure

```
a2a-demo-agents/
├── README.md              ← this file
├── echo-agent/
│   ├── main.py            ← FastAPI app
│   ├── requirements.txt
│   └── README.md
└── counter-agent/
    ├── main.py            ← FastAPI app
    ├── requirements.txt
    └── README.md
```
