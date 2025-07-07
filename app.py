from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from typing import Dict
import os
from dotenv import load_dotenv
import time
import logging
from utils import get_valkey_client

# Configure logging
logging.basicConfig(
    filename='/tmp/app.log',
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
)
logger = logging.getLogger(__name__)

# Import routers
from routers import health, statements

# Load environment variables
load_dotenv()

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

# Include routers
app.include_router(health.router, prefix="/api")
app.include_router(statements.router, prefix="/api")

# Test Valkey connection on startup
@app.on_event("startup")
async def startup_event():
    """Test Valkey connection on application startup"""
    try:
        logger.info("Starting application...")
        await get_valkey_client()
        logger.info("Application started successfully")
    except Exception as e:
        logger.error(f"Failed to connect to Valkey on startup: {e}")

# Cleanup Valkey client on shutdown
@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup Valkey client on application shutdown"""
    try:
        valkey_client = await get_valkey_client()
        if valkey_client:
            await valkey_client.close()  # close the glide client
            logger.info("Valkey client connection closed")
    except Exception as e:
        logger.error(f"Error closing Valkey client: {e}")

# Home endpoint
@app.get("/api")
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
                "home": "GET /api",
                "health": "GET /api/health",
                "analyze_statement": "POST /api/analyze-bank-statement",
                "check_status": "GET /api/check-bs-status/{task_id}",
                "docs": "GET /docs",
                "redoc": "GET /redoc"
            }
        }
    }

# Run the app
# if __name__ == '__main__':
#     import uvicorn
#     uvicorn.run(app, host="0.0.0.0", port=int(os.getenv('APP_PORT', 8001)), timeout_keep_alive=300)
