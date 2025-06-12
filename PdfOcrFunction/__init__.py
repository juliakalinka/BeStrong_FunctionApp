import azure.functions as func
import logging
import os
import json
from datetime import datetime

# Working version - using urllib instead of requests
import tempfile
import urllib.request
import urllib.parse

# Adding Azure packages one by one
from azure.core.credentials import AzureKeyCredential
from azure.storage.blob import BlobServiceClient
from azure.storage.fileshare import ShareServiceClient
from azure.ai.formrecognizer import DocumentAnalysisClient

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
        # ENV variables
        file_conn = os.environ["FileShareConnectionString"]
        blob_conn = os.environ["BlobStorageConnectionString"]
        endpoint = os.environ["FormRecognizerEndpoint"]
        key = os.environ["FormRecognizerKey"]

        # Get file from File Share
        file_client = ShareServiceClient.from_connection_string(file_conn) \
            .get_share_client("myshare") \
            .get_file_client(file_name)

        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
            file_client.download_file().readinto(tmp_file)
            temp_path = tmp_file.name

        # Analyze PDF
        form_client = DocumentAnalysisClient(endpoint, AzureKeyCredential(key))
        with open(temp_path, "rb") as f:
            poller = form_client.begin_analyze_document("prebuilt-document", f)
            result = poller.result()
        os.unlink(temp_path)

        json_result = {
            "file_name": file_name,
            "timestamp": datetime.utcnow().isoformat(),
            "text": result.content,
            "page_count": len(result.pages)
        }

        # Upload to Blob Storage
        blob_client = BlobServiceClient.from_connection_string(blob_conn)
        container = blob_client.get_container_client("mycontainer")
        try:
            container.create_container()
        except:
            pass

        blob_name = f"{os.path.splitext(file_name)[0]}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
        container.upload_blob(blob_name, json.dumps(json_result), overwrite=True)

        # Notifications with urllib instead of requests
        msg = f"✅ PDF processed: `{file_name}`\nSaved to blob: `{blob_name}`"
        send_discord_notification(msg)
        send_slack_notification(msg)

        return func.HttpResponse(json.dumps({
            "status": "ok",
            "blob": blob_name
        }), mimetype="application/json")

    except Exception as e:
        logging.error(str(e), exc_info=True)
        send_discord_notification(f"❌ Error processing `{file_name}`: {str(e)}")
        send_slack_notification(f"❌ Error processing `{file_name}`: {str(e)}")
        return func.HttpResponse("Internal error", status_code=500)