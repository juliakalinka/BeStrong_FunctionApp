import azure.functions as func
import logging
import json
import os
import urllib.request

# Add this line at the start of the file
logging.getLogger().setLevel(logging.DEBUG)

def send_discord_notification(message: str, environment: str):
    url = os.environ.get("DiscordWebhookUrl")
    if not url:
        logging.error(f"Discord webhook URL not set for {environment} environment")
        return False

    # Add environment indicator to the message
    env_indicator = "PRODUCTION" if environment == "prod" else "DEVELOPMENT"
    enhanced_message = f"{env_indicator}\n{message}"

    payload = {
        "content": enhanced_message,
        "username": f"PDF Analysis Bot ({environment.upper()})",
        "avatar_url": "https://cdn.jsdelivr.net/gh/twitter/twemoji@latest/assets/72x72/1f4c4.png"
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
            logging.info(f"Discord notification sent to {environment}, status: {response.status}")
            return True
    except urllib.error.HTTPError as e:
        logging.error(f"Discord HTTP Error for {environment}: {e.code} - {e.reason}")
        try:
            logging.error(f"Response body: {e.read().decode()}")
        except:
            pass
        return False
    except Exception as e:
        logging.error(f"Failed to send Discord notification to {environment}: {e}")
        return False

def send_slack_notification(message: str, environment: str):
    url = os.environ.get("SlackWebhookUrl")
    if not url:
        logging.error(f"Slack webhook URL not set for {environment} environment")
        return False
        
    try:
        # Add environment indicator to the message
        env_indicator = ":large_green_circle: PRODUCTION" if environment == "prod" else ":large_yellow_circle: DEVELOPMENT"
        enhanced_message = f"{env_indicator}\n{message}"
        
        payload = {
            "text": enhanced_message,
            "channel": "#all-bestrong"
        }
        
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode('utf-8'),
            headers={
                'Content-Type': 'application/json',
                'User-Agent': f'Azure-Function-{environment}/1.0'
            }
        )
        
        with urllib.request.urlopen(req, timeout=10) as response:
            response_body = response.read().decode('utf-8')
            logging.info(f"Slack response status for {environment}: {response.status}")
            logging.info(f"Slack response body: {response_body}")
            
            if response.status == 200:
                logging.info(f"Slack notification sent successfully to {environment}")
                return True
            else:
                logging.warning(f"Unexpected Slack response status for {environment}: {response.status}")
                return False
                
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8') if e.fp else "No error details"
        logging.error(f"Slack HTTP Error for {environment} {e.code}: {e.reason}")
        logging.error(f"Slack error details: {error_body}")
        return False
    except Exception as e:
        logging.error(f"Failed to send Slack notification to {environment}: {e}")
        return False

def main(myblob: func.InputStream) -> None:
    """
    Blob Trigger Function for push notifications
    Automatically triggers when JSON file is dropped into Azure Blob Storage
    Implements: "create push notifications when the result JSON file is dropped into the Azure Blob Storage"
    """
    try:
        # Get environment information
        environment = os.environ.get("ENVIRONMENT", "dev")  # Default to dev if not set
        
        logging.info(f'Blob trigger activated in {environment} environment')
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
        processed_environment = json_data.get('environment', environment)  # Use environment from JSON if available
        processed_by = json_data.get('processed_by', f'{environment}-function')
        
        logging.info(f'Extracted metadata - File: {original_file}, Pages: {page_count}, Text length: {text_length}, Environment: {processed_environment}')
        
        # Create notification message with environment information
        env_display = processed_environment.upper()
        notification_message = f"""PDF OCR Processing Complete

**Environment:** {env_display}
**File:** {original_file}
**Text extracted:** {text_length} characters
**Pages:** {page_count}
**Result saved as:** {blob_name}
**Processing time:** {timestamp}
**Processed by:** {processed_by}

✅ JSON file has been uploaded to Azure Blob Storage in {env_display} environment."""
        
        # Send notifications with enhanced error handling
        logging.info(f'Sending notifications for {processed_environment} environment...')
        
        discord_result = send_discord_notification(notification_message, processed_environment)
        slack_result = send_slack_notification(notification_message, processed_environment)
        
        if discord_result and slack_result:
            logging.info(f'All notifications sent successfully for {processed_environment}')
        elif discord_result or slack_result:
            logging.warning(f'Some notifications sent successfully for {processed_environment}')
        else:
            logging.error(f'All notifications failed to send for {processed_environment}')
            
    except Exception as e:
        logging.error(f'Error in notification function: {str(e)}', exc_info=True)