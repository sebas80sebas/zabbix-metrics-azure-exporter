import logging
import azure.functions as func
from export_metrics_csv import export_metrics
from csv_to_excel_dashboard import generate_excel
from send_to_teams import (
    generate_container_sas,
    list_container_files,
    send_to_teams_workflow,
    CONTAINER_NAME,
    SAS_EXPIRY_HOURS,
    ONLY_LATEST_FILE
)
import os
from datetime import datetime, timezone

app = func.FunctionApp()

@app.schedule(
    schedule="0 0 1 * *",  # Day 1 of each month at 00:00
    arg_name="mytimer",
    run_on_startup=False,
    use_monitor=False
)
def monthly_metrics_export(mytimer: func.TimerRequest) -> None:
    logging.info("Starting Azure Function: monthly metrics extraction")
    
    try:
        # Step 1: Export metrics
        logging.info("Exporting metrics to CSV...")
        export_metrics()
        
        # Step 2: Generate Excel
        logging.info("Generating Excel file...")
        generate_excel()
        
        # Step 3: Send to Teams with SAS token
        logging.info("Generating SAS token and sending to Teams...")
        send_to_teams()
        
        logging.info("Process completed: CSVs and Excel uploaded to Blob Storage, Teams notified")
        
    except Exception as e:
        logging.error(f"Error executing function: {e}")
        raise


def send_to_teams() -> None:
    """
    Generates SAS token and sends it to Teams via Workflow in both languages
    """
    connection_string = os.getenv('AZURE_STORAGE_CONNECTION_STRING')
    webhook_url = os.getenv('TEAMS_WEBHOOK_URL', '')
    
    if not connection_string:
        logging.error("AZURE_STORAGE_CONNECTION_STRING environment variable not set")
        raise ValueError("Missing AZURE_STORAGE_CONNECTION_STRING")
    
    try:
        # Generate SAS token for container
        logging.info("Generating SAS token for container...")
        container_url, sas_token, expiry_time, account_name = generate_container_sas(
            connection_string=connection_string,
            container_name=CONTAINER_NAME,
            expiry_hours=SAS_EXPIRY_HOURS
        )
        
        # List available Excel files
        logging.info("Listing Excel files in container...")
        files = list_container_files(
            connection_string=connection_string,
            container_name=CONTAINER_NAME,
            only_latest=ONLY_LATEST_FILE
        )
        
        if not files:
            logging.warning("No Excel files found in container")
        else:
            logging.info(f"Found {len(files)} Excel file(s)")
        
        # Send to Teams if webhook is configured
        if webhook_url:
            logging.info("Sending notifications to Teams Workflow...")
            
            # Send Spanish message
            logging.info("Sending Spanish notification...")
            result_es = send_to_teams_workflow(
                webhook_url=webhook_url,
                container_url=container_url,
                sas_token=sas_token,
                files=files,
                account_name=account_name,
                container_name=CONTAINER_NAME,
                expiry_time=expiry_time,
                expiry_hours=SAS_EXPIRY_HOURS,
                language="es"
            )
            
            # Send English message
            logging.info("Sending English notification...")
            result_en = send_to_teams_workflow(
                webhook_url=webhook_url,
                container_url=container_url,
                sas_token=sas_token,
                files=files,
                account_name=account_name,
                container_name=CONTAINER_NAME,
                expiry_time=expiry_time,
                expiry_hours=SAS_EXPIRY_HOURS,
                language="en"
            )
            
            if result_es and result_en:
                logging.info("Both notifications sent successfully to Teams (Spanish and English)")
            elif result_es or result_en:
                logging.warning("Only one notification sent successfully")
            else:
                logging.warning("Both Teams notifications failed to send")
        else:
            logging.info("TEAMS_WEBHOOK_URL not configured, skipping Teams notification")
            
    except FileNotFoundError as e:
        logging.error(f"Container not found: {e}")
        raise
    except ValueError as e:
        logging.error(f"Invalid configuration: {e}")
        raise
    except Exception as e:
        logging.error(f"Error in send_to_teams: {e}")
        raise