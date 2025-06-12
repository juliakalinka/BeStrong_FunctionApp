import logging
import azure.functions as func
import json
import os
import urllib.request

def send_webhook_message(url, message):
    data = json.dumps({"content": message}).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req) as response:
        return response.read().decode()

def main(blob: func.InputStream):
    logging.info(f"NotificationFunction triggered by blob: {blob.name}")

    try:
        blob_content = blob.read().decode('utf-8')
        parsed_json = json.loads(blob_content)

        file_name = parsed_json.get("file_name", "Unknown file")
        page_count = parsed_json.get("page_count", "N/A")
        text_length = len(parsed_json.get("text", ""))

        message = f"📄 New document processed:\n- File: `{file_name}`\n- Pages: `{page_count}`\n- Extracted text length: `{text_length}`"

        # Send to Discord
        discord_url = os.environ.get("DiscordWebhookUrl")
        if discord_url:
            send_webhook_message(discord_url, message)
            logging.info("Notification sent to Discord.")

        # Send to Slack
        slack_url = os.environ.get("SlackWebhookUrl")
        if slack_url:
            slack_data = json.dumps({"text": message}).encode("utf-8")
            req = urllib.request.Request(slack_url, data=slack_data, headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(req) as response:
                logging.info("Notification sent to Slack.")

    except Exception as e:
        logging.error(f"Failed to send notifications: {e}")
