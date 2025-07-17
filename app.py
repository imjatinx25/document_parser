from fastapi import FastAPI, File, UploadFile, HTTPException, Form, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from bank_statement_service import process_bank_statement
from typing import Dict, Optional
import os
import tempfile
from dotenv import load_dotenv
import json
import uuid
import time
import logging
from collections import defaultdict
from fastapi.responses import StreamingResponse
import asyncio
from progress_manager import progress_manager


log_dir = 'D:\\tmp'
os.makedirs(log_dir, exist_ok=True)


# Configure logging
logging.basicConfig(
    filename='/tmp/app.log',
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
)
logger = logging.getLogger(__name__)

# Import custom modules
# from celery_tasks import process_bank_statement
from pdf_service import check_pdf_password_protection, process_pdf_file, PDFPasswordError, PDFProcessingError

# Load environment variables
load_dotenv()
status_cache = {}
# Initialize FastAPI app
app = FastAPI(
    title="Bank Statement Analyzer",
    description="API for analyzing bank statements using AWS Textract and GPT",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add trusted host middleware
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["*"]  # Configure appropriately for production
)

# Simple rate limiting
request_counts = defaultdict(list)
RATE_LIMIT_WINDOW = 60  # 1 minute
RATE_LIMIT_MAX_REQUESTS = 10  # 10 requests per minute

def check_rate_limit(client_ip: str) -> bool:
    """Check if client has exceeded rate limit"""
    current_time = time.time()
    # Remove old requests outside the window
    request_counts[client_ip] = [req_time for req_time in request_counts[client_ip] 
                                if current_time - req_time < RATE_LIMIT_WINDOW]
    
    # Check if limit exceeded
    if len(request_counts[client_ip]) >= RATE_LIMIT_MAX_REQUESTS:
        return False
    
    # Add current request
    request_counts[client_ip].append(current_time)
    return True

# Valkey Glide client
# valkey_client = None

# async def get_valkey_client():
#     """Get or create Valkey Glide client"""
#     global valkey_client
#     if valkey_client is None:
#         try:
#             from glide import (
#                 GlideClusterClient,
#                 GlideClusterClientConfiguration,
#                 Logger,
#                 LogLevel,
#                 NodeAddress,
#             )
            
#             # Set logger configuration
#             Logger.set_logger_config(LogLevel.INFO)
            
#             # Get Valkey configuration from environment variables
#             valkey_host = os.getenv('VALKEY_HOST', 'localhost')
#             valkey_port = int(os.getenv('VALKEY_PORT', 6379))
#             use_tls = os.getenv('VALKEY_USE_TLS', 'false').lower() == 'true'
            
#             # Configure the Glide Cluster Client
#             addresses = [NodeAddress(valkey_host, valkey_port)]
#             config = GlideClusterClientConfiguration(addresses=addresses, use_tls=use_tls)
            
#             print(f"Connecting to Valkey Glide at {valkey_host}:{valkey_port}...")
#             valkey_client = await GlideClusterClient.create(config)
#             print("Valkey Glide connection successful")
            
#         except Exception as e:
#             print(f"Valkey Glide connection failed: {e}")
#             raise
    
#     return valkey_client

# # Test Valkey connection on startup
# @app.on_event("startup")
# async def startup_event():
#     """Test Valkey connection on application startup"""
#     try:
#         logger.info("Starting application...")
#         await get_valkey_client()
#         logger.info("Application started successfully")
#     except Exception as e:
#         logger.error(f"Failed to connect to Valkey on startup: {e}")

# # Cleanup Valkey client on shutdown
# @app.on_event("shutdown")
# async def shutdown_event():
#     """Cleanup Valkey client on application shutdown"""
#     global valkey_client
#     if valkey_client:
#         try:
#             await valkey_client.close()
#             logger.info("Valkey client connection closed")
#         except Exception as e:
#             logger.error(f"Error closing Valkey client: {e}")

# Home endpoint
@app.get("/")
async def home() -> Dict:
    """
    Root endpoint that provides API information and available endpoints.
    """
    return {
        "status": "success",
        "data": {
            "api_status": "online",
            "message": "Welcome to Bank Statement Analyzer API",
            "endpoints": {
                "home": "GET /",
                "health": "GET /health",
                "analyze_statement": "POST /analyze-bank-statement",
                "check_status": "GET /check-bs-status/{task_id}",
                "docs": "GET /docs",
                "redoc": "GET /redoc"
            }
        }
    }

# Health check endpoint
@app.get("/health")
async def health_check() -> Dict:
    """
    Health check endpoint for monitoring.
    """
    try:
        # Check Valkey connection
        client = await get_valkey_client()
        await client.ping()
        
        return {
            "status": "healthy",
            "message": "All services are operational",
            "timestamp": time.time(),
            "services": {
                "valkey": "connected",
                "celery": "available"
            }
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "unhealthy",
            "message": f"Service check failed: {str(e)}",
            "timestamp": time.time(),
            "services": {
                "valkey": "disconnected",
                "celery": "unknown"
            }
        }

# Analyze statement endpoint
@app.post("/analyze-bank-statement")
# async def analyze_statement(
#     file: UploadFile = File(...),
#     password: Optional[str] = Form(None),
#     request: Request = None
# ) -> Dict:
#     """
#     Analyze a bank statement PDF and extract tables.
#     Returns a task ID that can be used to check the analysis status.
#     If the PDF is password protected, the password parameter should be provided.
#     """
#     # Rate limiting
#     if request:
#         client_ip = request.client.host
#         if not check_rate_limit(client_ip):
#             return {
#                 "status": "error",
#                 "message": "Rate limit exceeded. Please try again later.",
#                 "data": None
#             }
    
#     if not file.filename.lower().endswith('.pdf'):
#         return {
#             "status": "error",
#             "message": "Only PDF files are allowed",
#             "data": None
#         }
    
#     # Check file size (limit to 10MB)
#     MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
#     if file.size and file.size > MAX_FILE_SIZE:
#         return {
#             "status": "error",
#             "message": f"File size too large. Maximum allowed size is {MAX_FILE_SIZE // (1024*1024)}MB",
#             "data": None
#         }
    
#     try:
#         # Read file content
#         file_content = await file.read()
        
#         # Check if PDF is password protected
#         if check_pdf_password_protection(file_content):
#             if password is None:
#                 return {
#                     "status": "password_required",
#                     "message": "PDF is password protected. Please provide the password parameter.",
#                     "data": {
#                         "example_request": {
#                             "file": "your_pdf_file.pdf",
#                             "password": "your_password"
#                         }
#                     }
#                 }
            
#             # Process the PDF with the provided password
#             try:
#                 unlocked_content = process_pdf_file(file_content, password)
#                 return await process_pdf_analysis(unlocked_content, file.filename)
                
#             except PDFPasswordError as e:
#                 return {
#                     "status": "error",
#                     "message": str(e),
#                     "data": None
#                 }
#             except PDFProcessingError as e:
#                 return {
#                     "status": "error",
#                     "message": str(e),
#                     "data": None
#                 }
#         else:
#             # PDF is not password protected, process directly
#             return await process_pdf_analysis(file_content, file.filename)
        
#     except Exception as e:
#         print(f"Error processing PDF: {str(e)}")
#         return {
#             "status": "error",
#             "message": str(e),
#             "data": None
#         }

@app.post("/analyze-bank-statement")
async def analyze_statement(
    file: UploadFile = File(...),
    password: Optional[str] = Form(None),
    request: Request = None
) -> Dict:
    """
    Analyze a bank statement PDF and extract tables.
    Returns immediate processed output (non-SSE, no streaming).
    """
    if request:
        client_ip = request.client.host
        if not check_rate_limit(client_ip):
            return {
                "status": "error",
                "message": "Rate limit exceeded. Please try again later.",
                "data": None
            }

    if not file.filename.lower().endswith('.pdf'):
        return {"status": "error", "message": "Only PDF files are allowed", "data": None}

    MAX_FILE_SIZE = 10 * 1024 * 1024
    if file.size and file.size > MAX_FILE_SIZE:
        return {"status": "error", "message": "File size too large. Max 10MB.", "data": None}

    try:
        file_content = await file.read()

        if check_pdf_password_protection(file_content):
            if password is None:
                return {"status": "password_required", "message": "PDF is password protected. Provide the password.", "data": None}
            try:
                unlocked_content = process_pdf_file(file_content, password)
                return await process_pdf_analysis(unlocked_content, file.filename)
            except (PDFPasswordError, PDFProcessingError) as e:
                return {"status": "error", "message": str(e), "data": None}
        else:
            return await process_pdf_analysis(file_content, file.filename)

    except Exception as e:
        return {"status": "error", "message": str(e), "data": None}

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

# API to poll task status
@app.get("/check-bs-status/{task_id}")
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
        task_data = await client.get(task_id)
        
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

# @app.post("/process-statement")
# async def process_statement(file: UploadFile = File(...)):
#     # Save uploaded file to a temporary location
#     suffix = os.path.splitext(file.filename)[1]
#     with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
#         temp_file.write(await file.read())
#         temp_path = temp_file.name

#     try:
#         # Read file bytes
#         with open(temp_path, 'rb') as f:
#             file_bytes = f.read()

#         # Process the bank statement
#         result = await process_bank_statement(file_bytes)
#         return result

#     finally:
#         # Cleanup the temporary file
#         os.remove(temp_path)

# @app.post("/process-statement")
# async def process_statement(file: UploadFile = File(...)):
#     import uuid
#     task_id = str(uuid.uuid4())
#     progress_manager.init_task(task_id)

#     suffix = os.path.splitext(file.filename)[1]
#     with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
#         temp_file.write(await file.read())
#         temp_path = temp_file.name

#     try:
#         with open(temp_path, 'rb') as f:
#             file_bytes = f.read()

#         result = await process_bank_statement(file_bytes, task_id=task_id)

#         return {
#             "task_id": task_id,
#             "summary": result
#         }

#     finally:
#         os.remove(temp_path)


@app.post("/api/process-statement")
# # async def process_statement(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
# #     task_id = str(uuid.uuid4())
# #     progress_manager.init_task(task_id)

# #     suffix = os.path.splitext(file.filename)[1]
# #     with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
# #         temp_file.write(await file.read())
# #         temp_path = temp_file.name

# #     with open(temp_path, 'rb') as f:
# #         file_bytes = f.read()

# #     # Process in the background
# #     background_tasks.add_task(background_process, file_bytes, task_id, temp_path)

# #     return {"task_id": task_id, "message": "Processing started. Listen to /progress-stream/{task_id}"}
async def process_statement(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    """
    Background processing with progress streaming.
    """
    task_id = str(uuid.uuid4())
    progress_manager.init_task(task_id)

    suffix = os.path.splitext(file.filename)[1]
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
        temp_file.write(await file.read())
        temp_path = temp_file.name

    with open(temp_path, 'rb') as f:
        file_bytes = f.read()

    background_tasks.add_task(background_process, file_bytes, task_id, temp_path)

    return {"task_id": task_id, "message": f"Processing started. Listen on /progress-stream/{task_id}"}


# async def background_process(file_bytes: bytes, task_id: str, temp_path: str):
#     try:
#         result = await process_bank_statement(file_bytes, task_id=task_id)
#         status_cache[task_id] = result

#         await progress_manager.update_progress(
#             task_id,
#             progress=100,
#             message="Processing complete!",
#             data=result
#         )
#     finally:
#         os.remove(temp_path)


async def background_process(file_bytes: bytes, task_id: str, temp_path: str):
    try:
        result = await process_bank_statement(file_bytes, task_id=task_id)
        status_cache[task_id] = result

        # Final progress update WITH COMPLETE RESULT
        await progress_manager.update_progress(
            task_id,
            progress=100,
            message="Processing complete!",
            data=result  # <-- This is your full result
        )
    finally:
        os.remove(temp_path)

# @app.get("/progress-stream/{task_id}")
# async def progress_stream(task_id: str):
#     return StreamingResponse(progress_manager.listen(task_id), media_type="text/event-stream")

@app.get("/api/progress-stream/{task_id}")
async def progress_stream(task_id: str):
    return StreamingResponse(progress_manager.listen(task_id), media_type="text/event-stream")

# Run the app
if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv('APP_PORT', 8001)))
