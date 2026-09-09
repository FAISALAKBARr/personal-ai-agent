# Personal AI Agent (WhatsApp) — Phase 1

Phase 1 slice of the Personal AI Operating System spec: a working request
loop (message -> orchestrator -> capability firewall -> tool -> scheduler ->
audit log -> reply). Two WhatsApp gateways are included: a mock gateway for
testing without any real connection, and a Baileys bridge for real WhatsApp.
See `docs/architecture-phase1.md` for the design rationale, schema, and open
decisions.

## Prerequisites
- Docker + Docker Compose
- Ollama installed natively on the host (not in Docker — see step 3), with an NVIDIA driver new enough for GPU support if you have a GPU
- ~3GB free disk for the Ollama model, wherever you pointed `OLLAMA_MODELS`

## 1. Configure
```bash
cp .env.example .env
```
Edit `.env`:
- `WHATSAPP_ALLOWED_NUMBERS` — your own number (this is what gates who the bot will even respond to)
- Leave `WHATSAPP_PROVIDER=mock` for now — that's what lets you test everything below without a real WhatsApp connection

## 2. Start the stack
```bash
cd infra
docker compose up -d --build
```
This starts Postgres, Redis, and the FastAPI backend (the Baileys bridge builds too but sits idle until `WHATSAPP_PROVIDER=baileys`). Tables are created automatically on first boot (see `app/database/init_db.py`).

## 3. Pull the model
Ollama runs natively on your machine for this setup, not inside Docker (see the comment in `docker-compose.yml` for why — short version: GPU passthrough into a container is unnecessary extra setup on Windows when the native install already has GPU access). Pull the model the same way you already installed Ollama — a regular PowerShell:
```powershell
ollama pull phi4-mini
```
`phi4-mini` is the default. It's Ollama's role in this chain (OpenRouter -> Gemini -> Claude -> Ollama, see `agents/providers.py`) that drives this choice: Ollama only ever gets used as the last resort when every cloud option has failed, so predictability matters more than raw speed there. `phi4-mini` has no "thinking" mode to misbehave (unlike `qwen3`, which caused a real 61s timeout in testing before `think: false` was added) and carries a 131K context window — `qwen3:4b` is still a fine general-purpose alternative if you want to compare, just pull it and change `OLLAMA_MODEL` in `.env` to match, then `docker compose restart backend`.

## 4. Check it's alive
```bash
curl http://localhost:8000/health
# {"status":"ok"}
```

## 5. Test the full loop (no real WhatsApp needed yet)
The mock gateway accepts a normalized message directly — this is standing in for what a real gateway adapter would hand the orchestrator.

**Simple read (no scheduling involved — good first test):**
```bash
curl -X POST http://localhost:8000/messages \
  -H "Content-Type: application/json" \
  -d '{"user_id": "+62812xxxxxxxx", "message_id": "test-001", "text": "Apa saja task saya?"}'
```
Use the *exact* number you put in `WHATSAPP_ALLOWED_NUMBERS`. Watch the backend logs (`docker compose logs -f backend`) — the reply prints there via `[MOCK WHATSAPP -> ...]` since there's no real WhatsApp to send it to yet.

**Reminder + scheduler (the Definition-of-Done #1 test):**
```bash
curl -X POST http://localhost:8000/messages \
  -H "Content-Type: application/json" \
  -d '{"user_id": "+62812xxxxxxxx", "message_id": "test-002", "text": "Remind me tomorrow at 8am to work on my portfolio"}'
```
Then try `docker compose restart backend` and confirm the reminder still fires at the right time — that's the "survives a restart" requirement, and it works because APScheduler's jobstore is Postgres, not memory.

**CONFIRM flow (delete_task is a placeholder specifically to prove this path):**
```bash
curl -X POST http://localhost:8000/messages \
  -H "Content-Type: application/json" \
  -d '{"user_id": "+62812xxxxxxxx", "message_id": "test-003", "text": "Delete task <some-task-id>"}'
```
Reply `setuju` (matching message_id) to confirm, or `batal` to cancel.

## 6. Run the tests
```bash
docker compose exec backend pytest
```

## 7. Connect real WhatsApp (Baileys bridge)
Everything above works with the mock gateway. This step swaps in your actual
WhatsApp account. Uses your real number — read the ban-risk note in
`docs/architecture-phase1.md` §8 first, and consider a spare number rather
than your daily driver if you're unsure.

```bash
docker compose up -d --build baileys-bridge
docker compose logs -f baileys-bridge
```
A QR code prints in the log. On your phone: WhatsApp > Settings > Linked
Devices > Link a Device, then scan it. The log should print "Connected to
WhatsApp." Session credentials persist in the `baileys_auth` volume, so you
only need to do this once — it survives restarts.

Now switch the backend over:
```bash
# in .env: WHATSAPP_PROVIDER=baileys
docker compose restart backend
```
Message your bot's number for real. Same rules apply as the curl tests above
— only numbers in `WHATSAPP_ALLOWED_NUMBERS` get a response.

Currently handles plain text only (no images/voice/documents yet — that's
future work, the message schema already has a `media` field waiting for it).
If you ever need to re-pair (new number, logged out), delete the
`baileys_auth` volume and restart: `docker compose down -v baileys-bridge && docker compose up -d baileys-bridge`.

## What's here vs. what's next
Included: FastAPI app, Postgres schema, Capability Firewall, Approval Engine, scheduler, audit logging, 4 tools, Ollama + Claude provider abstraction, mock WhatsApp gateway, **and now the Baileys bridge for real WhatsApp**.

Not yet: media messages (images/voice/docs), the admin dashboard, and everything from Phase 2 onward in the original spec (calendar, knowledge base/pgvector, research & career agent, email/GitHub/n8n integrations, browser agent, production hardening).
