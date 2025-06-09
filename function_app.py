import azure.functions as func
import logging
from azure.storage.blob import BlobServiceClient
from azure.storage.fileshare import ShareServiceClient, ShareFileClient
from azure.ai.formrecognizer import DocumentAnalysisClient
from azure.core.credentials import AzureKeyCredential
import json
import os
import tempfile
from datetime import datetime
import requests
import re

app = func.FunctionApp()

def send_discord_notification(message: str):
    """Відправляє повідомлення в Discord через Webhook"""
    webhook_url = os.environ.get("DiscordWebhookUrl")
    if not webhook_url:
        logging.warning("Discord webhook URL not configured")
        return

    try:
        payload = {
            "content": message,
            "username": "PDF Analysis Bot"
        }
        response = requests.post(webhook_url, json=payload)
        response.raise_for_status()
        logging.info("Discord notification sent successfully")
    except Exception as e:
        logging.error(f"Failed to send Discord notification: {str(e)}")

def send_slack_notification(message: str):
    """Відправляє повідомлення в Slack через Webhook"""
    webhook_url = os.environ.get("SlackWebhookUrl")
    if not webhook_url:
        logging.warning("Slack webhook URL not configured")
        return

    try:
        payload = {
            "text": message
        }
        response = requests.post(webhook_url, json=payload)
        response.raise_for_status()
        logging.info("Slack notification sent successfully")
    except Exception as e:
        logging.error(f"Failed to send Slack notification: {str(e)}")

def extract_structured_data(content: str) -> dict:
    """Витягує структуровані дані з тексту рахунку згідно з макетом PDF (адреси, білінг, meter_readings)"""
    data = {
        "company_info": {},
        "customer_info": {},
        "invoice_details": {},
        "meter_readings": [],
        "billing_details": {},
        "payment_details": {}
    }
    lines = [line.strip() for line in content.split('\n') if line.strip()]

    # 1. Company address
    company_address = []
    vat_number = None
    for i, line in enumerate(lines):
        if "VAT No." in line:
            vat_number = line.split("VAT No.")[-1].strip().replace(":", "")
            break
        company_address.append(line)
    if company_address:
        data["company_info"]["address"] = " ".join(company_address[-4:])
    if vat_number:
        data["company_info"]["vat_number"] = vat_number

    # 2. Customer address
    for i, line in enumerate(lines):
        if "Address Where Meter Installed:" in line:
            customer_address = []
            j = i + 1
            while j < len(lines) and not lines[j].startswith("Bill Payer Address") and not lines[j].startswith("Invoice Number") and not lines[j].startswith("Meter Serial Numbers"):
                if lines[j]:
                    customer_address.append(lines[j])
                j += 1
            if customer_address:
                data["customer_info"]["address"] = " ".join(customer_address)
            break

    # 3. Invoice details
    for i, line in enumerate(lines):
        if "Invoice Number:" in line and i + 1 < len(lines):
            data["invoice_details"]["number"] = lines[i + 1].strip()
        if "Invoice Date:" in line and i + 1 < len(lines):
            data["invoice_details"]["date"] = lines[i + 1].strip()
        if "Payment Due Date:" in line and i + 1 < len(lines):
            data["invoice_details"]["due_date"] = lines[i + 1].strip()

    # 4. Meter readings
    for i, line in enumerate(lines):
        if line.isdigit() and i + 5 < len(lines):
            serial_number = line
            meter_type = lines[i + 1].strip().lower()
            start_value = lines[i + 2].strip()
            start_date = lines[i + 3].strip()
            end_value = lines[i + 4].strip()
            end_date = lines[i + 5].strip()
            if any(month in end_value for month in ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]):
                parts = end_value.split(" ", 1)
                if len(parts) == 2:
                    end_value = parts[0]
                    end_date = parts[1]
            if meter_type in ["generation", "export"]:
                data["meter_readings"].append({
                    "type": meter_type,
                    "serial_number": serial_number,
                    "start_reading": {"value": start_value, "date": start_date},
                    "end_reading": {"value": end_value, "date": end_date}
                })

    # 5. Billing details
    billing_period = None
    rate = None
    consumption = None
    for i, line in enumerate(lines):
        if "Billing Period" in line and i + 1 < len(lines):
            val = lines[i + 1].strip()
            if any(char.isdigit() for char in val):
                billing_period = val
        if "Cost per kWh" in line and i + 1 < len(lines):
            val = lines[i + 1].strip()
            if any(char.isdigit() for char in val):
                rate = val
        if "Total Consumption" in line and i + 1 < len(lines):
            val = lines[i + 1].strip()
            if any(char.isdigit() for char in val):
                consumption = val
        if "Net Cost" in line and i + 1 < len(lines):
            data["billing_details"]["net_cost"] = lines[i + 1].strip()
        if "VAT @" in line:
            vat = line.split("VAT @")[-1].split("%", 1)[0].strip() + "%"
            data["billing_details"]["vat"] = vat
        if "Total Amount Due" in line and i + 1 < len(lines):
            data["billing_details"]["total"] = lines[i + 1].strip()
    if billing_period:
        data["billing_details"]["period"] = billing_period
    if rate:
        data["billing_details"]["rate"] = rate
    if consumption:
        data["billing_details"]["consumption"] = consumption

    # 6. Payment details
    for i, line in enumerate(lines):
        if "Account Name" in line and i + 1 < len(lines):
            data["payment_details"]["account_name"] = lines[i + 1].strip()
        if "Bank Sort Code" in line and i + 1 < len(lines):
            data["payment_details"]["sort_code"] = lines[i + 1].strip()
        if "Account Number" in line and i + 1 < len(lines):
            data["payment_details"]["account_number"] = lines[i + 1].strip()

    return data

@app.route(route="process-pdf", auth_level=func.AuthLevel.FUNCTION)
def process_pdf(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Python HTTP trigger function processed a request.')

    try:
        file_share_connection_string = os.environ["FileShareConnectionString"]
        share_service_client = ShareServiceClient.from_connection_string(file_share_connection_string)
        file_name = req.params.get('file_name')
        if not file_name:
            return func.HttpResponse(
                "Please provide file_name parameter",
                status_code=400
            )
        share_client = share_service_client.get_share_client("myshare")
        file_client = share_client.get_file_client(file_name)
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_file:
            download = file_client.download_file()
            download.readinto(temp_file)
            temp_file_path = temp_file.name
        logging.info(f"Successfully downloaded PDF: {file_name}")
        form_recognizer_endpoint = os.environ["FormRecognizerEndpoint"]
        form_recognizer_key = os.environ["FormRecognizerKey"]
        document_analysis_client = DocumentAnalysisClient(
            endpoint=form_recognizer_endpoint, 
            credential=AzureKeyCredential(form_recognizer_key)
        )
        with open(temp_file_path, "rb") as pdf_file:
            poller = document_analysis_client.begin_analyze_document(
                "prebuilt-document", pdf_file
            )
            result = poller.result()
        os.unlink(temp_file_path)
        structured_data = extract_structured_data(result.content)
        analysis_result = {
            "structured_data": structured_data,
            "raw_content": {
                "text": result.content,
                "pages": [
                    {
                        "page_number": page.page_number,
                        "width": page.width,
                        "height": page.height,
                        "unit": page.unit,
                        "words": [
                            {
                                "text": word.content,
                                "confidence": word.confidence,
                                "polygon": [
                                    {"x": point.x, "y": point.y}
                                    for point in word.polygon
                                ] if hasattr(word, 'polygon') else None
                            }
                            for word in page.words
                        ]
                    }
                    for page in result.pages
                ]
            }
        }
        blob_connection_string = os.environ["BlobStorageConnectionString"]
        blob_service_client = BlobServiceClient.from_connection_string(blob_connection_string)
        container_name = "mycontainer"
        container_client = blob_service_client.get_container_client(container_name)
        try:
            container_client.create_container()
        except Exception:
            pass
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        result_blob_name = f"{os.path.splitext(file_name)[0]}_{timestamp}.json"
        blob_client = container_client.get_blob_client(result_blob_name)
        blob_client.upload_blob(
            json.dumps(analysis_result, indent=2),
            overwrite=True
        )
        logging.info(f"Successfully saved analysis result to blob: {result_blob_name}")
        notification_message = f"PDF Analysis Complete!\nFile: {file_name}\nResult saved as: {result_blob_name}"
        send_discord_notification(notification_message)
        send_slack_notification(notification_message)
        return func.HttpResponse(
            json.dumps({
                "message": "PDF processed successfully",
                "result_blob": result_blob_name
            }),
            mimetype="application/json",
            status_code=200
        )
    except Exception as e:
        error_message = f"Error processing PDF: {str(e)}"
        logging.error(error_message)
        send_discord_notification(error_message)
        send_slack_notification(error_message)
        return func.HttpResponse(
            error_message,
            status_code=500
        )

@app.route(route="PdfOcrFunction", auth_level=func.AuthLevel.FUNCTION)
def PdfOcrFunction(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Python HTTP trigger function processed a request.')

    name = req.params.get('name')
    if not name:
        try:
            req_body = req.get_json()
        except ValueError:
            pass
        else:
            name = req_body.get('name')

    if name:
        return func.HttpResponse(f"Hello, {name}. This HTTP triggered function executed successfully.")
    else:
        return func.HttpResponse(
             "This HTTP triggered function executed successfully. Pass a name in the query string or in the request body for a personalized response.",
             status_code=200
        )