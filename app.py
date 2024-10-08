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
            user_query = "SELECT id FROM tbClients WHERE phone_number = ?"
            cursor.execute(user_query, (phone_number,))
            user = cursor.fetchone()

            if user is None:
                insert_user_query = "INSERT INTO tbClients (phone_number) VALUES (?)"
                cursor.execute(insert_user_query, (phone_number,))
                conn.commit()
                cursor.execute(user_query, (phone_number,))
                user = cursor.fetchone()            
            user_id = user.id
            insert_message_query = """
                INSERT INTO tbWhatsapp_Messages (user_input, bot_response, phone_number, user_id)
                VALUES (?, ?, ?, ?)
            """
            cursor.execute(insert_message_query, (user_input, bot_response, phone_number, user_id))
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
            query = """
                SELECT u.phone_number, 
                       ISNULL(u.name, u.phone_number) AS display_name,
                       MAX(m.timestamp) AS last_conversation_date,
                       (SELECT TOP 1 bot_response
                        FROM tbWhatsapp_Messages
                        WHERE tbWhatsapp_Messages.phone_number = u.phone_number
                        AND tbWhatsapp_Messages.bot_response IS NOT NULL
                        ORDER BY timestamp DESC) AS last_bot_response
                FROM tbClients u
                LEFT JOIN tbWhatsapp_Messages m ON u.phone_number = m.phone_number
                GROUP BY u.phone_number, u.name
            """
            cursor.execute(query)
            users = cursor.fetchall()

            phone_numbers_json = []
            last_conversation_dates = {}

            for user in users:
                # Store the last conversation date in dd-mm format (without the year)
                last_conversation_dates[user.phone_number] = user.last_conversation_date.strftime("%d-%m") if user.last_conversation_date else None
                
                user_info = {
                    "phone_number": user.phone_number,
                    "last_bot_response": user.last_bot_response
                }
                
                # Include name only if it's not null
                if user.display_name != user.phone_number:
                    user_info["name"] = user.display_name
                
                phone_numbers_json.append(user_info)
            
            # Sort the phone numbers by last conversation date (latest first)
            sorted_phone_numbers_json = sorted(phone_numbers_json, key=lambda x: last_conversation_dates[x['phone_number']], reverse=True)

        return jsonify({
            "lastConversationDates": dict(sorted(last_conversation_dates.items(), key=lambda item: item[1], reverse=True)),
            "phoneNumbersJson": sorted_phone_numbers_json,
            "totalPhoneNumbers": len(phone_numbers_json)
        }), 200
    except pyodbc.Error as e:
        logging.error(f"Failed to retrieve unique phone numbers: {e}")
        return jsonify({"error": "Failed to retrieve data"}), 500



@app.route("/api/dashboardv1", methods=["GET"])
def get_unique_phone_numbersv1():
    try:
        with pyodbc.connect(db_connection_string) as conn:
            cursor = conn.cursor()
            query = """
                SELECT u.phone_number, 
                       ISNULL(u.name, u.phone_number) AS display_name,
                       MAX(m.timestamp) AS last_conversation_date,
                       (SELECT TOP 1 user_input
                        FROM tbWhatsapp_Messages
                        WHERE tbWhatsapp_Messages.phone_number = u.phone_number
                        AND tbWhatsapp_Messages.user_input IS NOT NULL
                        ORDER BY timestamp DESC) AS last_user_message
                FROM tbClients u
                LEFT JOIN tbWhatsapp_Messages m ON u.phone_number = m.phone_number
                GROUP BY u.phone_number, u.name
            """
            cursor.execute(query)
            users = cursor.fetchall()

            phone_numbers_json = []
            last_conversation_dates = {}
            
            for user in users:
                last_conversation_dates[user.phone_number] = user.last_conversation_date.strftime("%Y-%m-%d") if user.last_conversation_date else None
                
                user_info = {
                    "phone_number": user.phone_number,
                    "last_user_message": user.last_user_message
                }
                
                # Include name only if it's not null
                if user.display_name != user.phone_number:
                    user_info["name"] = user.display_name
                
                phone_numbers_json.append(user_info)
            
        return jsonify({
            "lastConversationDates": last_conversation_dates,
            "phoneNumbersJson": phone_numbers_json,
            "totalPhoneNumbers": len(phone_numbers_json)
        }), 200
    except pyodbc.Error as e:
        logging.error(f"Failed to retrieve unique phone numbers: {e}")
        return jsonify({"error": "Failed to retrieve data"}), 500




@app.route("/api/fetch_chatv1", methods=["POST"])
def fetch_chat_by_phone_numberv1():
    try:
        content = request.get_json()
        phone_number = content.get("phone_number")

        if phone_number:
            with pyodbc.connect(db_connection_string) as conn:
                cursor = conn.cursor()

                # Get the user_id from the tbClients table using the provided phone number
                user_query = "SELECT id FROM tbClients WHERE phone_number = ?"
                cursor.execute(user_query, phone_number)
                user = cursor.fetchone()

                if user is None:
                    return jsonify({"error": "Phone number not found"}), 404

                user_id = user.id

                # Fetch the messages for the provided phone number, ordered by timestamp DESC
                message_query = """
                    SELECT user_input, bot_response, timestamp, user_id
                    FROM tbWhatsapp_Messages
                    WHERE phone_number = ?
                    ORDER BY timestamp DESC
                """
                cursor.execute(message_query, phone_number)

                # Group chats by date
                chats_by_date = {}
                for row in cursor.fetchall():
                    timestamp = row.timestamp
                    date = timestamp.strftime("%d-%m-%Y")  # Group by date (e.g., "09-09-2024")
                    time = timestamp.strftime("%I:%M %p")  # Time format (e.g., "9:15 AM")

                    # Prepare message format based on user_id
                    message = {
                        "time": time,
                        "bot_response": row.bot_response
                    }
                    
                    if row.user_id != -1:
                        message["user_input"] = row.user_input

                    # Append the message to the correct date group
                    if date not in chats_by_date:
                        chats_by_date[date] = []

                    chats_by_date[date].append(message)

            return jsonify({"Dates": chats_by_date}), 200
        else:
            return jsonify({"error": "Phone number is required"}), 400
    except pyodbc.Error as e:
        logging.error(f"Failed to fetch chats: {e}")
        return jsonify({"error": "Failed to retrieve data"}), 500
        

@app.route("/api/fetch_chat", methods=["POST"])
def fetch_chat_by_phone_number():
    try:
        content = request.get_json()
        phone_number = content.get("phone_number")

        if phone_number:
            with pyodbc.connect(db_connection_string) as conn:
                cursor = conn.cursor()

                # Get the user_id from the tbClients table using the provided phone number
                user_query = "SELECT id FROM tbClients WHERE phone_number = ?"
                cursor.execute(user_query, phone_number)
                user = cursor.fetchone()

                if user is None:
                    return jsonify({"error": "Phone number not found"}), 404

                user_id = user.id

                # Fetch the messages for the provided phone number, ordered by timestamp DESC
                message_query = """
                    SELECT user_input, bot_response, timestamp, user_id
                    FROM tbWhatsapp_Messages
                    WHERE phone_number = ?
                    ORDER BY timestamp ASC
                """
                cursor.execute(message_query, phone_number)

                # Group chats by date
                chats_by_date = {}
                for row in cursor.fetchall():
                    timestamp = row.timestamp
                    date = timestamp.strftime("%d-%m-%Y")  # Group by date (e.g., "03-09-2024")
                    time = timestamp.strftime("%I:%M %p")  # Time format (e.g., "9:15 AM")

                    # Prepare message format based on user_id
                    message = {
                        "time": time,
                        "bot_response": row.bot_response
                    }
                    
                    if row.user_id != -1:
                        message["user_input"] = row.user_input

                    # Append the message to the correct date group
                    if date not in chats_by_date:
                        chats_by_date[date] = []

                    chats_by_date[date].append(message)

                # Formatting the output to have "actual_date" directly associated with chats
                simplified_response = []
                for date, messages in chats_by_date.items():
                    simplified_response.append({
                        "actual_date": date,
                        "chats": messages
                    })

            return jsonify({"dates": simplified_response}), 200
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

                # Use a placeholder user ID for admin messages
                admin_user_id = -1  # Use -1 or another placeholder value

                # Insert the message with the placeholder user ID
                query = """
                    INSERT INTO tbWhatsapp_Messages (user_id, user_input, bot_response, phone_number)
                    VALUES (?, 'ADMIN', ?, ?)
                """
                cursor.execute(query, admin_user_id, bot_response, phone_number)
                conn.commit()

            return jsonify({"status": "success", "message": "Response saved successfully"}), 200
        else:
            return jsonify({"error": "Phone number and bot response are required"}), 400
    except pyodbc.Error as e:
        logging.error(f"Failed to save response: {e}")
        return jsonify({"error": "Failed to save data"}), 500

@app.route("/api/update_name", methods=["POST"])
def update_name():
    try:
        content = request.get_json()
        phone_number = content.get("phone_number")
        name = content.get("name")
        if not phone_number or not name:
            return jsonify({"error": "Phone number and name are required"}), 400

        with pyodbc.connect(db_connection_string) as conn:
            cursor = conn.cursor()
            query = "UPDATE tbClients SET name = ? WHERE phone_number = ?"
            cursor.execute(query, name, phone_number)
            if cursor.rowcount == 0:
                return jsonify({"error": "Phone number not found"}), 404
            conn.commit()        
        return jsonify({"message": "Name updated successfully"}), 200
    except pyodbc.Error as e:
        logging.error(f"Failed to update name: {e}")
        return jsonify({"error": "Failed to update name"}), 500


@app.route("/api/latest_chat", methods=["GET"])
def get_latest_chat():
    try:
        with pyodbc.connect(db_connection_string) as conn:
            cursor = conn.cursor()
            
            # Get the phone number with the most recent interaction (latest last_conversation_date)
            query = """
                SELECT TOP 1 u.phone_number
                FROM tbClients u
                LEFT JOIN tbWhatsapp_Messages m ON u.phone_number = m.phone_number
                GROUP BY u.phone_number
                ORDER BY MAX(m.timestamp) DESC
            """
            cursor.execute(query)
            latest_user = cursor.fetchone()

            if latest_user is None:
                return jsonify({"error": "No chats found"}), 404
            
            latest_phone_number = latest_user.phone_number

            # Fetch the entire chat history for this phone number
            chat_query = """
                SELECT user_input, bot_response, timestamp
                FROM tbWhatsapp_Messages
                WHERE phone_number = ?
                ORDER BY timestamp ASC
            """
            cursor.execute(chat_query, latest_phone_number)
            chat_history = cursor.fetchall()

            if not chat_history:
                return jsonify({"error": "No chat history found for this user"}), 404

            # Format the chat history by date and time
            chats_by_date = {}
            for chat in chat_history:
                timestamp = chat.timestamp
                date = timestamp.strftime("%d-%m-%Y")  # Group by date (e.g., "09-09-2024")
                time = timestamp.strftime("%I:%M %p")  # Time format (e.g., "9:15 AM")

                message = {
                    "time": time,
                    "bot_response": chat.bot_response
                }

                if chat.user_input:
                    message["user_input"] = chat.user_input

                if date not in chats_by_date:
                    chats_by_date[date] = []

                chats_by_date[date].append(message)

            return jsonify({
                "phone_number": latest_phone_number,
                "chat_history": chats_by_date
            }), 200
    except pyodbc.Error as e:
        logging.error(f"Failed to retrieve chat history: {e}")
        return jsonify({"error": "Failed to retrieve data"}), 500


@app.route("/api/search_contact", methods=["GET"])
def search_clients():
    try:
        # Get the search query from the URL parameters
        search_query = request.args.get("query", "")

        if not search_query:
            return jsonify({"error": "Search query is required"}), 400

        with pyodbc.connect(db_connection_string) as conn:
            cursor = conn.cursor()
            
            # SQL query to search for clients by name or phone number
            query = """
                SELECT u.phone_number, 
                       ISNULL(u.name, u.phone_number) AS display_name,
                       MAX(m.timestamp) AS last_conversation_date,
                       (SELECT TOP 1 bot_response
                        FROM tbWhatsapp_Messages
                        WHERE tbWhatsapp_Messages.phone_number = u.phone_number
                        AND tbWhatsapp_Messages.bot_response IS NOT NULL
                        ORDER BY timestamp DESC) AS last_bot_response
                FROM tbClients u
                LEFT JOIN tbWhatsapp_Messages m ON u.phone_number = m.phone_number
                WHERE u.name LIKE ? OR u.phone_number LIKE ?
                GROUP BY u.phone_number, u.name
            """
            cursor.execute(query, f"%{search_query}%", f"%{search_query}%")
            users = cursor.fetchall()

            phone_numbers_json = []
            last_conversation_dates = {}

            for user in users:
                # Format the last conversation date to 'dd-mm' (exclude the year)
                last_conversation_date = user.last_conversation_date.strftime("%d-%m") if user.last_conversation_date else None
                
                # Store the details in the desired format
                last_conversation_dates[user.phone_number] = last_conversation_date
                
                user_info = {
                    "phone_number": user.phone_number,
                    "last_bot_response": user.last_bot_response
                }
                
                # Include name only if it's not null
                if user.display_name != user.phone_number:
                    user_info["name"] = user.display_name
                
                phone_numbers_json.append(user_info)

            # Sort the results by the last conversation date (latest first)
            sorted_phone_numbers_json = sorted(phone_numbers_json, key=lambda x: last_conversation_dates[x['phone_number']], reverse=True)

        return jsonify({
            "lastConversationDates": dict(sorted(last_conversation_dates.items(), key=lambda item: item[1], reverse=True)),
            "phoneNumbersJson": sorted_phone_numbers_json,
            "totalPhoneNumbers": len(phone_numbers_json)
        }), 200
    except pyodbc.Error as e:
        logging.error(f"Failed to search clients: {e}")
        return jsonify({"error": "Failed to retrieve data"}), 500


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
    logging.info(f"Webhook 1 received request: {body}")

    business_phone_number_id = body.get("entry", [{}])[0].get("changes", [{}])[0].get("value", {}).get("metadata", {}).get("phone_number_id")

    # Check if the phone_number_id matches the specific one (replace 'your_phone_number_id_1' with the actual ID)
    if business_phone_number_id == PHONE_NUMBER_ID_1:
        if (body.get("entry", [{}])[0]
            .get("changes", [{}])[0]
            .get("value", {})
            .get("statuses")):
            logging.info("Webhook 1: Received a WhatsApp status update.")
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
    else:
        # Log and ignore the event if the phone_number_id does not match
        logging.info("Webhook 1: Ignored event due to unmatched phone_number_id.")
        return jsonify({"status": "ignored"}), 200


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
