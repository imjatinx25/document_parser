from fastapi import APIRouter, HTTPException
from typing import Dict
import time
import logging
from utils import get_valkey_client

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Health"])

@router.get("/health")
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