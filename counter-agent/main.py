"""
Counter Agent — A2A demo agent that counts messages per sender.

Registers with relay on startup, serves A2A tasks/send endpoint,
keeps an in-memory count per sender_agent_id, and replies with
"Counter for {sender}: {count} (message: {text})".
"""

import asyncio
import logging
import os
import uuid
from collections import defaultdict

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("counter-agent")

RELAY_URL = os.environ.get("RELAY_URL", "http://localhost:8765")
RELAY_ADMIN_KEY = os.environ.get("RELAY_ADMIN_KEY", "")
AGENT_PORT = int(os.environ.get("AGENT_PORT", "9002"))

AGENT_ID = "counter-agent"
AGENT_NAME = "Counter Agent"
AGENT_DESCRIPTION = "Counts messages per sender and reports the running total"

app = FastAPI(title="Counter Agent")
app.state.bearer_key = None
# In-memory counter: sender_agent_id -> count
counts: dict[str, int] = defaultdict(int)


async def register_with_relay() -> str:
    """Register this agent with the relay and return Bearer key."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        # 1. Idempotent cleanup — revoke any existing registration
        try:
            r = await client.delete(f"{RELAY_URL}/admin/revoke/{AGENT_ID}",
                                    headers={"X-Admin-Key": RELAY_ADMIN_KEY})
            logger.info(f"Revoke existing: {r.status_code}")
        except Exception as e:
            logger.warning(f"Revoke failed (may not exist): {e}")

        # 2. Request auth token
        r = await client.post(f"{RELAY_URL}/auth/request", json={
            "agent_id": AGENT_ID,
            "name": AGENT_NAME,
            "description": AGENT_DESCRIPTION,
        })
        r.raise_for_status()
        data = r.json()
        token = data.get("request_token") or data.get("token")
        logger.info(f"Got request token: {token[:8]}..." if token else "No token!")

        # 3. Admin approve
        r = await client.post(f"{RELAY_URL}/admin/approve/{token}",
                               headers={"X-Admin-Key": RELAY_ADMIN_KEY})
        r.raise_for_status()
        data = r.json()
        bearer_key = data.get("agent_key") or data.get("key") or data.get("bearer")
        logger.info(f"Got bearer key: {bearer_key[:8]}..." if bearer_key else f"Full response: {data}")
        return bearer_key


async def poll_and_reply_loop():
    """Poll relay mailbox every 2s and reply with running count."""
    await asyncio.sleep(2)
    async with httpx.AsyncClient(timeout=10.0) as client:
        while True:
            try:
                if app.state.bearer_key:
                    r = await client.get(
                        f"{RELAY_URL}/mailbox/{AGENT_ID}",
                        headers={"Authorization": f"Bearer {app.state.bearer_key}"},
                    )
                    msgs = r.json() if isinstance(r.json(), list) else r.json().get("messages", [])
                    for m in msgs:
                        sender = m.get("sender_agent_id", "unknown")
                        params = m.get("a2a_payload", {}).get("params", {})
                        text = ""
                        for msg in params.get("messages", []):
                            for part in msg.get("parts", []):
                                if part.get("type") == "text":
                                    text = part.get("text", "")
                        if sender and sender != AGENT_ID:
                            counts[sender] += 1
                            count = counts[sender]
                            reply_text = f"Counter for {sender}: {count} (received: {text!r})"
                            reply = {
                                "jsonrpc": "2.0", "method": "tasks/send", "id": "counter-reply",
                                "params": {
                                    "id": str(uuid.uuid4()),
                                    "metadata": {"relay_target_agent_id": sender, "sender_agent_id": AGENT_ID},
                                    "messages": [{"role": "user", "parts": [{"type": "text", "text": reply_text}]}],
                                },
                            }
                            await client.post(f"{RELAY_URL}/a2a", json=reply,
                                headers={"Authorization": f"Bearer {app.state.bearer_key}"})
                            logger.info(f"Replied to {sender}: {reply_text}")
                        msg_id = m.get("message_id")
                        if msg_id:
                            await client.post(f"{RELAY_URL}/mailbox/{AGENT_ID}/ack",
                                json={"message_ids": [msg_id]},
                                headers={"Authorization": f"Bearer {app.state.bearer_key}"})
            except Exception as e:
                logger.warning(f"Poll loop error: {e}")
            await asyncio.sleep(2)


@app.on_event("startup")
async def startup():
    logger.info(f"Counter Agent starting on port {AGENT_PORT}, relay={RELAY_URL}")
    if not RELAY_ADMIN_KEY:
        logger.warning("RELAY_ADMIN_KEY not set — relay registration will be skipped")
        return
    try:
        key = await register_with_relay()
        app.state.bearer_key = key
        logger.info("✓ Registered with relay successfully")
        asyncio.create_task(poll_and_reply_loop())
    except Exception as e:
        logger.error(f"✗ Failed to register with relay: {e}")


@app.get("/.well-known/agent.json")
async def agent_card():
    return JSONResponse({
        "name": AGENT_NAME,
        "description": AGENT_DESCRIPTION,
        "url": f"http://localhost:{AGENT_PORT}",
        "version": "1.0.0",
        "protocolVersion": "0.3.0",
        "preferredTransport": "JSONRPC",
        "capabilities": {"streaming": False},
        "defaultInputModes": ["text"],
        "defaultOutputModes": ["text"],
        "skills": [
            {
                "id": "counter",
                "name": "Counter",
                "description": "Counts messages per sender agent",
                "tags": ["counter", "demo", "state"],
                "examples": ["Count this", "How many messages?"],
            }
        ],
    })


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "agent_id": AGENT_ID,
        "registered": app.state.bearer_key is not None,
        "counts": dict(counts),
    }


@app.post("/a2a")
async def handle_a2a(request: Request):
    body = await request.json()
    logger.info(f"Received A2A payload: {body}")

    try:
        params = body.get("params", {})
        metadata = params.get("metadata", {})
        sender = metadata.get("sender_agent_id", "unknown")
        messages = params.get("messages", [])

        # Extract text from first user message
        text = ""
        for msg in messages:
            if msg.get("role") == "user":
                for part in msg.get("parts", []):
                    if part.get("type") == "text":
                        text = part.get("text", "")
                        break
                if text:
                    break

        # Increment per-sender counter
        counts[sender] += 1
        count = counts[sender]
        reply_text = f"Counter for {sender}: {count} (message: {text})"
        logger.info(f"Message from '{sender}': {text!r} → count={count}")

        # Reply via relay
        if app.state.bearer_key and sender and sender != "unknown":
            reply_payload = {
                "jsonrpc": "2.0",
                "method": "tasks/send",
                "id": "counter-reply",
                "params": {
                    "id": str(uuid.uuid4()),
                    "metadata": {
                        "relay_target_agent_id": sender,
                        "sender_agent_id": AGENT_ID,
                    },
                    "messages": [
                        {
                            "role": "user",
                            "parts": [{"type": "text", "text": reply_text}],
                        }
                    ],
                },
            }
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.post(
                    f"{RELAY_URL}/a2a",
                    json=reply_payload,
                    headers={"Authorization": f"Bearer {app.state.bearer_key}"},
                )
                logger.info(f"Relay reply status: {r.status_code} — {r.text[:200]}")
        else:
            logger.warning(f"Cannot reply: bearer_key={bool(app.state.bearer_key)}, sender={sender!r}")

        # Return A2A-compliant acknowledgement
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": body.get("id"),
            "result": {
                "id": params.get("id", str(uuid.uuid4())),
                "status": {"state": "completed"},
                "messages": [
                    {
                        "role": "agent",
                        "parts": [{"type": "text", "text": reply_text}],
                    }
                ],
            },
        })

    except Exception as e:
        logger.exception(f"Error handling A2A request: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=AGENT_PORT, log_level="info")
