import azure.functions as func
import logging
import json
import os
import urllib.request

def send_discord_notification(message: str):
    """Send notification to Discord webhook"""
    url = os.environ.get("DiscordWebhookUrl")
    if url:
        try:
            data = json.dumps({"content": message}).encode('utf-8')
            req = urllib.request.Request(url, data, {'Content-Type': 'application/json'})
            urllib.request.urlopen(req, timeout=10)
            logging.info("Discord notification sent successfully")
        except Exception as e:
            logging.warning(f"Discord notification failed: {e}")
    else:
        logging.info("Discord webhook URL not configured")

def send_slack_notification(message: str):
    """Send notification to Slack webhook"""
    url = os.environ.get("SlackWebhookUrl")
    if url:
        try:
            data = json.dumps({"text": message}).encode('utf-8')
            req = urllib.request.Request(url, data, {'Content-Type': 'application/json'})
            urllib.request.urlopen(req, timeout=10)
            logging.info("Slack notification sent successfully")
        except Exception as e:
            logging.warning(f"Slack notification failed: {e}")
    else:
        logging.info("Slack webhook URL not configured")

def main(myblob: func.InputStream) -> None:
    """
    Blob Trigger Function for push notifications
    Automatically triggers when JSON file is dropped into Azure Blob Storage
    Implements: "create push notifications when the result JSON file is dropped into the Azure Blob Storage"
    """
    try:
        logging.info(f'🔔 Blob trigger activated for: {myblob.name}')
        logging.info(f'Blob size: {myblob.length} bytes')
        
        # Extract blob name from full path (e.g., mycontainer/filename.json -> filename.json)
        blob_name = myblob.name.split('/')[-1] if '/' in myblob.name else myblob.name
        
        # Only process JSON files (our OCR results)
        if not blob_name.endswith('.json'):
            logging.info(f'Skipping non-JSON file: {blob_name}')
            return
        
        # Read and parse the JSON content
        try:
            blob_content = myblob.read().decode('utf-8')
            json_data = json.loads(blob_content)
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            logging.error(f'Error parsing JSON from blob {blob_name}: {e}')
            return
        
        # Extract information from the OCR result JSON
        original_file = json_data.get('file_name', 'Unknown')
        text_content = json_data.get('text', '')
        text_length = len(text_content)
        page_count = json_data.get('page_count', 0)
        timestamp = json_data.get('timestamp', 'Unknown')
        
        # Create notification message (English, no emojis)
        notification_message = f"""PDF OCR Processing Complete

File: {original_file}
Text extracted: {text_length} characters
Pages: {page_count}
Result saved as: {blob_name}
Processing time: {timestamp}

JSON file has been uploaded to Azure Blob Storage."""
        
        # Send notifications
        logging.info('Sending push notifications triggered by blob upload...')
        send_discord_notification(notification_message)
        send_slack_notification(notification_message)
        
        logging.info(f'✅ Push notifications sent for blob: {blob_name}')
        
    except Exception as e:
        logging.error(f'Error in notification function: {str(e)}', exc_info=True) 