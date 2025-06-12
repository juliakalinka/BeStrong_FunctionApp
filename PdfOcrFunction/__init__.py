import azure.functions as func
import logging
import os
import json
from datetime import datetime

# Working version - using urllib instead of requests
import tempfile
import urllib.request
import urllib.parse

# Alternative approach: Using REST API instead of Azure SDK
# from azure.core.credentials import AzureKeyCredential
# from azure.storage.blob import BlobServiceClient
# from azure.storage.fileshare import ShareServiceClient
# from azure.ai.formrecognizer import DocumentAnalysisClient

def send_discord_notification(message: str):
    url = os.environ.get("DiscordWebhookUrl")
    if url:
        try:
            data = json.dumps({"content": message}).encode('utf-8')
            req = urllib.request.Request(url, data, {'Content-Type': 'application/json'})
            urllib.request.urlopen(req, timeout=10)
        except Exception as e:
            logging.warning(f"Discord notification failed: {e}")

def send_slack_notification(message: str):
    url = os.environ.get("SlackWebhookUrl")
    if url:
        try:
            data = json.dumps({"text": message}).encode('utf-8')
            req = urllib.request.Request(url, data, {'Content-Type': 'application/json'})
            urllib.request.urlopen(req, timeout=10)
        except Exception as e:
            logging.warning(f"Slack notification failed: {e}")

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
        logging.info('Alternative approach: REST API instead of Azure SDK')
        
        # Get environment variables for REST API calls
        form_recognizer_endpoint = os.environ.get("FormRecognizerEndpoint", "")
        form_recognizer_key = os.environ.get("FormRecognizerKey", "")
        file_share_conn = os.environ.get("FileShareConnectionString", "")
        blob_conn = os.environ.get("BlobStorageConnectionString", "")
        
        test_result = {
            "status": "rest_api_approach",
            "file_name": file_name,
            "timestamp": datetime.utcnow().isoformat(),
            "message": "Using REST API instead of Azure SDK to avoid conflicts",
            "form_recognizer_available": bool(form_recognizer_endpoint and form_recognizer_key),
            "storage_available": bool(file_share_conn and blob_conn)
        }
        
        logging.info('Basic test completed successfully')
        return func.HttpResponse(json.dumps(test_result), mimetype="application/json")

    except Exception as e:
        logging.error(f'Error in basic test: {str(e)}', exc_info=True)
        return func.HttpResponse(f"Basic test error: {str(e)}", status_code=500)