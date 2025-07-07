from fastapi import APIRouter, File, UploadFile, Request
from typing import Dict
import uuid
import json
import logging
from PyPDF2 import PdfReader
from io import BytesIO
from celery_tasks import process_bank_statement
from utils import get_valkey_client

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Bank Statements"])

def is_pdf_password_protected(file_bytes: bytes) -> bool:
    try:
        reader = PdfReader(BytesIO(file_bytes))
        return reader.is_encrypted
    except Exception as e:
        print(f"Error checking PDF encryption: {e}")
        return False

async def process_pdf_analysis(file_content: bytes, filename: str) -> Dict:
    """
    Process PDF analysis and start Celery task.
    """
    try:
        # Validate file content
        if not file_content or len(file_content) == 0:
            return {
                "status": "error",
                "message": "Empty file content",
                "data": None
            }
        
        # Generate a unique task ID
        task_id = str(uuid.uuid4())
        
        # Start Celery task
        try:
            task = process_bank_statement.delay(file_content, filename, task_id)
            if not task:
                return {
                    "status": "error",
                    "message": "Failed to start analysis task",
                    "data": None
                }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Failed to queue analysis task: {str(e)}",
                "data": None
            }
        
        return {
            "status": "success",
            "message": "Bank statement analysis started",
            "data": {
                "task_id": task_id,
                "status": "queued"
            }
        }
        
    except Exception as e:
        print(f"Error starting analysis: {str(e)}")
        return {
            "status": "error",
            "message": str(e),
            "data": None
        }

@router.post("/analyze-bank-statement")
async def analyze_statement(
    file: UploadFile = File(...),
    request: Request = None
) -> Dict:
    """
    Analyze a bank statement PDF and extract tables.
    Returns a task ID that can be used to check the analysis status.
    """

    # check if file is pdf
    if not file.filename.lower().endswith('.pdf'):
        return {
            "status": "error",
            "message": "Only PDF files are allowed",
            "data": None
        }
    
    # Check file size (limit to 10MB)
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
    if file.size and file.size > MAX_FILE_SIZE:
        return {
            "status": "error",
            "message": f"File size too large. Maximum allowed size is {MAX_FILE_SIZE // (1024*1024)}MB",
            "data": None
        }
    
    try:
        # Read file content
        file_content = await file.read()

        # check if file is password protected use with keyword
        # if is_pdf_password_protected(file_content):
        #     return {
        #         "status": "error",
        #         "message": "File is password protected",
        #         "data": None
        #     }

        # Process the PDF directly
        return await process_pdf_analysis(file_content, file.filename)
        
    except Exception as e:
        print(f"Error processing PDF: {str(e)}")
        return {
            "status": "error",
            "message": str(e),
            "data": None
        }

@router.get("/check-bs-status/{task_id}")
async def check_bs_status(task_id: str) -> Dict:
    """
    Check the status of a bank statement analysis task.
    """
    try:
        # Validate task ID format (UUID)
        try:
            uuid.UUID(task_id)
        except ValueError:
            return {
                "status": "error",
                "message": "Invalid task ID format",
                "data": None
            }
        
        client = await get_valkey_client()
        task_data = client.get(task_id)
        
        if not task_data:
            return {
                "status": "error",
                "message": "Invalid task ID",
                "data": None
            }

        task_info = json.loads(task_data)
        return task_info
    except json.JSONDecodeError as e:
        return {
            "status": "error",
            "message": f"Invalid task data format: {str(e)}",
            "data": None
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to retrieve task status: {str(e)}",
            "data": None
        } 