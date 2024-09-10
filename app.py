import logging
import json
import requests
import re
from flask import Flask, request, jsonify
from flask_cors import CORS
from functools import wraps
import hashlib
import hmac
import aiohttp
import asyncio
import subprocess
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta
import pyodbc
app = Flask(__name__)
load_dotenv()
CORS(app, resources={"/*": {"origins": "*"}})
db_connection_string = (
    "Driver={ODBC Driver 17 for SQL Server};"
    "Server=103.239.89.99,21433;"
    "Database=ArriveChatAppDB;"
    "UID=ArriveDBUsr;"
    "PWD=Arrive@pas12;"
)
ACCESS_TOKEN = os.getenv("access_token")
PHONE_NUMBER_ID_1 = os.getenv("phone_number_id_1")
PHONE_NUMBER_ID_2 = os.getenv("phone_number_id_2")
ng=os.getenv("authtoken")
VERSION = "v20.0"

def log_chat_to_db(user_input, bot_response, phone_number):
    try:
        with pyodbc.connect(db_connection_string) as conn:
            cursor = conn.cursor()
            query = """
                INSERT INTO tbWhatsapp_Messages (user_input, bot_response, phone_number)
                VALUES (?, ?, ?)
            """
            cursor.execute(query, (user_input, bot_response, phone_number))
            conn.commit()
    except pyodbc.Error as e:
        logging.error(f"Failed to log chat to database: {e}")
        
async def send_message(recipient, data):
    headers = {
        "Content-type": "application/json",
        "Authorization": f"Bearer {ACCESS_TOKEN}",
    }

    async with aiohttp.ClientSession() as session:
        url = f"https://graph.facebook.com/{VERSION}/{PHONE_NUMBER_ID_1}/messages"
        try:
            async with session.post(url, data=data, headers=headers) as response:
                if response.status == 200:
                    html = await response.text()
                    return {"status": response.status, "response": html}
                else:
                    return {"status": response.status, "response": str(response)}
        except aiohttp.ClientConnectorError as e:
            return {"status": 500, "response": str(e)}



@app.route("/send-message", methods=["POST"])
def send_whatsapp_message():
    try:
        content = request.get_json()
        recipient = content.get("recipient")
        attachment_id = content.get("attachment_id")  # Assuming attachment ID is provided in the request
        
        if recipient and attachment_id:
            data = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": recipient,
                "type": "template",
                "template": {
                    "name": "intel",
                    "language": {
                        "code": "en"
                    },
                    "components": [
                        {
                            "type": "header",
                            "parameters": [
                                {
                                    "type": "image",
                                    "image": {
                                        "id": attachment_id
                                    }
                                }
                            ]
                        },
                        {
                            "type": "button",
                            "sub_type": "url",
                            "index": "0",
                            "parameters": [
                                {
                                    "type": "text",
                                    "text": "https://www.waysaheadglobal.com/index.html"
                                }
                            ]
                        }
                    ]
                }
            }

            data_json = json.dumps(data)  # Convert the dictionary to a JSON string
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(send_message(recipient, data_json))
            loop.close()
            return jsonify(result)
        else:
            return jsonify({"error": "Recipient and attachment_id are required"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/send-custom-message", methods=["POST"])
def send_custom_whatsapp_message():
    try:
        content = request.get_json()
        recipient = content.get("recipient")
        text = content.get("text")

        if recipient and text:
            data = json.dumps({
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": recipient,
                "type": "text",
                "text": {"preview_url": False, "body": text},
            })
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(send_message(recipient, data))
            loop.close()

            return jsonify(result)
        else:
            return jsonify({"error": "Recipient and text are required"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500




def log_http_response(response):
    logging.info(f"Status: {response.status_code}")
    logging.info(f"Content-type: {response.headers.get('content-type')}")
    logging.info(f"Body: {response.text}")

def get_text_message_input(recipient, text):
    return json.dumps({
    "messaging_product": "whatsapp",
    "recipient_type": "individual",
    "to": recipient,
    "type": "text",
    "text": {
        "body": text
    }
})

def generate_response(response):
    headers = {
        'Content-Type': 'application/json'
    }
    data = {'user_input': response}

    try:
        api_response = requests.post(
            'https://ae.arrive.waysdatalabs.com/api/chat', 
            headers=headers, 
            data=json.dumps(data),
            timeout=10  # Adding a timeout for the request
        )
        api_response.raise_for_status()  # This will raise an HTTPError for bad responses (4xx, 5xx)
        
        response_json = api_response.json()  # Parse the JSON response
        c_response = response_json.get('response')
        if c_response is None:
            logging.error("API response did not contain 'response' key.")
            return None
        
        return c_response

    except requests.exceptions.RequestException as e:
        logging.error(f"Error calling API: {e}")
        return None



def send_messages(data):
    headers = {
        "Content-type": "application/json",
        "Authorization": f"Bearer {ACCESS_TOKEN}",
    }

    url = f"https://graph.facebook.com/{VERSION}/{PHONE_NUMBER_ID_2}/messages"

    try:
        response = requests.post(url, data=data, headers=headers, timeout=10)
        response.raise_for_status()
    except requests.Timeout:
        logging.error("Timeout occurred while sending message")
        return jsonify({"status": "error", "message": "Request timed out"}), 408
    except requests.RequestException as e:
        logging.error(f"Request failed due to: {e}")
        return jsonify({"status": "error", "message": "Failed to send message"}), 500
    else:
        log_http_response(response)
        return response

def process_text_for_whatsapp(text):
    pattern = r"\【.*?\】"
    text = re.sub(pattern, "", text).strip()

    pattern = r"\\(.?)\\*"
    replacement = r"\1"
    whatsapp_style_text = re.sub(pattern, replacement, text)

    return whatsapp_style_text


def process_whatsapp_message(body):
    wa_id = body["entry"][0]["changes"][0]["value"]["contacts"][0]["wa_id"]
    name = body["entry"][0]["changes"][0]["value"]["contacts"][0]["profile"]["name"]
    message = body["entry"][0]["changes"][0]["value"]["messages"][0]
    message_body = message["text"]["body"]
    sender_number = message["from"]
    response = generate_response(message_body)
    data = get_text_message_input(sender_number, response)
    bot_response = generate_response(message_body)
    log_chat_to_db(user_input=message_body, bot_response=bot_response, phone_number=sender_number)
    data = get_text_message_input(sender_number, bot_response)
    send_messages(data)

def is_valid_whatsapp_message(body):
    return (body.get("object")
        and body.get("entry")
        and body["entry"][0].get("changes")
        and body["entry"][0]["changes"][0].get("value")
        and body["entry"][0]["changes"][0]["value"].get("messages")
        and body["entry"][0]["changes"][0]["value"]["messages"][0])

# Security

def validate_signature(payload, signature):
    expected_signature = hmac.new(
        bytes("d8273c13f5b8209eb98a57e667bccf50", "latin-1"),
        msg=payload.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected_signature, signature)

def signature_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        signature = request.headers.get("X-Hub-Signature-256", "")[7:]
        if not validate_signature(request.data.decode("utf-8"), signature):
            logging.info("Signature verification failed!")
            return jsonify({"status": "error", "message": "Invalid signature"}), 403
        return f(*args, **kwargs)
    return decorated_function

@app.route("/api/dashboard", methods=["GET"])
def get_unique_phone_numbers():
    try:
        with pyodbc.connect(db_connection_string) as conn:
            cursor = conn.cursor()

            # Query to get the name if available, otherwise return phone number
            query = """
                SELECT 
                    CASE 
                        WHEN name IS NOT NULL AND name != '' THEN name 
                        ELSE phone_number 
                    END AS display_name
                FROM tbClients
            """
            cursor.execute(query)
            display_names = [row.display_name for row in cursor.fetchall()]
        
        return jsonify({
            "phoneNumbersJson": json.dumps(display_names),  # Return as JSON string
            "totalPhoneNumbers": len(display_names)
        }), 200
    except pyodbc.Error as e:
        logging.error(f"Failed to retrieve unique phone numbers: {e}")
        return jsonify({"error": "Failed to retrieve data"}), 500

@app.route("/api/fetch_chat", methods=["POST"])
def fetch_chat_by_phone_number():
    try:
        content = request.get_json()
        phone_number = content.get("phone_number")

        if phone_number:
            with pyodbc.connect(db_connection_string) as conn:
                cursor = conn.cursor()
                query = """
                    SELECT user_input, bot_response, timestamp
                    FROM tbWhatsapp_Messages
                    WHERE phone_number = ?
                    ORDER BY timestamp ASC  -- Oldest first for WhatsApp-like behavior
                """
                cursor.execute(query, phone_number)
                chats = []
                for row in cursor.fetchall():
                    timestamp = row.timestamp

                    # Split date and time from the timestamp
                    date = timestamp.strftime("%Y-%m-%d")  # Example format: "2024-09-10"
                    time = timestamp.strftime("%I:%M %p")  # Example format: "9:15 AM"

                    chats.append({
                        "user_input": row.user_input,
                        "bot_response": row.bot_response,
                        "date": date,  # Separate date field
                        "time": time   # Separate time field, formatted in WhatsApp style
                    })

            return jsonify({"chats": chats}), 200
        else:
            return jsonify({"error": "Phone number is required"}), 400
    except pyodbc.Error as e:
        logging.error(f"Failed to fetch chats: {e}")
        return jsonify({"error": "Failed to retrieve data"}), 500


@app.route("/api/save_response", methods=["POST"])
def save_response():
    try:
        content = request.get_json()
        phone_number = content.get("phone_number")
        bot_response = content.get("bot_response")

        if phone_number and bot_response:
            with pyodbc.connect(db_connection_string) as conn:
                cursor = conn.cursor()
                query = """
                    INSERT INTO tbWhatsapp_Messages (user_input, bot_response, phone_number)
                    VALUES ('ADMIN', ?, ?)
                """
                cursor.execute(query, bot_response, phone_number)
                conn.commit()
            return jsonify({"status": "success", "message": "Response saved successfully"}), 200
        else:
            return jsonify({"error": "Phone number and bot response are required"}), 400
    except pyodbc.Error as e:
        logging.error(f"Failed to save response: {e}")
        return jsonify({"error": "Failed to save data"}), 500




# Views

@app.route("/webhook", methods=["GET"])
def webhook_get():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    if mode and token:
        if mode == "subscribe" and token == "12345":
            logging.info("WEBHOOK_VERIFIED")
            return challenge, 200
        else:
            logging.info("VERIFICATION_FAILED")
            return jsonify({"status": "error", "message": "Verification failed"}), 403
    else:
        logging.info("MISSING_PARAMETER")
        return jsonify({"status": "error", "message": "Missing parameters"}), 400

@app.route("/webhook", methods=["POST"])
@signature_required
def webhook_post():
    body = request.get_json()
    if (body.get("entry", [{}])[0]
        .get("changes", [{}])[0]
        .get("value", {})
        .get("statuses")):
        logging.info("Received a WhatsApp status update.")
        return jsonify({"status": "ok"}), 200
    try:
        if is_valid_whatsapp_message(body):
            process_whatsapp_message(body)
            return jsonify({"status": "ok"}), 200
        else:
            return jsonify({"status": "error", "message": "Not a WhatsApp API event"}), 404
    except json.JSONDecodeError:
        logging.error("Failed to decode JSON")
        return jsonify({"status": "error", "message": "Invalid JSON provided"}), 400

import subprocess
import threading
def run_ngrok():
    try:
        subprocess.run([
            "ngrok", "http",
            "--authtoken=2kHvsJYgyCk9tLWPrWsRYCAMYwG_pvxhJC8bsEFHptmKACfL",
            "--domain=locust-upward-easily.ngrok-free.app",
            "8005"
        ], check=True)
    except subprocess.CalledProcessError as e:
        print(f"An error occurred: {e}")
        # Handle the error, if needed
        pass

if __name__ == "__main__":
    # Start ngrok in a separate thread
    ngrok_thread = threading.Thread(target=run_ngrok)
    ngrok_thread.start()

    # Start Flask app
    app.run(port=8005, debug=False)
