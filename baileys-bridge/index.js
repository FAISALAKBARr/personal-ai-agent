const crypto = require("crypto");

const express = require("express");
const pino = require("pino");
const qrcode = require("qrcode-terminal");
const {
  default: makeWASocket,
  useMultiFileAuthState,
  DisconnectReason,
} = require("@whiskeysockets/baileys");

const PORT = process.env.PORT || 3000;
const BACKEND_URL = process.env.BACKEND_URL || "http://backend:8000";
const WEBHOOK_SECRET = process.env.WHATSAPP_WEBHOOK_SECRET || "changeme";
const AUTH_DIR = process.env.AUTH_DIR || "./auth_info";

let sock = null;

// "+62812xxxxxxxx" -> "62812xxxxxxxx@s.whatsapp.net"
function toJid(phone) {
  return phone.replace(/^\+/, "") + "@s.whatsapp.net";
}

// "62812xxxxxxxx@s.whatsapp.net" -> "+62812xxxxxxxx"
function fromJid(jid) {
  return "+" + jid.split("@")[0];
}

function sign(bodyString) {
  // Must match app/whatsapp/baileys.py:verify_signature() on the Python side —
  // same secret, same algorithm, raw hex digest (no "sha256=" prefix).
  return crypto.createHmac("sha256", WEBHOOK_SECRET).update(bodyString).digest("hex");
}

async function forwardToBackend(payload) {
  const body = JSON.stringify(payload);
  try {
    const res = await fetch(`${BACKEND_URL}/messages`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Hub-Signature-256": sign(body),
      },
      body,
    });
    if (!res.ok) {
      console.error("backend rejected message:", res.status, await res.text());
    }
  } catch (err) {
    console.error("failed to forward message to backend:", err.message);
  }
}

async function startConnection() {
  const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR);

  sock = makeWASocket({
    auth: state,
    logger: pino({ level: "warn" }),
  });

  sock.ev.on("creds.update", saveCreds);

  sock.ev.on("connection.update", (update) => {
    const { connection, lastDisconnect, qr } = update;

    if (qr) {
      console.log("Scan this QR code with WhatsApp (Linked Devices > Link a Device):");
      qrcode.generate(qr, { small: true });
    }

    if (connection === "close") {
      const statusCode = lastDisconnect?.error?.output?.statusCode;
      const loggedOut = statusCode === DisconnectReason.loggedOut;
      console.log(
        "Connection closed.",
        loggedOut ? "Logged out — delete auth_info/ and restart to re-pair." : "Reconnecting in 5s..."
      );
      if (!loggedOut) setTimeout(startConnection, 5000);
    } else if (connection === "open") {
      console.log("Connected to WhatsApp.");
    }
  });

  sock.ev.on("messages.upsert", async ({ messages, type }) => {
    console.log(`[debug] messages.upsert fired: type=${type} count=${messages?.length ?? 0}`);
    for (const msg of messages) {
      console.log(`[debug] key=${JSON.stringify(msg.key)}`);

      if (!msg.message || msg.key.fromMe) {
        console.log("[debug] SKIP: no message content, or fromMe");
        continue;
      }

      // Phase 1 is private-chat only. Group JIDs end in @g.us, broadcast
      // lists differently again — none of those are "the user talking to
      // their own agent", so don't treat them as commands.
      if (!msg.key.remoteJid.endsWith("@s.whatsapp.net")) {
        console.log(`[debug] SKIP: not a private chat, remoteJid=${msg.key.remoteJid}`);
        continue;
      }

      // Phase 1b: plain text only. Media/voice notes are future work
      // (the InboundMessage schema on the Python side already has a `media`
      // field ready for when that gets built).
      const text = msg.message.conversation || msg.message.extendedTextMessage?.text;
      if (!text) {
        console.log(`[debug] SKIP: no plain text extracted, message=${JSON.stringify(msg.message)}`);
        continue;
      }

      console.log(`[debug] forwarding: from=${fromJid(msg.key.remoteJid)} text=${JSON.stringify(text)}`);
      await forwardToBackend({
        type: "message",
        from: fromJid(msg.key.remoteJid),
        id: msg.key.id,
        timestamp: msg.messageTimestamp,
        text,
      });
    }
  });
}

startConnection().catch((err) => {
  console.error("failed to start WhatsApp connection:", err);
  process.exit(1);
});

// --- HTTP API the FastAPI backend calls to send outgoing messages ---
const app = express();
app.use(express.json());

app.get("/health", (_req, res) => res.json({ status: "ok", connected: !!sock?.user }));

// Same secret as the inbound HMAC signing — only the backend should ever
// call this. Previously unauthenticated: anything able to reach this port
// could make the bridge send WhatsApp messages as the user with no checks
// at all. Combined with removing the host port publish in docker-compose.yml,
// this is defense in depth, not either/or.
function requireBridgeSecret(req, res, next) {
  const provided = req.headers["x-bridge-secret"];
  if (!provided || provided !== WEBHOOK_SECRET) {
    return res.status(401).json({ error: "unauthorized" });
  }
  next();
}

app.post("/send", requireBridgeSecret, async (req, res) => {
  const { to, text } = req.body || {};
  if (!to || !text) return res.status(400).json({ error: "to and text are required" });
  if (!sock?.user) return res.status(503).json({ error: "not connected to WhatsApp yet" });

  try {
    await sock.sendMessage(toJid(to), { text });
    res.json({ status: "sent" });
  } catch (err) {
    console.error("send failed:", err.message);
    res.status(500).json({ error: err.message });
  }
});

app.listen(PORT, () => console.log(`Baileys bridge listening on :${PORT}`));
