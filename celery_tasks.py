from celery_app import celery_app
from aws_service import extract_tables_from_pdf
from gpt_service import analyze_table_structure, extract_transactions, categorize_transactions
from analysis import generate_transaction_breakdown
import json
import asyncio
from io import BytesIO
import os

# Valkey Glide client
valkey_client = None

async def get_valkey_client():
    """Get or create Valkey Glide client"""
    global valkey_client
    if valkey_client is None:
        try:
            from glide import (
                GlideClusterClient,
                GlideClusterClientConfiguration,
                Logger,
                LogLevel,
                NodeAddress,
            )
            
            # Set logger configuration
            Logger.set_logger_config(LogLevel.INFO)
            
            # Get Valkey configuration from environment variables
            valkey_host = os.getenv('VALKEY_HOST', 'localhost')
            valkey_port = int(os.getenv('VALKEY_PORT', 6379))
            use_tls = os.getenv('VALKEY_USE_TLS', 'false').lower() == 'true'
            
            # Configure the Glide Cluster Client
            addresses = [NodeAddress(valkey_host, valkey_port)]
            config = GlideClusterClientConfiguration(addresses=addresses, use_tls=use_tls)
            
            print(f"Connecting to Valkey Glide at {valkey_host}:{valkey_port}...")
            valkey_client = await GlideClusterClient.create(config)
            print("Valkey Glide connection successful")
            
        except Exception as e:
            print(f"Valkey Glide connection failed: {e}")
            raise
    
    return valkey_client

# Utility to set task status/result
async def set_task_status(task_id: str, status: str, result: dict = None, expiry_seconds: int = 900):
    try:
        client = await get_valkey_client()
        data = {"status": status}
        if result:
            data["result"] = result
        
        # Set with expiry (Valkey Glide uses seconds for expiry)
        await client.set(task_id, json.dumps(data), ex=expiry_seconds)
    except Exception as e:
        print(f"Error setting task status: {e}")

# Helper function to run async code
def run_async(coro):
    try:
        # Try to get the current event loop
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # If loop is running, create a new one
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(coro)
            finally:
                loop.close()
        else:
            # Use existing loop
            return loop.run_until_complete(coro)
    except RuntimeError:
        # No event loop in current thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

@celery_app.task(name='process_bank_statement', bind=True, max_retries=3, ignore_result=True)
def process_bank_statement(self, file_content: bytes, filename: str, task_id: str):
    try:
        run_async(set_task_status(task_id, "in_progress", {"message": "Starting analysis..."}, 3600))

        # Create BytesIO object from file content
        file_obj = BytesIO(file_content)
        file_obj.name = filename

        # Extract tables using Textract
        run_async(set_task_status(task_id, "in_progress", {"message": "Extracting tables from PDF..."}, 3600))
        tables = run_async(extract_tables_from_pdf(file_obj))

        # Analyze table structure
        run_async(set_task_status(task_id, "in_progress", {"message": "Analyzing table structure..."}, 3600))
        table_analysis = run_async(analyze_table_structure(tables))

        # Extract transactions
        run_async(set_task_status(task_id, "in_progress", {"message": "Extracting transactions..."}, 3600))
        transactions = run_async(extract_transactions(tables, table_analysis))

        # Categorize transactions
        run_async(set_task_status(task_id, "in_progress", {"message": "Categorizing transactions..."}, 3600))
        categorized_transactions = run_async(categorize_transactions(transactions))

        # Generate transaction breakdown
        run_async(set_task_status(task_id, "in_progress", {"message": "Generating analysis report..."}, 3600))
        transaction_analysis = generate_transaction_breakdown(categorized_transactions)

        # Set final status and result
        result = {
            "message": f"Successfully analyzed {len(categorized_transactions)} transactions",
            "analysis": transaction_analysis
        }
        run_async(set_task_status(task_id, "done", result, 900))

    except Exception as e:
        run_async(set_task_status(task_id, "failed", {"error": str(e)}, 900))
        # Retry the task if it fails
        try:
            self.retry(exc=e, countdown=60)  # Retry after 60 seconds
        except self.MaxRetriesExceededError:
            raise 