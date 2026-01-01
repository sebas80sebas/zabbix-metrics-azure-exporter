import logging
import azure.functions as func
from export_metrics_csv import export_metrics
from csv_to_excel_dashboard import generate_excel
from send_to_teams import (
    generate_container_sas,
    list_container_files,
    send_to_teams_workflow,
    SAS_EXPIRY_HOURS,
    ONLY_LATEST_FILE
)
import os
from datetime import datetime

app = func.FunctionApp()

@app.schedule(
    schedule="0 0 1 * *",  # Day 1 of each month at 00:00
    arg_name="mytimer",
    run_on_startup=False,
    use_monitor=False
)
def monthly_metrics_export(mytimer: func.TimerRequest) -> None:
    start_time = datetime.now()
    logging.info("Starting Multi-Client Zabbix Metrics extraction")
    
    clients_str = os.getenv('CLIENTS', '')
    if not clients_str:
        logging.error("No CLIENTS configured in environment variables. Check your configuration.")
        return

    clients = [c.strip() for c in clients_str.split(',') if c.strip()]
    logging.info(f"Identified {len(clients)} clients to process: {clients}")

    for client in clients:
        logging.info(f">>> Processing Client: {client.upper()} <<<")
        container_name = f"metrics-{client}"
        
        try:
            # 1. Fetch Credentials
            zabbix_url = os.getenv(f'ZABBIX_URL_{client.upper()}')
            zabbix_user = os.getenv(f'ZABBIX_USER_{client.upper()}')
            zabbix_password = os.getenv(f'ZABBIX_PASSWORD_{client.upper()}')

            if not all([zabbix_url, zabbix_user, zabbix_password]):
                raise ValueError(f"Missing Zabbix credentials for client '{client}' in environment variables.")

            # Step 1: Export metrics from Zabbix API
            logging.info(f"[{client}] Connecting to Zabbix API...")
            export_metrics(zabbix_url, zabbix_user, zabbix_password, container_name)
            
            # Step 2: Generate Excel Dashboard and cleanup CSVs
            logging.info(f"[{client}] Processing dashboard and cleaning up temporary CSVs...")
            generate_excel(container_name)
            
            # Step 3: Notify Teams
            logging.info(f"[{client}] Generating secure links and notifying Teams...")
            send_to_teams(client, container_name)
            
            logging.info(f"[{client}] Successfully processed.")
            
        except Exception as e:
            # Robust error handling: Log the specific failure but continue with the next client
            logging.error(f"!!! CRITICAL FAILURE for client '{client}' !!!")
            logging.error(f"Error details: {str(e)}")
            logging.info(f"Proceeding to the next client in the list...")
            continue
    
    end_time = datetime.now()
    duration = end_time - start_time
    logging.info(f"Multi-Client process completed. Total duration: {duration}")


def send_to_teams(client_id: str, container_name: str) -> None:
    """
    Generates SAS token and sends it to Teams via Workflow for a specific client
    """
    connection_string = os.getenv('AZURE_STORAGE_CONNECTION_STRING')
    webhook_url = os.getenv('TEAMS_WEBHOOK_URL', '')
    
    if not connection_string:
        raise ValueError("AZURE_STORAGE_CONNECTION_STRING environment variable is not set. Cannot generate SAS tokens.")
    
    # Generate SAS token for container (read-only)
    container_url, sas_token, expiry_time, account_name = generate_container_sas(
        connection_string=connection_string,
        container_name=container_name,
        expiry_hours=SAS_EXPIRY_HOURS
    )
    
    # List Excel files (Only process .xlsx files, which were not deleted during cleanup)
    files = list_container_files(
        connection_string=connection_string,
        container_name=container_name,
        only_latest=ONLY_LATEST_FILE
    )
    
    if not files:
        logging.warning(f"[{client_id}] No Excel reports found in container '{container_name}'. Notification skipped.")
        return
    
    # Send to Teams if webhook is configured
    if webhook_url:
        # Send Bilingual notifications
        for lang in ["es", "en"]:
            success = send_to_teams_workflow(
                webhook_url=webhook_url,
                container_url=container_url,
                sas_token=sas_token,
                files=files,
                account_name=account_name,
                container_name=container_name,
                expiry_time=expiry_time,
                expiry_hours=SAS_EXPIRY_HOURS,
                client_id=client_id,
                language=lang
            )
            if not success:
                logging.error(f"[{client_id}] Failed to send {lang.upper()} notification to Teams.")
    else:
        logging.info(f"[{client_id}] TEAMS_WEBHOOK_URL not configured. Skipping notification.")