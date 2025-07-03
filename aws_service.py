import boto3
import os
from botocore.exceptions import ClientError
from fastapi import UploadFile
from io import BytesIO
import time
from exceptions import S3UploadError, TextractError

# AWS Configuration
AWS_REGION = os.getenv('AWS_REGION', 'ap-south-1')
AWS_BUCKET_NAME = os.getenv('AWS_BUCKET_NAME')
AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')

# Validate required AWS configuration
if not AWS_BUCKET_NAME:
    raise ValueError("AWS_BUCKET_NAME environment variable is required")
if not AWS_ACCESS_KEY_ID:
    raise ValueError("AWS_ACCESS_KEY_ID environment variable is required")
if not AWS_SECRET_ACCESS_KEY:
    raise ValueError("AWS_SECRET_ACCESS_KEY environment variable is required")

# Initialize S3 client
s3_client = boto3.client(
    's3',
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    region_name=AWS_REGION
)

# Initialize Textract client
textract_client = boto3.client(
    'textract',
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    region_name=AWS_REGION
)

async def upload_fileobj_to_s3(file: UploadFile | BytesIO, bucket_name: str, s3_key: str) -> str:
    """
    Upload a file object directly to S3 bucket
    
    Args:
        file (UploadFile | BytesIO): File object to upload
        bucket_name (str): S3 bucket name
        s3_key (str): S3 object key
    
    Returns:
        str: S3 URI of uploaded file
    
    Raises:
        S3UploadError: If upload fails
    """
    try:
        if isinstance(file, UploadFile):
            await file.seek(0)  # Reset file pointer to beginning
            s3_client.upload_fileobj(file.file, bucket_name, s3_key)
        else:  # BytesIO
            file.seek(0)  # Reset file pointer to beginning
            s3_client.upload_fileobj(file, bucket_name, s3_key)
        return f"s3://{bucket_name}/{s3_key}"
    except ClientError as e:
        raise S3UploadError(f"Failed to upload file to S3: {str(e)}")
    except Exception as e:
        raise S3UploadError(f"Unexpected error during S3 upload: {str(e)}")

def process_textract_job(job_id: str) -> dict:
    """
    Process Textract job and extract table data
    
    Args:
        job_id (str): Textract job ID
    
    Returns:
        Dict: Dictionary containing extracted table data
    
    Raises:
        TextractError: If job processing fails
    """
    while True:
        result = textract_client.get_document_analysis(JobId=job_id)
        status = result['JobStatus']
        if status in ['SUCCEEDED', 'FAILED']:
            break
        time.sleep(5)

    if status == 'FAILED':
        raise TextractError("Textract job failed")

    next_token = None
    all_blocks = []
    table_data_dict = {}

    # Collect all blocks from the job
    while True:
        if next_token:
            result = textract_client.get_document_analysis(JobId=job_id, NextToken=next_token)
        else:
            result = textract_client.get_document_analysis(JobId=job_id)
        all_blocks.extend(result['Blocks'])
        next_token = result.get('NextToken')
        if not next_token:
            break

    # Process blocks into tables
    block_map = {b['Id']: b for b in all_blocks}
    tables = [b for b in all_blocks if b['BlockType'] == 'TABLE']

    for table_index, table in enumerate(tables, 1):
        table_key = f"Table {table_index}"
        table_rows = []
        rows = {}
        
        for rel in table.get('Relationships', []):
            if rel['Type'] == 'CHILD':
                for cell_id in rel['Ids']:
                    cell = block_map[cell_id]
                    row_idx = cell['RowIndex']
                    col_idx = cell['ColumnIndex']
                    text = ''
                    if 'Relationships' in cell:
                        for cr in cell['Relationships']:
                            if cr['Type'] == 'CHILD':
                                text += ' '.join(block_map[word_id]['Text'] for word_id in cr['Ids'])
                    rows.setdefault(row_idx, {})[col_idx] = text
        
        for r in sorted(rows.keys()):
            row_data = [rows[r].get(c, '') for c in sorted(rows[r].keys())]
            table_rows.append(row_data)
        
        table_data_dict[table_key] = table_rows

    return table_data_dict

async def extract_tables_from_pdf(file: UploadFile | BytesIO) -> dict:
    """
    Extract tables from PDF using Amazon Textract
    
    Args:
        file (UploadFile | BytesIO): File object containing the PDF
    
    Returns:
        Dict: Dictionary containing extracted table data
    """
    s3_key = None
    try:
        # Get filename from UploadFile or use a default name for BytesIO
        filename = file.filename if isinstance(file, UploadFile) else "statement.pdf"
        
        # Upload file to S3
        s3_key = f"uploads/{filename}"
        print("   - Starting Textract job...")
        await upload_fileobj_to_s3(file, AWS_BUCKET_NAME, s3_key)
        
        # Start Textract job
        response = textract_client.start_document_analysis(
            DocumentLocation={ 'S3Object': { 'Bucket': AWS_BUCKET_NAME, 'Name': s3_key } },
            FeatureTypes=['TABLES']
        )
        
        # Process the job
        print("   - Processing Textract results...")
        table_data = process_textract_job(response['JobId'])
        
        # Clean up S3
        try:
            s3_client.delete_object(Bucket=AWS_BUCKET_NAME, Key=s3_key)
        except Exception as e:
            print(f"   - Warning: Failed to delete S3 object: {str(e)}")
        
        return table_data

    except (S3UploadError, TextractError) as e:
        raise Exception(str(e))
    except Exception as e:
        raise Exception(f"Failed to extract tables from PDF: {str(e)}")
    finally:
        # Clean up S3 in case of any errors
        if s3_key:
            try:
                s3_client.delete_object(Bucket=AWS_BUCKET_NAME, Key=s3_key)
            except:
                pass
