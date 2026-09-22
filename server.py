import os
import requests
from flask import Flask, request, jsonify
from fira_bot import FiraTransactionalBot

app = Flask(__name__)
bot = FiraTransactionalBot()

# Tokens de configuración para Facebook (los obtienes en developers.facebook.com)
VERIFY_TOKEN = os.getenv("FB_VERIFY_TOKEN", "fira_bot_messenger_2026")
PAGE_ACCESS_TOKEN = os.getenv("FB_PAGE_ACCESS_TOKEN", "TU_PAGE_ACCESS_TOKEN")



# ----------------------------------------------------------------------
# 1. ENDPOINT PARA PRUEBAS WEB DIRECTAS (HTML / JS / Postman)
# ----------------------------------------------------------------------
@app.route("/api/chat", methods=["POST"])
def api_chat():
    """Permite probar el bot desde una cajita de chat web o script."""
    data = request.get_json(force=True)
    user_id = data.get("user_id", "web_test_user")
    message = data.get("message", "")
    
    reply = bot.handle_message(user_id, message)
    return jsonify({"response": reply})


# ----------------------------------------------------------------------
# 2. ENDPOINT DE FACEBOOK MESSENGER (Verificación y Webhook)
# ----------------------------------------------------------------------
@app.route("/webhook", methods=["GET"])
def fb_verify():
    """Meta envía un GET para validar que el webhook te pertenece."""
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        print("✅ Webhook verificado exitosamente por Facebook.")
        return challenge, 200
    return "Token de verificación inválido", 403


@app.route("/webhook", methods=["POST"])
def fb_webhook():
    """Meta envía aquí cada mensaje que un usuario escribe a la Página."""
    data = request.get_json()

    if data.get("object") == "page":
        for entry in data.get("entry", []):
            for messaging_event in entry.get("messaging", []):
                sender_id = messaging_event.get("sender", {}).get("id")
                message = messaging_event.get("message", {})

                # Si es un mensaje de texto entrante (y no un eco del propio bot)
                if "text" in message and not message.get("is_echo", False):
                    user_text = message["text"]
                    print(f"📩 Mensaje recibido de FB ({sender_id}): {user_text}")

                    # Procesar con el bot transaccional
                    reply_text = bot.handle_message(sender_id, user_text)

                    # Enviar la respuesta de vuelta a Messenger
                    send_fb_message(sender_id, reply_text)

        return "EVENT_RECEIVED", 200
    return "Not Found", 404


def send_fb_message(recipient_id: str, text: str):
    """Envía un mensaje de texto de vuelta a la API de Messenger Graph."""
    url = f"https://graph.facebook.com/v21.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    payload = {
        "recipient": {"id": recipient_id},
        "message": {"text": text}
    }
    headers = {"Content-Type": "application/json"}

    try:
        r = requests.post(url, json=payload, headers=headers, timeout=10)
        if r.status_code != 200:
            print(f"❌ Error al enviar mensaje a FB: {r.text}")
    except Exception as e:
        print(f"❌ Excepción al conectar con Graph API: {e}")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"🚀 Servidor de pruebas FIRA activo en el puerto {port}...")
    app.run(host="0.0.0.0", port=port, debug=False)