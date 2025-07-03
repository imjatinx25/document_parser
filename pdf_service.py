import PyPDF2
from io import BytesIO
from typing import Tuple, Optional

class PDFPasswordError(Exception):
    """Exception raised when PDF password is required but not provided"""
    pass

class PDFProcessingError(Exception):
    """Exception raised when PDF processing fails"""
    pass

def check_pdf_password_protection(file_content: bytes) -> bool:
    """
    Check if a PDF file is password protected.
    
    Args:
        file_content (bytes): PDF file content as bytes
    
    Returns:
        bool: True if PDF is password protected, False otherwise
    """
    try:
        pdf_reader = PyPDF2.PdfReader(BytesIO(file_content))
        return pdf_reader.is_encrypted
    except Exception as e:
        # If PyPDF2 fails to read, assume it's not password protected
        return False

def unlock_pdf_with_password(file_content: bytes, password: str) -> bytes:
    """
    Unlock a password-protected PDF and return the unlocked content.
    
    Args:
        file_content (bytes): Original PDF file content
        password (str): Password to unlock the PDF
    
    Returns:
        bytes: Unlocked PDF content
    
    Raises:
        PDFPasswordError: If password is incorrect
        PDFProcessingError: If PDF processing fails
    """
    try:
        pdf_reader = PyPDF2.PdfReader(BytesIO(file_content))
        if pdf_reader.is_encrypted:
            if pdf_reader.decrypt(password):
                # Create a new PDF writer
                pdf_writer = PyPDF2.PdfWriter()
                
                # Add all pages from the decrypted reader
                for page in pdf_reader.pages:
                    pdf_writer.add_page(page)
                
                # Write to bytes buffer
                output_buffer = BytesIO()
                pdf_writer.write(output_buffer)
                output_buffer.seek(0)
                
                return output_buffer.getvalue()
            else:
                raise PDFPasswordError("Incorrect password provided")
        else:
            # PDF is not encrypted, return original content
            return file_content
            
    except PDFPasswordError:
        raise
    except Exception as e:
        raise PDFProcessingError(f"Failed to unlock PDF: {str(e)}")

def validate_pdf_file(file_content: bytes) -> Tuple[bool, Optional[str]]:
    """
    Validate PDF file and check if it's password protected.
    
    Args:
        file_content (bytes): PDF file content
    
    Returns:
        Tuple[bool, Optional[str]]: (is_valid, error_message)
    """
    try:
        # Check if it's a valid PDF
        pdf_reader = PyPDF2.PdfReader(BytesIO(file_content))
        
        # Check if it's password protected
        if pdf_reader.is_encrypted:
            return False, "PDF is password protected. Please provide the password."
        
        # Check if PDF has content
        if len(pdf_reader.pages) == 0:
            return False, "PDF appears to be empty or corrupted."
        
        return True, None
        
    except Exception as e:
        return False, f"Invalid PDF file: {str(e)}"

def process_pdf_file(file_content: bytes, password: Optional[str] = None) -> bytes:
    """
    Process PDF file, handling password protection if needed.
    
    Args:
        file_content (bytes): Original PDF file content
        password (Optional[str]): Password if PDF is protected
    
    Returns:
        bytes: Processed PDF content ready for analysis
    
    Raises:
        PDFPasswordError: If password is required but not provided or incorrect
        PDFProcessingError: If PDF processing fails
    """
    try:
        # Check if PDF is password protected
        if check_pdf_password_protection(file_content):
            if password is None:
                raise PDFPasswordError("PDF is password protected. Please provide a password.")
            
            # Unlock the PDF with the provided password
            return unlock_pdf_with_password(file_content, password)
        else:
            # PDF is not password protected, validate and return
            is_valid, error_message = validate_pdf_file(file_content)
            if not is_valid:
                raise PDFProcessingError(error_message)
            
            return file_content
            
    except (PDFPasswordError, PDFProcessingError):
        raise
    except Exception as e:
        raise PDFProcessingError(f"Failed to process PDF: {str(e)}") 