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

def main(myblob: func.InputStream) -> None:
    """
    Azure Function with Blob Trigger
    Automatically triggers when a JSON file is uploaded to the blob container
    """
    try:
        logging.info(f'🔔 Blob trigger function processed blob: {myblob.name}')
        logging.info(f'Blob length: {myblob.length} bytes')
        
        # Extract blob name from full path (e.g., mycontainer/filename.json -> filename.json)
        blob_name = myblob.name.split('/')[-1] if '/' in myblob.name else myblob.name
        
        # Check if this is a JSON file (our OCR results)
        if not blob_name.endswith('.json'):
            logging.info(f'Skipping non-JSON file: {blob_name}')
            return
        
        # Read the JSON content
        blob_content = myblob.read().decode('utf-8')
        json_data = json.loads(blob_content)
        
        # Extract information from the JSON
        original_file = json_data.get('file_name', 'Unknown')
        text_length = len(json_data.get('text', ''))
        page_count = json_data.get('page_count', 0)
        timestamp = json_data.get('timestamp', 'Unknown')
        
        # Create notification message
        message = f"""🔔 **PDF OCR Результат готовий!**
        
📄 **Файл:** `{original_file}`
📝 **Текст:** {text_length} символів
📖 **Сторінок:** {page_count}
💾 **Збережено як:** `{blob_name}`
⏰ **Час обробки:** {timestamp}

✅ Результати доступні в Azure Blob Storage!"""
        
        # Send notifications
        logging.info('Sending notifications...')
        send_discord_notification(message)
        send_slack_notification(message)
        
        logging.info(f'✅ Notifications sent for blob: {blob_name}')
        
    except Exception as e:
        logging.error(f'Error in notification function: {str(e)}', exc_info=True) 