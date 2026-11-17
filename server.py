import os
import json
import sqlite3
from datetime import datetime, timezone
import requests
from flask import Flask, request, jsonify, render_template_string
from fira_bot import FiraTransactionalBot

app = Flask(__name__)
bot = FiraTransactionalBot()

VERIFY_TOKEN = os.getenv("FB_VERIFY_TOKEN", "fira_bot_messenger_2026")
PAGE_ACCESS_TOKEN = os.getenv("FB_PAGE_ACCESS_TOKEN")
DB_PATH = "/tmp/fira_monitor.db"

# Caché en memoria para no repetir la llamada a /me en cada polling del navegador
ASSET_CACHE = {"id": None, "name": None, "checked": False}


def init_db():
    with sqlite3.connect(DB_PATH, timeout=5) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                type TEXT NOT NULL,
                details TEXT NOT NULL,
                payload TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS state (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        conn.commit()


def set_state(key: str, value: str):
    if value is None:
        return
    with sqlite3.connect(DB_PATH, timeout=5) as conn:
        conn.execute(
            "INSERT INTO state (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, str(value))
        )
        conn.commit()


def get_state(key: str, default: str = None) -> str:
    with sqlite3.connect(DB_PATH, timeout=5) as conn:
        row = conn.execute("SELECT value FROM state WHERE key = ?", (key,)).fetchone()
        return row[0] if row else default


def log_event(event_type: str, details: str, payload: dict = None):
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    payload_str = json.dumps(payload, ensure_ascii=False, indent=2) if payload else ""

    with sqlite3.connect(DB_PATH, timeout=5) as conn:
        conn.execute(
            "INSERT INTO events (timestamp, type, details, payload) VALUES (?, ?, ?, ?)",
            (timestamp, event_type, details, payload_str)
        )
        # Mantener solo los últimos 40 registros
        conn.execute(
            "DELETE FROM events WHERE id NOT IN (SELECT id FROM events ORDER BY id DESC LIMIT 40)"
        )
        conn.commit()

    # Log en consola para la pestaña "Logs" de Render
    print(f"[{timestamp}] [{event_type}] {details}", flush=True)
    if payload:
        print(json.dumps(payload, ensure_ascii=False), flush=True)


def get_connected_asset():
    """Consulta una vez a Graph API el nombre e ID de la Página asociada al token."""
    if ASSET_CACHE["checked"]:
        return ASSET_CACHE["id"], ASSET_CACHE["name"]

    ASSET_CACHE["checked"] = True
    if not PAGE_ACCESS_TOKEN:
        return None, None

    try:
        r = requests.get(
            "https://graph.facebook.com/v26.0/me",
            params={"fields": "id,name", "access_token": PAGE_ACCESS_TOKEN},
            timeout=5
        )
        if r.status_code == 200:
            info = r.json()
            ASSET_CACHE["id"] = info.get("id")
            ASSET_CACHE["name"] = info.get("name")
            if ASSET_CACHE["id"]:
                set_state("connected_page_id", ASSET_CACHE["id"])
            if ASSET_CACHE["name"]:
                set_state("connected_page_name", ASSET_CACHE["name"])
    except Exception as e:
        print(f"[ASSET_LOOKUP_WARN] Could not fetch /me: {e}", flush=True)

    return ASSET_CACHE["id"], ASSET_CACHE["name"]


init_db()


@app.after_request
def enable_cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "POST, GET, OPTIONS"
    return response


# 1. ENDPOINT HTML / JS / Postman
@app.route("/api/chat", methods=["POST", "OPTIONS"])
def api_chat():
    if request.method == "OPTIONS":
        return "", 200

    data = request.get_json(force=True)
    user_id = data.get("user_id", "web_test_user")
    message = data.get("message", "")

    reply = bot.handle_message(user_id, message)
    return jsonify({"response": reply})


# 2. ENDPOINT DE FACEBOOK MESSENGER (Verificación y Webhook)
@app.route("/webhook", methods=["GET"])
def fb_verify():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        log_event("WEBHOOK_VERIFIED", "Meta webhook verification succeeded (HTTP 200).")
        return challenge, 200
    log_event("WEBHOOK_VERIFY_FAILED", "Invalid verification token.")
    return "Token de verificación inválido", 403


@app.route("/webhook", methods=["POST"])
def fb_webhook():
    data = request.get_json()

    if data.get("object") == "page":
        for entry in data.get("entry", []):
            page_id = entry.get("id")
            if page_id:
                set_state("connected_page_id", page_id)

            for messaging_event in entry.get("messaging", []):
                sender_id = messaging_event.get("sender", {}).get("id")
                message = messaging_event.get("message", {})

                if "text" in message and not message.get("is_echo", False):
                    user_text = message["text"]
                    set_state("last_sender_id", sender_id)

                    log_event(
                        "WEBHOOK_RECEIVED",
                        f"Incoming Messenger event | Page Asset ID: {page_id} | Sender PSID: {sender_id} | Text: '{user_text}'",
                        {"page_id": page_id, "sender_psid": sender_id, "message": user_text}
                    )

                    reply_text = bot.handle_message(sender_id, user_text)
                    log_event(
                        "BOT_REPLY_GENERATED",
                        f"Validated response generated for PSID {sender_id} ({len(reply_text)} chars)."
                    )

                    send_fb_message(sender_id, reply_text, page_id=page_id)

        return "EVENT_RECEIVED", 200
    return "Not Found", 404


def send_fb_message(recipient_id: str, text: str, page_id: str = None):
    """Envía un mensaje de texto mediante Meta Graph API v26.0."""
    if not PAGE_ACCESS_TOKEN:
        log_event("GRAPH_API_ERROR", "FB_PAGE_ACCESS_TOKEN is missing in Render environment variables.")
        return False, {"error": "Missing FB_PAGE_ACCESS_TOKEN"}

    url = "https://graph.facebook.com/v26.0/me/messages"
    params = {"access_token": PAGE_ACCESS_TOKEN}
    payload = {
        "recipient": {"id": recipient_id},
        "message": {"text": text}
    }
    headers = {"Content-Type": "application/json"}
    active_page = page_id or get_state("connected_page_id", "unknown")

    log_event(
        "GRAPH_API_SEND_REQUEST",
        f"POST {url} | Page Asset ID: {active_page} | Recipient PSID: {recipient_id}",
        {"recipient": payload["recipient"], "message_preview": text[:200]}
    )

    try:
        r = requests.post(url, params=params, json=payload, headers=headers, timeout=10)
        resp_json = r.json() if r.content else {}
        if r.status_code == 200:
            log_event(
                "GRAPH_API_SEND_SUCCESS",
                f"HTTP 200 OK | Delivered via pages_messaging | message_id: {resp_json.get('message_id')}",
                resp_json
            )
            return True, resp_json
        else:
            log_event("GRAPH_API_SEND_ERROR", f"HTTP {r.status_code}: {r.text}", resp_json)
            return False, resp_json
    except Exception as e:
        log_event("GRAPH_API_EXCEPTION", f"Error connecting to Graph API: {e}")
        return False, {"error": str(e)}


# 3. PANEL DE MONITOREO EN INGLÉS PARA APP REVIEW
MONITOR_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>FIRA - Chatbot | Server-to-Server Messenger Console</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f0f2f5; margin: 20px; color: #1c1e21; }
    .container { max-width: 960px; margin: 0 auto; }
    .card { background: #fff; border-radius: 8px; padding: 16px 20px; margin-bottom: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.12); }
    .badge { display: inline-block; padding: 4px 10px; border-radius: 12px; font-size: 12px; font-weight: 600; background: #e6f4ea; color: #137333; }
    .row { display: flex; gap: 20px; flex-wrap: wrap; }
    .col { flex: 1; min-width: 280px; }
    label { font-size: 13px; font-weight: 600; color: #606770; display: block; margin-bottom: 6px; }
    input { width: 100%; box-sizing: border-box; padding: 9px 12px; font-size: 14px; border: 1px solid #ccd0d5; border-radius: 6px; margin-bottom: 10px; }
    button { background: #1877f2; color: #fff; border: none; border-radius: 6px; padding: 9px 16px; font-size: 14px; font-weight: 600; cursor: pointer; }
    button:hover { background: #166fe5; }
    .meta-line { margin: 6px 0; font-size: 14px; }
    code { background: #f0f2f5; padding: 2px 6px; border-radius: 4px; font-size: 13px; }
    .log-item { border-left: 4px solid #1877f2; padding: 10px 12px; margin-bottom: 10px; background: #f8f9fa; border-radius: 0 6px 6px 0; font-size: 13px; }
    .log-success { border-left-color: #137333; background: #f2f9f4; }
    .log-error { border-left-color: #c5221f; background: #fdf3f2; }
    pre { background: #eceff3; padding: 8px; border-radius: 4px; overflow-x: auto; font-size: 12px; margin: 6px 0 0 0; }
    .status-msg { font-size: 13px; margin-left: 10px; font-weight: 600; }
  </style>
</head>
<body>
<div class="container">
  <div class="card">
    <h2 style="margin: 0 0 8px 0;">FIRA - Chatbot | Messenger API Console</h2>
    <span class="badge">Server-to-Server App (App ID: 2395925307178064)</span>
    <span class="badge" style="background:#e7f3ff; color:#1877f2;">Permission: pages_messaging</span>
  </div>

  <div class="card row">
    <div class="col">
      <h3 style="margin-top:0;">1. Connected Asset Selection</h3>
      <div class="meta-line"><strong>Selected Facebook Page:</strong> <code id="page_name">Loading...</code></div>
      <div class="meta-line"><strong>Page Asset ID:</strong> <code id="page_id">Loading...</code></div>
      <div class="meta-line"><strong>Authentication:</strong> <code>Page Access Token (Configured: <span id="token_status">-</span>)</code></div>
      <div class="meta-line"><strong>Active Messenger User (PSID):</strong> <code id="last_psid">-</code></div>
    </div>

    <div class="col">
      <h3 style="margin-top:0;">2. Live Send Action (App UI &rarr; Messenger)</h3>
      <label for="manual_msg">Message to send via Graph API (POST /v26.0/me/messages):</label>
      <input type="text" id="manual_msg" value="Hello from FIRA Chatbot App UI! Confirmed live delivery via pages_messaging.">
      <button onclick="sendManual()">Send Message to Messenger</button>
      <span id="send_status" class="status-msg"></span>
      <p style="font-size:12px; color:#606770; margin-top:8px;">
        Note: Automated replies are also sent immediately whenever a webhook event arrives from Messenger.
      </p>
    </div>
  </div>

  <div class="card">
    <h3 style="margin-top:0;">3. Live Server Logs (Incoming Webhooks &amp; Outgoing Graph API Calls)</h3>
    <div id="logs">Loading events...</div>
  </div>
</div>

<script>
  function escapeHtml(str) {
    return String(str || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  async function fetchLogs() {
    try {
      const res = await fetch('/api/logs');
      const data = await res.json();
      document.getElementById('page_name').innerText = data.connected_page_name || 'Not detected yet';
      document.getElementById('page_id').innerText = data.connected_page_id || 'Waiting for webhook...';
      document.getElementById('token_status').innerText = data.token_configured ? 'Yes (Hidden)' : 'No';
      document.getElementById('last_psid').innerText = data.last_sender_id || 'Send a message from Messenger first';

      const container = document.getElementById('logs');
      if (!data.events.length) {
        container.innerHTML = '<p style="color:#606770;">No webhook events yet. Send "hola" to the Facebook Page in Messenger.</p>';
        return;
      }
      container.innerHTML = data.events.map(e => {
        let cls = 'log-item';
        if (e.type.includes('SUCCESS')) cls += ' log-success';
        if (e.type.includes('ERROR') || e.type.includes('FAILED')) cls += ' log-error';
        return `<div class="${cls}">
          <strong>[${escapeHtml(e.timestamp)}] ${escapeHtml(e.type)}</strong><br>
          ${escapeHtml(e.details)}
          ${e.payload ? `<pre>${escapeHtml(e.payload)}</pre>` : ''}
        </div>`;
      }).join('');
    } catch (err) {
      console.error(err);
    }
  }

  async function sendManual() {
    const statusEl = document.getElementById('send_status');
    const msg = document.getElementById('manual_msg').value;
    statusEl.style.color = '#606770';
    statusEl.innerText = 'Sending...';

    const res = await fetch('/api/send_test', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({message: msg})
    });
    const data = await res.json();
    if (data.ok) {
      statusEl.style.color = '#137333';
      statusEl.innerText = 'Sent (HTTP 200 OK)';
    } else {
      statusEl.style.color = '#c5221f';
      statusEl.innerText = 'Error: ' + (data.error || 'Failed');
    }
    fetchLogs();
  }

  fetchLogs();
  setInterval(fetchLogs, 2000);
</script>
</body>
</html>
"""


@app.route("/monitor", methods=["GET"])
def monitor_ui():
    get_connected_asset()
    return render_template_string(MONITOR_HTML)


@app.route("/api/logs", methods=["GET"])
def get_logs():
    asset_id, asset_name = get_connected_asset()
    with sqlite3.connect(DB_PATH, timeout=5) as conn:
        rows = conn.execute(
            "SELECT timestamp, type, details, payload FROM events ORDER BY id DESC LIMIT 30"
        ).fetchall()

    events = [
        {"timestamp": r[0], "type": r[1], "details": r[2], "payload": r[3]}
        for r in rows
    ]

    return jsonify({
        "connected_page_id": get_state("connected_page_id") or asset_id,
        "connected_page_name": get_state("connected_page_name") or asset_name,
        "last_sender_id": get_state("last_sender_id"),
        "token_configured": bool(PAGE_ACCESS_TOKEN),
        "events": events
    })


@app.route("/api/send_test", methods=["POST"])
def send_test():
    data = request.get_json(force=True)
    text = data.get("message", "").strip()
    psid = get_state("last_sender_id")
    if not psid:
        return jsonify({"ok": False, "error": "Send a message from Messenger first to capture PSID."}), 400
    if not text:
        return jsonify({"ok": False, "error": "Message cannot be empty."}), 400
    ok, resp = send_fb_message(psid, text)
    return jsonify({"ok": ok, "response": resp}), (200 if ok else 500)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"FIRA Chatbot server active on port {port}", flush=True)
    app.run(host="0.0.0.0", port=port, debug=False)