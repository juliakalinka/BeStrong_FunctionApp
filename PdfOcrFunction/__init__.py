import azure.functions as func
import logging
import os
import json
from datetime import datetime

# Working version - using urllib and built-in modules for REST API
import tempfile
import urllib.request
import urllib.parse
import base64
import hashlib
import hmac
import time

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
        logging.info('Processing PDF using REST API approach')
        
        # Parse connection strings
        file_share_conn = os.environ["FileShareConnectionString"]
        blob_conn = os.environ["BlobStorageConnectionString"] 
        form_recognizer_endpoint = os.environ["FormRecognizerEndpoint"]
        form_recognizer_key = os.environ["FormRecognizerKey"]
        
        # Extract storage account info from connection string
        storage_account_name = file_share_conn.split('AccountName=')[1].split(';')[0]
        storage_account_key = file_share_conn.split('AccountKey=')[1].split(';')[0]
        
        # Step 1: Download PDF from File Share using REST API
        # URL encode the file name to handle spaces and special characters
        encoded_file_name = urllib.parse.quote(file_name)
        file_share_url = f"https://{storage_account_name}.file.core.windows.net/myshare/{encoded_file_name}"
        
        # Create authorization header for File Share
        from datetime import timezone
        
        utc_now = datetime.now(timezone.utc).strftime('%a, %d %b %Y %H:%M:%S GMT')
        string_to_sign = f"GET\n\n\n\n\n\n\n\n\n\n\n\nx-ms-date:{utc_now}\nx-ms-version:2020-12-06\n/{storage_account_name}/myshare/{encoded_file_name}"
        
        key = base64.b64decode(storage_account_key)
        signature = base64.b64encode(hmac.new(key, string_to_sign.encode('utf-8'), hashlib.sha256).digest()).decode()
        
        headers = {
            'x-ms-date': utc_now,
            'x-ms-version': '2020-12-06',
            'Authorization': f'SharedKey {storage_account_name}:{signature}'
        }
        
        # Download file
        req = urllib.request.Request(file_share_url, headers=headers)
        with urllib.request.urlopen(req) as response:
            pdf_data = response.read()
        
        logging.info(f'Downloaded PDF file: {len(pdf_data)} bytes')
        
        # Step 2: Send to Form Recognizer using REST API
        fr_url = f"{form_recognizer_endpoint.rstrip('/')}/formrecognizer/documentModels/prebuilt-document:analyze?api-version=2023-07-31"
        
        fr_headers = {
            'Ocp-Apim-Subscription-Key': form_recognizer_key,
            'Content-Type': 'application/pdf'
        }
        
        fr_request = urllib.request.Request(fr_url, data=pdf_data, headers=fr_headers, method='POST')
        
        with urllib.request.urlopen(fr_request) as fr_response:
            operation_location = fr_response.headers.get('Operation-Location')
        
        logging.info(f'Form Recognizer operation started: {operation_location}')
        
        # Poll for results
        result_headers = {'Ocp-Apim-Subscription-Key': form_recognizer_key}
        
        for attempt in range(30):  # Wait up to 30 seconds
            time.sleep(1)
            result_req = urllib.request.Request(operation_location, headers=result_headers)
            
            with urllib.request.urlopen(result_req) as result_response:
                result_data = json.loads(result_response.read().decode())
                
                if result_data.get('status') == 'succeeded':
                    extracted_text = result_data.get('analyzeResult', {}).get('content', '')
                    page_count = len(result_data.get('analyzeResult', {}).get('pages', []))
                    break
                elif result_data.get('status') == 'failed':
                    raise Exception(f"Form Recognizer failed: {result_data}")
        else:
            raise Exception("Form Recognizer timeout")
        
        logging.info(f'Text extracted successfully: {len(extracted_text)} characters')
        
        # Step 3: Create JSON result
        json_result = {
            "file_name": file_name,
            "timestamp": datetime.utcnow().isoformat(),
            "text": extracted_text,
            "page_count": page_count
        }
        
        # Step 4: Upload to Blob Storage using REST API
        blob_name = f"{os.path.splitext(file_name)[0]}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
        encoded_blob_name = urllib.parse.quote(blob_name)
        blob_url = f"https://{storage_account_name}.blob.core.windows.net/mycontainer/{encoded_blob_name}"
        
        json_data = json.dumps(json_result).encode('utf-8')
        
        # Create authorization for Blob Storage
        utc_now = datetime.now(timezone.utc).strftime('%a, %d %b %Y %H:%M:%S GMT')
        content_length = str(len(json_data))
        
        blob_string_to_sign = f"PUT\n\n\napplication/json\n\n\n\n\n\n\n\n\nx-ms-blob-type:BlockBlob\nx-ms-date:{utc_now}\nx-ms-version:2020-12-06\n/{storage_account_name}/mycontainer/{encoded_blob_name}"
        
        blob_signature = base64.b64encode(hmac.new(key, blob_string_to_sign.encode('utf-8'), hashlib.sha256).digest()).decode()
        
        blob_headers = {
            'x-ms-date': utc_now,
            'x-ms-version': '2020-12-06',
            'x-ms-blob-type': 'BlockBlob',
            'Content-Type': 'application/json',
            'Content-Length': content_length,
            'Authorization': f'SharedKey {storage_account_name}:{blob_signature}'
        }
        
        blob_request = urllib.request.Request(blob_url, data=json_data, headers=blob_headers, method='PUT')
        urllib.request.urlopen(blob_request)
        
        logging.info(f'JSON uploaded to blob: {blob_name}')
        
        # Step 5: Send notifications
        msg = f"✅ PDF processed via REST API: `{file_name}`\nSaved to blob: `{blob_name}`"
        send_discord_notification(msg)
        send_slack_notification(msg)
        
        return func.HttpResponse(json.dumps({
            "status": "success",
            "message": "PDF processed successfully using REST API",
            "blob_name": blob_name,
            "text_length": len(extracted_text),
            "page_count": page_count
        }), mimetype="application/json")

    except Exception as e:
        logging.error(f'Error in basic test: {str(e)}', exc_info=True)
        return func.HttpResponse(f"Basic test error: {str(e)}", status_code=500)