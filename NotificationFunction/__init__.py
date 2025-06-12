import azure.functions as func
import logging
import json
import os
import urllib.request

# Add this line at the start of the file
logging.getLogger().setLevel(logging.DEBUG)

def send_discord_notification(message: str):
    url = os.environ.get("DiscordWebhookUrl")
    if not url:
        logging.error("Discord webhook URL not set")
        return

    payload = {
        "content": message,
        "username": "PDF Analysis Bot"
    }

    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0"
    }

    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode('utf-8'),
            headers=headers,
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            logging.info(f" Discord notification sent, status: {response.status}")
    except urllib.error.HTTPError as e:
        logging.error(f" Discord HTTP Error: {e.code} - {e.reason}")
        try:
            logging.error(f"Response body: {e.read().decode()}")
        except:
            pass
    except Exception as e:
        logging.error(f" Failed to send Discord notification: {e}")

def send_slack_notification(message: str):
    url = os.environ.get("SlackWebhookUrl")
    if not url:
        logging.error("Slack webhook URL not set")
        return False
        
    try:
        payload = {"text": message}
        
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode('utf-8'),
            headers={
                'Content-Type': 'application/json',
                'User-Agent': 'Azure-Function/1.0'
            }
        )
        
        with urllib.request.urlopen(req, timeout=10) as response:
            response_body = response.read().decode('utf-8')
            logging.info(f"Slack response status: {response.status}")
            logging.info(f"Slack response body: {response_body}")
            
            if response.status == 200:
                logging.info("Slack notification sent successfully")
                return True
            else:
                logging.warning(f"Unexpected Slack response status: {response.status}")
                return False
                
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8') if e.fp else "No error details"
        logging.error(f"Slack HTTP Error {e.code}: {e.reason}")
        logging.error(f"Slack error details: {error_body}")
        return False
    except Exception as e:
        logging.error(f"Failed to send Slack notification: {e}")
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
        notification_message = f"""📄 PDF OCR Processing Complete

**File:** {original_file}
**Text extracted:** {text_length} characters
**Pages:** {page_count}
**Result saved as:** {blob_name}
**Processing time:** {timestamp}

✅ JSON file has been uploaded to Azure Blob Storage."""
        
        # Send notifications with enhanced error handling
        logging.info('Sending notifications...')
        
        discord_result = send_discord_notification(notification_message)
        slack_result = send_slack_notification(notification_message)
        
        if discord_result and slack_result:
            logging.info('✅ All notifications sent successfully')
        elif discord_result or slack_result:
            logging.warning('⚠️ Some notifications sent successfully')
        else:
            logging.error('❌ All notifications failed to send')
            
    except Exception as e:
        logging.error(f'Error in notification function: {str(e)}', exc_info=True)