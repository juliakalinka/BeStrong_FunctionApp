import azure.functions as func
import logging
import sys
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
from typing import Dict, Any, Optional

app = func.FunctionApp()

def send_discord_notification(message: str) -> bool:
    """Відправляє повідомлення в Discord через Webhook"""
    webhook_url = os.environ.get("DiscordWebhookUrl")
    if not webhook_url:
        logging.warning("Discord webhook URL not configured")
        return False

    try:
        payload = {
            "content": message,
            "username": "PDF Analysis Bot",
            "avatar_url": "https://cdn.discordapp.com/attachments/your-avatar-url.png"  # Optional
        }
        response = requests.post(webhook_url, json=payload, timeout=30)
        response.raise_for_status()
        logging.info("Discord notification sent successfully")
        return True
    except requests.exceptions.RequestException as e:
        logging.error(f"Failed to send Discord notification: {str(e)}")
        return False

def send_slack_notification(message: str) -> bool:
    """Відправляє повідомлення в Slack через Webhook"""
    webhook_url = os.environ.get("SlackWebhookUrl")
    if not webhook_url:
        logging.warning("Slack webhook URL not configured")
        return False

    try:
        payload = {
            "text": message,
            "username": "PDF Analysis Bot",
            "icon_emoji": ":robot_face:"
        }
        response = requests.post(webhook_url, json=payload, timeout=30)
        response.raise_for_status()
        logging.info("Slack notification sent successfully")
        return True
    except requests.exceptions.RequestException as e:
        logging.error(f"Failed to send Slack notification: {str(e)}")
        return False

def extract_structured_data(content: str) -> Dict[str, Any]:
    """Витягує структуровані дані з тексту рахунку згідно з макетом PDF"""
    data = {
        "company_info": {},
        "customer_info": {},
        "invoice_details": {},
        "meter_readings": [],
        "billing_details": {},
        "payment_details": {}
    }
    
    if not content or not content.strip():
        logging.warning("Empty content provided for data extraction")
        return data
        
    lines = [line.strip() for line in content.split('\n') if line.strip()]

    try:
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
                while (j < len(lines) and 
                       not lines[j].startswith("Bill Payer Address") and 
                       not lines[j].startswith("Invoice Number") and 
                       not lines[j].startswith("Meter Serial Numbers")):
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
            elif "Invoice Date:" in line and i + 1 < len(lines):
                data["invoice_details"]["date"] = lines[i + 1].strip()
            elif "Payment Due Date:" in line and i + 1 < len(lines):
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
                
                # Handle date parsing
                if any(month in end_value for month in ["Jan", "Feb", "Mar", "Apr", "May", "Jun", 
                                                      "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]):
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
        _extract_billing_details(lines, data)
        
        # 6. Payment details
        _extract_payment_details(lines, data)
        
    except Exception as e:
        logging.error(f"Error extracting structured data: {str(e)}")
        data["extraction_error"] = str(e)

    return data

def _extract_billing_details(lines: list, data: Dict[str, Any]) -> None:
    """Helper function to extract billing details"""
    billing_period = None
    rate = None
    consumption = None
    
    for i, line in enumerate(lines):
        if "Billing Period" in line and i + 1 < len(lines):
            val = lines[i + 1].strip()
            if any(char.isdigit() for char in val):
                billing_period = val
        elif "Cost per kWh" in line and i + 1 < len(lines):
            val = lines[i + 1].strip()
            if any(char.isdigit() for char in val):
                rate = val
        elif "Total Consumption" in line and i + 1 < len(lines):
            val = lines[i + 1].strip()
            if any(char.isdigit() for char in val):
                consumption = val
        elif "Net Cost" in line and i + 1 < len(lines):
            data["billing_details"]["net_cost"] = lines[i + 1].strip()
        elif "VAT @" in line:
            vat = line.split("VAT @")[-1].split("%", 1)[0].strip() + "%"
            data["billing_details"]["vat"] = vat
        elif "Total Amount Due" in line and i + 1 < len(lines):
            data["billing_details"]["total"] = lines[i + 1].strip()
    
    if billing_period:
        data["billing_details"]["period"] = billing_period
    if rate:
        data["billing_details"]["rate"] = rate
    if consumption:
        data["billing_details"]["consumption"] = consumption

def _extract_payment_details(lines: list, data: Dict[str, Any]) -> None:
    """Helper function to extract payment details"""
    for i, line in enumerate(lines):
        if "Account Name" in line and i + 1 < len(lines):
            data["payment_details"]["account_name"] = lines[i + 1].strip()
        elif "Bank Sort Code" in line and i + 1 < len(lines):
            data["payment_details"]["sort_code"] = lines[i + 1].strip()
        elif "Account Number" in line and i + 1 < len(lines):
            data["payment_details"]["account_number"] = lines[i + 1].strip()

def validate_environment_variables() -> Dict[str, str]:
    """Validates required environment variables"""
    required_vars = [
        "FileShareConnectionString",
        "FormRecognizerEndpoint", 
        "FormRecognizerKey",
        "BlobStorageConnectionString"
    ]
    
    missing_vars = []
    for var in required_vars:
        if not os.environ.get(var):
            missing_vars.append(var)
    
    if missing_vars:
        raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")
    
    return {var: os.environ[var] for var in required_vars}

@app.route(route="process-pdf", auth_level=func.AuthLevel.FUNCTION)
def process_pdf(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('PDF processing request received')
    
    try:
        # Validate environment variables
        env_vars = validate_environment_variables()
        
        # Get file name from request
        file_name = req.params.get('file_name')
        if not file_name:
            error_msg = "Missing required parameter 'file_name'"
            logging.error(error_msg)
            return func.HttpResponse(error_msg, status_code=400)
        
        if not file_name.lower().endswith('.pdf'):
            error_msg = "File must be a PDF"
            logging.error(error_msg)
            return func.HttpResponse(error_msg, status_code=400)

        logging.info(f'Processing PDF file: {file_name}')

        # Download PDF from File Share
        share_service_client = ShareServiceClient.from_connection_string(
            env_vars["FileShareConnectionString"]
        )
        
        share_name = "myshare"  # Consider making this configurable
        share_client = share_service_client.get_share_client(share_name)
        file_client = share_client.get_file_client(file_name)
        
        # Create temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_file:
            try:
                download = file_client.download_file()
                download.readinto(temp_file)
                temp_file_path = temp_file.name
                logging.info(f"Successfully downloaded PDF: {file_name}")
            except Exception as e:
                logging.error(f"Failed to download file from share: {str(e)}")
                raise

        try:
            # Process PDF with Form Recognizer
            document_analysis_client = DocumentAnalysisClient(
                endpoint=env_vars["FormRecognizerEndpoint"], 
                credential=AzureKeyCredential(env_vars["FormRecognizerKey"])
            )
            
            with open(temp_file_path, "rb") as pdf_file:
                poller = document_analysis_client.begin_analyze_document(
                    "prebuilt-document", pdf_file
                )
                result = poller.result()
            
            logging.info("PDF analysis completed successfully")
            
            # Extract structured data
            structured_data = extract_structured_data(result.content)
            
            # Prepare analysis result
            analysis_result = {
                "file_name": file_name,
                "processed_at": datetime.now().isoformat(),
                "structured_data": structured_data,
                "raw_content": {
                    "text": result.content,
                    "page_count": len(result.pages),
                    "pages": [
                        {
                            "page_number": page.page_number,
                            "width": page.width,
                            "height": page.height,
                            "unit": page.unit,
                            "word_count": len(page.words) if hasattr(page, 'words') else 0,
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
                            ] if hasattr(page, 'words') else []
                        }
                        for page in result.pages
                    ]
                }
            }
            
        finally:
            # Clean up temporary file
            if os.path.exists(temp_file_path):
                os.unlink(temp_file_path)

        # Save result to Blob Storage
        blob_service_client = BlobServiceClient.from_connection_string(
            env_vars["BlobStorageConnectionString"]
        )
        
        container_name = "mycontainer"  # Consider making this configurable
        container_client = blob_service_client.get_container_client(container_name)
        
        # Ensure container exists
        try:
            container_client.create_container()
            logging.info(f"Created blob container: {container_name}")
        except Exception:
            # Container probably already exists
            pass
        
        # Generate unique blob name
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        result_blob_name = f"{os.path.splitext(file_name)[0]}_{timestamp}.json"
        
        blob_client = container_client.get_blob_client(result_blob_name)
        blob_data = json.dumps(analysis_result, indent=2, ensure_ascii=False)
        
        blob_client.upload_blob(blob_data, overwrite=True)
        logging.info(f"Successfully saved analysis result to blob: {result_blob_name}")
        
        # Send notifications
        notification_message = (
            f"PDF Analysis Complete!\n"
            f"File: {file_name}\n"
            f"Result saved as: {result_blob_name}\n"
            f"Pages processed: {len(result.pages)}\n"
            f"Processed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        
        discord_sent = send_discord_notification(notification_message)
        slack_sent = send_slack_notification(notification_message)
        
        # Return success response
        response_data = {
            "message": "PDF processed successfully",
            "file_name": file_name,
            "result_blob": result_blob_name,
            "pages_processed": len(result.pages),
            "notifications": {
                "discord_sent": discord_sent,
                "slack_sent": slack_sent
            }
        }
        
        return func.HttpResponse(
            json.dumps(response_data, ensure_ascii=False),
            mimetype="application/json",
            status_code=200
        )
        
    except ValueError as ve:
        error_message = f"Configuration error: {str(ve)}"
        logging.error(error_message)
        send_discord_notification(f"Configuration Error: {str(ve)}")
        send_slack_notification(f"Configuration Error: {str(ve)}")
        return func.HttpResponse(error_message, status_code=500)
        
    except Exception as e:
        error_message = f"Error processing PDF '{file_name}': {str(e)}"
        logging.error(error_message, exc_info=True)
        send_discord_notification(f"Error processing PDF '{file_name}': {str(e)}")
        send_slack_notification(f"Error processing PDF '{file_name}': {str(e)}")
        return func.HttpResponse(error_message, status_code=500)

@app.route(route="health", auth_level=func.AuthLevel.ANONYMOUS)
def health_check(req: func.HttpRequest) -> func.HttpResponse:
    """Health check endpoint"""
    try:
        # Basic environment check
        required_vars = ["FileShareConnectionString", "FormRecognizerEndpoint", 
                        "FormRecognizerKey", "BlobStorageConnectionString"]
        missing_vars = [var for var in required_vars if not os.environ.get(var)]
        
        environment = os.environ.get("ENVIRONMENT", "unknown")
        build_id = os.environ.get("BUILD_ID", "unknown")
        
        health_data = {
            "status": "healthy" if not missing_vars else "unhealthy",
            "timestamp": datetime.now().isoformat(),
            "environment": environment,
            "build_id": build_id,
            "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "function_worker_runtime": os.environ.get("FUNCTIONS_WORKER_RUNTIME", "unknown"),
            "function_extension_version": os.environ.get("FUNCTIONS_EXTENSION_VERSION", "unknown")
        }
        
        if missing_vars:
            health_data["missing_config"] = missing_vars
            health_data["warning"] = "Some configuration variables are missing but basic function is operational"
            # Still return 200 for basic connectivity test
            status_code = 200
        else:
            health_data["message"] = "All configuration variables are present"
            status_code = 200
        
        return func.HttpResponse(
            json.dumps(health_data, indent=2),
            mimetype="application/json",
            status_code=status_code
        )
    except Exception as e:
        return func.HttpResponse(
            json.dumps({
                "status": "error",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }, indent=2),
            mimetype="application/json",
            status_code=500
        )

@app.route(route="ping", auth_level=func.AuthLevel.ANONYMOUS)
def ping(req: func.HttpRequest) -> func.HttpResponse:
    """Simple ping endpoint for basic connectivity test"""
    return func.HttpResponse(
        json.dumps({
            "status": "ok",
            "timestamp": datetime.now().isoformat(),
            "message": "Function App is responding"
        }),
        mimetype="application/json",
        status_code=200
    )

# Keep the original function for backward compatibility
@app.route(route="PdfOcrFunction", auth_level=func.AuthLevel.FUNCTION)
def PdfOcrFunction(req: func.HttpRequest) -> func.HttpResponse:
    """Legacy endpoint - redirects to process-pdf"""
    logging.info('Legacy endpoint accessed - redirecting to process-pdf')
    
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