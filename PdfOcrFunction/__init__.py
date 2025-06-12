import azure.functions as func
import logging
import os
import json
from datetime import datetime

# Testing tempfile only
import tempfile  
# import requests  # Commented for testing

# Still commented - will add one by one
# from azure.storage.blob import BlobServiceClient
# from azure.storage.fileshare import ShareServiceClient
# from azure.ai.formrecognizer import DocumentAnalysisClient
# from azure.core.credentials import AzureKeyCredential

# Temporarily disabled for testing
# def send_discord_notification(message: str):
#     url = os.environ.get("DiscordWebhookUrl")
#     if url:
#         try:
#             requests.post(url, json={"content": message}, timeout=10)
#         except Exception as e:
#             logging.warning(f"Discord notification failed: {e}")

# def send_slack_notification(message: str):
#     url = os.environ.get("SlackWebhookUrl")
#     if url:
#         try:
#             requests.post(url, json={"text": message}, timeout=10)
#         except Exception as e:
#             logging.warning(f"Slack notification failed: {e}")

def main(req: func.HttpRequest) -> func.HttpResponse:
    try:
        logging.info('Function triggered - START')
        
        file_name = req.params.get('file_name')
        logging.info(f'File name parameter: {file_name}')
        
        if not file_name:
            logging.info('No file_name parameter - returning 400')
            return func.HttpResponse("Missing 'file_name' parameter", status_code=400)
    except Exception as e:
        logging.error(f'Error in initial setup: {str(e)}', exc_info=True)
        return func.HttpResponse(f"Initialization error: {str(e)}", status_code=500)

    try:
        logging.info('Starting basic test mode')
        
        # Basic environment variable check
        env_vars = {
            'FileShareConnectionString': os.environ.get("FileShareConnectionString", "NOT_SET"),
            'FormRecognizerEndpoint': os.environ.get("FormRecognizerEndpoint", "NOT_SET"),
            'BUILD_ID': os.environ.get("BUILD_ID", "NOT_SET")
        }
        
        logging.info(f'Environment variables: {env_vars}')
        
        # Simple response for testing
        test_result = {
            "status": "test_mode",
            "file_name": file_name,
            "timestamp": datetime.utcnow().isoformat(),
            "environment_check": env_vars,
            "message": "Basic function test successful!"
        }
        
        logging.info('Test mode completed successfully')
        return func.HttpResponse(json.dumps(test_result), mimetype="application/json")

    except Exception as e:
        logging.error(f'Error in test mode: {str(e)}', exc_info=True)
        return func.HttpResponse(f"Test mode error: {str(e)}", status_code=500)