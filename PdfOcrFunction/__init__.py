
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

def main(req: func.HttpRequest) -> func.HttpResponse:
    try:
        logging.info('Function triggered - START')
        
        # Get environment information
        environment = os.environ.get("ENVIRONMENT", "dev")  # Default to dev if not set
        logging.info(f'Running in environment: {environment}')
        
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
        
        # Get environment variables with environment suffix
        file_share_conn = os.environ.get(f"FileShareConnectionString{environment}")
        blob_conn = os.environ.get(f"BlobStorageConnectionString{environment}")
        form_recognizer_endpoint = os.environ.get(f"FormRecognizerEndpoint{environment}")
        form_recognizer_key = os.environ.get(f"FormRecognizerKey{environment}")
        
        # Validate that all required environment variables are present
        missing_vars = []
        if not file_share_conn:
            missing_vars.append(f"FileShareConnectionString{environment}")
        if not blob_conn:
            missing_vars.append(f"BlobStorageConnectionString{environment}")
        if not form_recognizer_endpoint:
            missing_vars.append(f"FormRecognizerEndpoint{environment}")
        if not form_recognizer_key:
            missing_vars.append(f"FormRecognizerKey{environment}")
            
        if missing_vars:
            error_msg = f"Missing environment variables: {', '.join(missing_vars)}"
            logging.error(error_msg)
            return func.HttpResponse(error_msg, status_code=500)
        
        # Extract storage account info from connection strings
        # File Share connection
        fs_storage_account_name = file_share_conn.split('AccountName=')[1].split(';')[0]
        fs_storage_account_key = file_share_conn.split('AccountKey=')[1].split(';')[0]
        
        # Blob Storage connection (may be different account)
        blob_storage_account_name = blob_conn.split('AccountName=')[1].split(';')[0]
        blob_storage_account_key = blob_conn.split('AccountKey=')[1].split(';')[0]
        
        logging.info(f'Environment: {environment}')
        logging.info(f'Parsed File Share account: {fs_storage_account_name}')
        logging.info(f'Parsed Blob Storage account: {blob_storage_account_name}')
        logging.info(f'Form Recognizer endpoint: {form_recognizer_endpoint}')
        
        # Step 1: Download PDF from File Share using REST API
        # URL encode the file name to handle spaces and special characters
        encoded_file_name = urllib.parse.quote(file_name)
        file_share_url = f"https://{fs_storage_account_name}.file.core.windows.net/myshare/{encoded_file_name}"
        
        # Create authorization header for File Share
        from datetime import timezone
        
        utc_now = datetime.now(timezone.utc).strftime('%a, %d %b %Y %H:%M:%S GMT')
        
        # Canonical resource for File Share: /{account}/{share}/{file_path}
        fs_canonical_resource = f"/{fs_storage_account_name}/myshare/{encoded_file_name}"
        
        # String to sign format for File Share REST API
        fs_string_to_sign = f"GET\n\n\n\n\n\n\n\n\n\n\n\nx-ms-date:{utc_now}\nx-ms-version:2020-12-06\n{fs_canonical_resource}"
        
        fs_key = base64.b64decode(fs_storage_account_key)
        fs_signature = base64.b64encode(hmac.new(fs_key, fs_string_to_sign.encode('utf-8'), hashlib.sha256).digest()).decode()
        
        # Debug logging
        logging.info(f'FS Account: {fs_storage_account_name}')
        logging.info(f'UTC Date: {utc_now}')
        logging.info(f'File Share URL: {file_share_url}')
        
        headers = {
            'x-ms-date': utc_now,
            'x-ms-version': '2020-12-06',
            'Authorization': f'SharedKey {fs_storage_account_name}:{fs_signature}'
        }
        
        # Download file
        req = urllib.request.Request(file_share_url, headers=headers)
        
        try:
            with urllib.request.urlopen(req) as response:
                pdf_data = response.read()
        except urllib.error.HTTPError as e:
            error_body = e.read().decode() if hasattr(e, 'read') else 'No error body'
            logging.error(f'HTTP Error {e.code}: {e.reason}')
            logging.error(f'Error body: {error_body}')
            raise Exception(f'File Share auth error {e.code}: {e.reason} - {error_body}')
        
        logging.info(f'Downloaded PDF file: {len(pdf_data)} bytes')
        
        # Step 2: Send to Form Recognizer using REST API
        fr_url = f"{form_recognizer_endpoint.rstrip('/')}/formrecognizer/documentModels/prebuilt-document:analyze?api-version=2023-07-31"
        
        # Log Form Recognizer details for debugging
        logging.info(f'Form Recognizer URL: {fr_url}')
        logging.info(f'Form Recognizer Key (first 10 chars): {form_recognizer_key[:10]}...' if form_recognizer_key else 'No key found')
        
        fr_headers = {
            'Ocp-Apim-Subscription-Key': form_recognizer_key,
            'Content-Type': 'application/pdf'
        }
        
        fr_request = urllib.request.Request(fr_url, data=pdf_data, headers=fr_headers, method='POST')
        
        try:
            with urllib.request.urlopen(fr_request) as fr_response:
                operation_location = fr_response.headers.get('Operation-Location')
        except urllib.error.HTTPError as e:
            error_body = e.read().decode() if hasattr(e, 'read') else 'No error body'
            logging.error(f'Form Recognizer HTTP Error {e.code}: {e.reason}')
            logging.error(f'Form Recognizer error body: {error_body}')
            raise Exception(f'Form Recognizer auth error {e.code}: {e.reason} - {error_body}')
        
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
        
        # Step 3: Create JSON result with environment info
        json_result = {
            "file_name": file_name,
            "timestamp": datetime.utcnow().isoformat(),
            "text": extracted_text,
            "page_count": page_count,
            "environment": environment,
            "processed_by": f"{environment}-function"
        }
        
        # Step 4: Upload to Blob Storage using REST API
        blob_name = f"{environment}_{os.path.splitext(file_name)[0]}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
        encoded_blob_name = urllib.parse.quote(blob_name)
        blob_url = f"https://{blob_storage_account_name}.blob.core.windows.net/mycontainer/{encoded_blob_name}"
        
        json_data = json.dumps(json_result).encode('utf-8')
        
        # Create authorization for Blob Storage
        blob_utc_now = datetime.now(timezone.utc).strftime('%a, %d %b %Y %H:%M:%S GMT')
        content_length = str(len(json_data))
        
        # Canonical resource for Blob Storage: /{account}/{container}/{blob}
        blob_canonical_resource = f"/{blob_storage_account_name}/mycontainer/{encoded_blob_name}"
        
        # Correct string_to_sign format for Blob Storage PUT operation
        blob_string_to_sign = f"PUT\n\n\n{content_length}\n\napplication/json\n\n\n\n\n\n\nx-ms-blob-type:BlockBlob\nx-ms-date:{blob_utc_now}\nx-ms-version:2020-12-06\n{blob_canonical_resource}"
        
        blob_key = base64.b64decode(blob_storage_account_key)
        blob_signature = base64.b64encode(hmac.new(blob_key, blob_string_to_sign.encode('utf-8'), hashlib.sha256).digest()).decode()
        
        # Debug logging for Blob Storage
        logging.info(f'Blob Account: {blob_storage_account_name}')
        logging.info(f'Blob URL: {blob_url}')
        logging.info(f'Content Length: {content_length}')
        
        blob_headers = {
            'x-ms-date': blob_utc_now,
            'x-ms-version': '2020-12-06',
            'x-ms-blob-type': 'BlockBlob',
            'Content-Type': 'application/json',
            'Content-Length': content_length,
            'Authorization': f'SharedKey {blob_storage_account_name}:{blob_signature}'
        }
        
        blob_request = urllib.request.Request(blob_url, data=json_data, headers=blob_headers, method='PUT')
        
        try:
            urllib.request.urlopen(blob_request)
        except urllib.error.HTTPError as e:
            error_body = e.read().decode() if hasattr(e, 'read') else 'No error body'
            logging.error(f'Blob Storage HTTP Error {e.code}: {e.reason}')
            logging.error(f'Blob error body: {error_body}')
            raise Exception(f'Blob Storage auth error {e.code}: {e.reason} - {error_body}')
        
        logging.info(f'JSON uploaded to blob: {blob_name}')
        
        # Notifications will be triggered automatically by separate NotificationFunction
        # when JSON file appears in blob storage (blob trigger)
        
        return func.HttpResponse(json.dumps({
            "status": "success",
            "message": f"PDF processed successfully in {environment} environment",
            "environment": environment,
            "blob_name": blob_name,
            "text_length": len(extracted_text),
            "page_count": page_count
        }), mimetype="application/json")

    except Exception as e:
        logging.error(f'Error in PDF processing: {str(e)}', exc_info=True)
        return func.HttpResponse(f"Processing error: {str(e)}", status_code=500)