
import paho.mqtt.client as mqtt
from datetime import datetime
import os
import requests
import time
import json
import logging
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Load environment variables
load_dotenv()

# MQTT Broker settings
BROKER = "broker.hivemq.com"
PORT = 1883
BASE_TOPIC = os.getenv("BASE_TOPIC", "your_unique_topic/ece140/sensors")
if BASE_TOPIC == "your_unique_topic/ece140/sensors":
    logging.error("Please enter a unique topic for your server in the .env file")
    exit()

# Full topic for subscription
TOPIC = "default_topic/ece140/sensors/default_topic/ece140/sensors/reading"

# Web server URL
WEB_SERVER_URL = os.getenv("WEB_SERVER_URL", "http://localhost:6543/api/temperature")
if "localhost" in WEB_SERVER_URL:
    logging.warning("Using localhost for the web server. Update this in production.")

# Track the last time a POST request was sent
last_post_time = 0
post_interval = 5  # Minimum interval between POST requests (in seconds)

# MQTT Callback: When a message is received
def on_message(client, userdata, msg):
    global last_post_time
    try:
        # Decode the message payload
        payload = msg.payload.decode()
        logging.info(f"Received message: {payload}")

        # Parse the JSON payload
        try:
            data = json.loads(payload)
        except json.JSONDecodeError as e:
            logging.error(f"Failed to parse payload as JSON: {e}")
            return

        # Extract temperature
        temperature = data.get("temperature")
        if temperature is None:
            logging.error(f"Error: 'temperature' key not found in payload: {payload}")
            return

        # Generate timestamp
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Check if enough time has passed since the last POST request
        current_time = time.time()
        if current_time - last_post_time >= post_interval:
            # Prepare the POST request body
            post_data = {
                "value": temperature,
                "unit": "C",
                "timestamp": timestamp
            }

            # Send the POST request to the web server
            try:
                response = requests.post(WEB_SERVER_URL, json=post_data, timeout=5)
                if response.status_code == 200:
                    logging.info("POST request successful!")
                else:
                    logging.error(f"POST request failed with status code {response.status_code}")
            except requests.exceptions.RequestException as e:
                logging.error(f"HTTP request failed: {e}")

            # Update the last POST time
            last_post_time = current_time
    except Exception as e:
        logging.error(f"Error processing message: {e}")

# MQTT Callback: When connected to the broker
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        logging.info("Connected to MQTT broker successfully!")
        # Subscribe to the topic
        client.subscribe(TOPIC)
        logging.info(f"Subscribed to topic: {TOPIC}")
    else:
        logging.error(f"Failed to connect to MQTT broker with result code {rc}")

def main():
    # Create MQTT client
    logging.info("Creating MQTT client...")
    client = mqtt.Client()

    # Set the callback functions
    client.on_connect = on_connect
    client.on_message = on_message

    try:
        # Connect to broker
        logging.info("Connecting to broker...")
        client.connect(BROKER, PORT, 60)

        # Start the MQTT loop
        logging.info("Starting MQTT loop...")
        client.loop_forever()
    except KeyboardInterrupt:
        logging.info("\nDisconnecting from broker...")
    except Exception as e:
        logging.error(f"Error: {e}")
    finally:
        client.disconnect()
        logging.info("Disconnected from broker.")

if __name__ == "__main__":
    main()