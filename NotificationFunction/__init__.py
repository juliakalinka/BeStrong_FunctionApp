import azure.functions as func
import logging
import json
import os
import urllib.request

# Add this line at the start of the file
logging.getLogger().setLevel(logging.DEBUG)

def send_discord_notification(message: str) -> bool:
    """Send notification to Discord webhook"""
    url = os.environ.get("DiscordWebhookUrl")
    if not url:
        logging.error("Discord webhook URL not configured")
        return False
        
    try:
        data = json.dumps({"content": message}).encode('utf-8')
        req = urllib.request.Request(url, data, {'Content-Type': 'application/json'})
        response = urllib.request.urlopen(req, timeout=10)
        
        if response.status == 204:  # Discord returns 204 No Content on success
            logging.info("Discord notification sent successfully")
            return True
        else:
            logging.warning(f"Discord notification returned unexpected status: {response.status}")
            return False
            
    except Exception as e:
        logging.error(f"Discord notification failed: {str(e)}", exc_info=True)
        return False

def send_slack_notification(message: str) -> bool:
    """Send notification to Slack webhook"""
    url = os.environ.get("SlackWebhookUrl")
    if not url:
        logging.error("Slack webhook URL not configured")
        return False
        
    try:
        data = json.dumps({"text": message}).encode('utf-8')
        req = urllib.request.Request(url, data, {'Content-Type': 'application/json'})
        response = urllib.request.urlopen(req, timeout=10)
        
        if response.status == 200:  # Slack returns 200 OK on success
            logging.info("Slack notification sent successfully")
            return True
        else:
            logging.warning(f"Slack notification returned unexpected status: {response.status}")
            return False
            
    except Exception as e:
        logging.error(f"Slack notification failed: {str(e)}", exc_info=True)
        return False

def main(myblob: func.InputStream) -> None:
    """
    Blob Trigger Function for push notifications
    Automatically triggers when JSON file is dropped into Azure Blob Storage
    Implements: "create push notifications when the result JSON file is dropped into the Azure Blob Storage"
    """
    try:
        logging.info(f'🔔 Blob trigger activated')
        logging.info(f'Blob name: {myblob.name}')
        logging.info(f'Blob URI: {myblob.uri if hasattr(myblob, "uri") else "Not available"}')
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
            logging.info(f'Successfully read blob content')
            json_data = json.loads(blob_content)
            logging.info(f'Successfully parsed JSON content')
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            logging.error(f'Error parsing JSON from blob {blob_name}: {e}')
            return
        
        # Extract information from the OCR result JSON
        original_file = json_data.get('file_name', 'Unknown')
        text_content = json_data.get('text', '')
        text_length = len(text_content)
        page_count = json_data.get('page_count', 0)
        timestamp = json_data.get('timestamp', 'Unknown')
        
        logging.info(f'Extracted metadata - File: {original_file}, Pages: {page_count}, Text length: {text_length}')
        
        # Create notification message
        notification_message = f"""PDF OCR Processing Complete

File: {original_file}
Text extracted: {text_length} characters
Pages: {page_count}
Result saved as: {blob_name}
Processing time: {timestamp}

JSON file has been uploaded to Azure Blob Storage."""
        
        # Send notifications with enhanced error handling
        logging.info('Sending notifications...')
        
        discord_result = send_discord_notification(notification_message)
        slack_result = send_slack_notification(notification_message)
        
        if discord_result and slack_result:
            logging.info('✅ All notifications sent successfully')
        else:
            logging.warning('⚠️ Some notifications failed to send')
            
    except Exception as e:
        logging.error(f'Error in notification function: {str(e)}', exc_info=True) 