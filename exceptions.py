from fastapi import HTTPException
from fastapi.responses import JSONResponse

class S3UploadError(Exception):
    """Custom exception for S3 upload errors"""
    pass

class TextractError(Exception):
    """Custom exception for Textract processing errors"""
    pass

async def http_exception_handler(request, exc) -> JSONResponse:
    """
    Global exception handler for HTTP exceptions
    """
    return JSONResponse(
        content={
            "status": "error",
            "message": str(exc.detail),
            "data": None
        },
        status_code=exc.status_code
    )

async def general_exception_handler(request, exc) -> JSONResponse:
    """
    Global exception handler for all other exceptions
    """
    return JSONResponse(
        content={
            "status": "error",
            "message": "Internal server error",
            "data": None
        },
        status_code=500
    ) 