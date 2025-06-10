from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse
from typing import Dict, List
import boto3
from openai import OpenAI
import os
from dotenv import load_dotenv
import json
from pathlib import Path
import time
from botocore.exceptions import ClientError
from datetime import datetime

# Import custom modules
from exceptions import S3UploadError, TextractError, http_exception_handler, general_exception_handler
from prompts import get_analysis_prompt, get_extraction_prompt, get_categorization_prompt
from analysis import generate_transaction_breakdown

# Load environment variables
load_dotenv()

# Initialize FastAPI app
app = FastAPI(
    title="Bank Statement Analyzer",
    description="API for analyzing bank statements using AWS Textract and GPT",
    version="1.0.0"
)

# Register exception handlers
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(Exception, general_exception_handler)

# AWS Configuration
AWS_REGION = os.getenv('AWS_REGION', 'ap-south-1')
AWS_BUCKET_NAME = os.getenv('AWS_BUCKET_NAME')

# Initialize S3 client
s3_client = boto3.client(
    's3',
    aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
    region_name=AWS_REGION
)

# Initialize Textract client
textract_client = boto3.client(
    'textract',
    aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
    region_name=AWS_REGION
)

# Initialize OpenAI client
openai_client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

# Upload file to S3 bucket using boto3 client and return S3 URI
async def upload_fileobj_to_s3(file: UploadFile, bucket_name: str, s3_key: str) -> str:
    """
    Upload a file object directly to S3 bucket
    
    Args:
        file (UploadFile): FastAPI UploadFile object
        bucket_name (str): S3 bucket name
        s3_key (str): S3 object key
    
    Returns:
        str: S3 URI of uploaded file
    
    Raises:
        S3UploadError: If upload fails
    """
    try:
        await file.seek(0)  # Reset file pointer to beginning
        s3_client.upload_fileobj(file.file, bucket_name, s3_key)
        return f"s3://{bucket_name}/{s3_key}"
    except ClientError as e:
        raise S3UploadError(f"Failed to upload file to S3: {str(e)}")
    except Exception as e:
        raise S3UploadError(f"Unexpected error during S3 upload: {str(e)}")

# Process Textract job and extract table data
def process_textract_job(job_id: str) -> Dict:
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

# Extract tables from PDF using Amazon Textract and upload to S3 bucket
async def extract_tables_from_pdf(file: UploadFile) -> Dict:
    """
    Extract tables from PDF using Amazon Textract
    
    Args:
        file (UploadFile): FastAPI UploadFile object
    
    Returns:
        Dict: Dictionary containing extracted table data
    """
    try:
        # Upload file to S3
        s3_key = f"uploads/{file.filename}"
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
        try:
            s3_client.delete_object(Bucket=AWS_BUCKET_NAME, Key=s3_key)
        except:
            pass

# Analyze table structure
async def analyze_table_structure(tables: Dict[str, List[List[str]]]) -> Dict:
    """
    Analyze the first few tables to identify transaction patterns and table structure
    
    Args:
        tables (Dict[str, List[List[str]]]): Dictionary of extracted tables
    
    Returns:
        Dict: Analysis results including headers and example transactions
    """
    # Sort and take first 4 tables
    table_keys = sorted(tables.keys(), key=lambda x: int(x.split()[1]))
    chunk_tables = table_keys[:4]
    combined_text = ""
    retry_count = 0
    max_retries = 3

    print("   - Analyzing first 4 tables for structure...")
    # Format tables for prompt
    for table_key in chunk_tables:
        combined_text += f"\n {table_key}\n"
        for row in tables[table_key]:
            combined_text += f"[{' | '.join(str(cell) for cell in row)}]" + "\n"

    while retry_count < max_retries:
        try:
            print(f"   - Sending to GPT for analysis (attempt {retry_count + 1}/{max_retries})...")
            response = openai_client.chat.completions.create(
                model='gpt-4.1-nano',
                messages=[
                    {
                        "role": "system", 
                        "content": "You are a financial data analysis expert. Extract headers and example transactions from bank statements. Return only valid JSON."
                    },
                    {"role": "user", "content": get_analysis_prompt(combined_text)}
                ],
                response_format={ "type": "json_object" }
            )
            
            analysis_result = json.loads(response.choices[0].message.content)
            
            # Validate the response structure
            required_fields = ['available_header', 'example_transactions', 'column_types']
            if not all(field in analysis_result for field in required_fields):
                raise ValueError("Missing required fields in analysis result")
                
            print("      ✓ Successfully analyzed table structure")
            return analysis_result
            
        except json.JSONDecodeError as e:
            print(f"      - Warning: Invalid JSON response: {str(e)}")
            retry_count += 1
        except ValueError as e:
            print(f"      - Warning: Validation error: {str(e)}")
            retry_count += 1
        except Exception as e:
            print(f"      - Warning: Error during analysis: {str(e)}")
            retry_count += 1
        
        if retry_count < max_retries:
            print(f"      - Retrying analysis (attempt {retry_count + 1}/{max_retries})...")
        else:
            print(f"      ! Failed to analyze table structure after {max_retries} attempts")
            raise Exception("Failed to analyze table structure after maximum retries")

# Extract transactions from tables using the context from analyze_table_structure
async def extract_transactions(tables: Dict[str, List[List[str]]], context: Dict) -> List[Dict]:
    """
    Extract transactions from tables using the context from analyze_table_structure.
    Processes tables in chunks to handle large statements efficiently.
    
    Args:
        tables (Dict[str, List[List[str]]]): Dictionary of extracted tables
        context (Dict): Context from analyze_table_structure containing headers and example format
    
    Returns:
        List[Dict]: List of all extracted transactions
    """
    try:
        # Sort tables by their number
        table_keys = sorted(tables.keys(), key=lambda x: int(x.split()[1]))
        chunk_size = 2  # Process 2 tables at a time
        final_transactions = []  # List to hold all merged transactions
        max_retries = 3

        # Create logs directory if it doesn't exist
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        
        # Create a new log file for this extraction run
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = log_dir / f"extraction_log_{timestamp}.json"
        extraction_logs = []

        # Get context information
        headers = context['available_header']
        example_transactions = context['example_transactions']
        column_types = context['column_types']

        print(f"   - Processing {len(table_keys)} tables in chunks of 2...")

        # Create text context from example transactions
        text_context = f"""
        Based on the analyzed tables, here's the transaction format:
        1. Headers: {json.dumps(headers)}
        2. Example Transaction:
           {json.dumps(example_transactions[0], indent=2)}
        3. Column Mapping: {json.dumps(column_types, indent=2)}
        """

        # Process tables in chunks
        for i in range(0, len(table_keys), chunk_size):
            chunk_tables = table_keys[i:i+chunk_size]
            chunk_num = i // chunk_size + 1
            print(f"   - Processing tables {i+1}-{min(i+chunk_size, len(table_keys))}...")
            combined_text = ""
            retry_count = 0

            # Format tables in the chunk
            for table_key in chunk_tables:
                combined_text += f"\n Table {table_key}\n"
                for row in tables[table_key]:
                    combined_text += f"[{' | '.join(str(cell) for cell in row)}]" + "\n"

            while retry_count < max_retries:
                try:
                    print(f"      - Extracting transactions (attempt {retry_count + 1}/{max_retries})...")
                    extraction_prompt = get_extraction_prompt(text_context, combined_text)

                    response = openai_client.chat.completions.create(
                        model='gpt-4.1-nano',
                        messages=[
                            {
                                "role": "system", 
                                "content": "You are a financial data extraction expert. Extract transactions exactly matching the example format. Return only valid JSON array."
                            },
                            {"role": "user", "content": extraction_prompt}
                        ],
                        response_format={ "type": "json_object" },
                        temperature=0.0  # Use deterministic output
                    )

                    chunk_transactions = json.loads(response.choices[0].message.content)
                    
                    # Validate response format and structure
                    if isinstance(chunk_transactions, dict) and 'transactions' in chunk_transactions:
                        transactions_list = chunk_transactions['transactions']
                        if isinstance(transactions_list, list):
                            # Validate each transaction has required fields
                            for tx in transactions_list:
                                required_fields = ['date', 'description', 'debit', 'credit', 'balance']
                                if not all(field in tx for field in required_fields):
                                    raise ValueError("Missing required fields in transaction")
                            
                            final_transactions.extend(transactions_list)
                            # Log successful extraction
                            log_entry = {
                                "chunk_num": chunk_num,
                                "attempt": retry_count + 1,
                                "tables": chunk_tables,
                                "prompt": extraction_prompt,
                                "response": response.choices[0].message.content,
                                "status": "success",
                                "transactions_found": len(transactions_list)
                            }
                            extraction_logs.append(log_entry)
                            print(f"      ✓ Found {len(transactions_list)} transactions")
                            break  # Success, exit retry loop
                        else:
                            raise ValueError(f"Invalid transactions format in chunk {chunk_num}")
                    elif isinstance(chunk_transactions, list):
                        # Validate each transaction has required fields
                        for tx in chunk_transactions:
                            required_fields = ['date', 'description', 'debit', 'credit', 'balance']
                            if not all(field in tx for field in required_fields):
                                raise ValueError("Missing required fields in transaction")
                        
                        final_transactions.extend(chunk_transactions)
                        # Log successful extraction
                        log_entry = {
                            "chunk_num": chunk_num,
                            "attempt": retry_count + 1,
                            "tables": chunk_tables,
                            "prompt": extraction_prompt,
                            "response": response.choices[0].message.content,
                            "status": "success",
                            "transactions_found": len(chunk_transactions)
                        }
                        extraction_logs.append(log_entry)
                        print(f"      ✓ Found {len(chunk_transactions)} transactions")
                        break  # Success, exit retry loop
                    else:
                        raise ValueError(f"Invalid response format for chunk {chunk_num}")

                except json.JSONDecodeError as e:
                    error_msg = f"Invalid JSON response in chunk {chunk_num}: {str(e)}"
                    print(f"      - Warning: {error_msg}")
                    log_entry = {
                        "chunk_num": chunk_num,
                        "attempt": retry_count + 1,
                        "tables": chunk_tables,
                        "prompt": extraction_prompt,
                        "response": response.choices[0].message.content if 'response' in locals() else None,
                        "status": "error",
                        "error": error_msg
                    }
                    extraction_logs.append(log_entry)
                    retry_count += 1
                except ValueError as e:
                    error_msg = f"Validation error in chunk {chunk_num}: {str(e)}"
                    print(f"      - Warning: {error_msg}")
                    log_entry = {
                        "chunk_num": chunk_num,
                        "attempt": retry_count + 1,
                        "tables": chunk_tables,
                        "prompt": extraction_prompt,
                        "response": response.choices[0].message.content if 'response' in locals() else None,
                        "status": "error",
                        "error": error_msg
                    }
                    extraction_logs.append(log_entry)
                    retry_count += 1
                except Exception as e:
                    error_msg = f"Error processing chunk {chunk_num}: {str(e)}"
                    print(f"      - Warning: {error_msg}")
                    log_entry = {
                        "chunk_num": chunk_num,
                        "attempt": retry_count + 1,
                        "tables": chunk_tables,
                        "prompt": extraction_prompt,
                        "response": response.choices[0].message.content if 'response' in locals() else None,
                        "status": "error",
                        "error": error_msg
                    }
                    extraction_logs.append(log_entry)
                    retry_count += 1
                
                if retry_count < max_retries:
                    print(f"      - Retrying chunk {chunk_num} (attempt {retry_count + 1}/{max_retries})...")
                else:
                    print(f"      ! Failed to process chunk {chunk_num} after {max_retries} attempts")
                    # Skip this chunk and continue with the next one
                    print(f"      - Skipping chunk {chunk_num} and continuing...")

        print(f"\n   ℹ Found total {len(extraction_logs)} log entries")
        
        # Save all logs to file
        with open(log_file, 'w', encoding='utf-8') as f:
            json.dump({
                "timestamp": timestamp,
                "total_chunks": len(table_keys) // chunk_size + (1 if len(table_keys) % chunk_size else 0),
                "total_transactions": len(final_transactions),
                "logs": extraction_logs
            }, f, indent=2, ensure_ascii=False)
        print(f"   ℹ Extraction logs saved to: {log_file}")

        if not final_transactions:
            raise Exception("No transactions were successfully extracted")

        return final_transactions

    except Exception as e:
        raise Exception(f"Failed to extract transactions: {str(e)}")

# Categorize transactions
async def categorize_transactions(transactions: List[Dict]) -> List[Dict]:
    """
    Categorize transactions using GPT.
    Process transactions in chunks to handle large volumes efficiently.
    
    Args:
        transactions (List[Dict]): List of transactions to categorize
    
    Returns:
        List[Dict]: List of categorized transactions
    """
    try:
        chunk_size = 40  # Process 40 transactions at a time
        categorized_transactions = []
        max_retries = 3

        # Create logs directory if it doesn't exist
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        
        # Create a new log file for this categorization run
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = log_dir / f"categorization_log_{timestamp}.json"
        categorization_logs = []

        # Process transactions in chunks
        total_chunks = (len(transactions) + chunk_size - 1) // chunk_size
        for i in range(0, len(transactions), chunk_size):
            chunk = transactions[i:i + chunk_size]
            chunk_num = i // chunk_size + 1
            print(f"   - Processing chunk {chunk_num}/{total_chunks} ({len(chunk)} transactions)...")
            
            retry_count = 0
            while retry_count < max_retries:
                try:
                    categorization_prompt = get_categorization_prompt(chunk)

                    response = openai_client.chat.completions.create(
                        model='gpt-4.1-nano',
                        messages=[
                            {
                                "role": "system", 
                                "content": "You are a financial transaction categorization expert. Categorize transactions based on their description, amount, and patterns."
                            },
                            {"role": "user", "content": categorization_prompt}
                        ],
                        response_format={ "type": "json_object" },
                        temperature=0.0  # Use deterministic output
                    )

                    result = json.loads(response.choices[0].message.content)
                    
                    # Validate response format
                    if not isinstance(result, dict) or 'transactions' not in result:
                        raise ValueError("Invalid response format")
                    
                    chunk_transactions = result['transactions']
                    
                    # Validate each transaction has required fields
                    for tx in chunk_transactions:
                        required_fields = ['date', 'description', 'debit', 'credit', 'balance', 'category']
                        if not all(field in tx for field in required_fields):
                            raise ValueError("Missing required fields in transaction")
                        
                        # Validate category format
                        category = tx['category']
                        if not isinstance(category, str) or '.' not in category:
                            raise ValueError(f"Invalid category format: {category}")
                        
                        category_type, subcategory = category.split('.')
                        valid_types = ['income', 'expense', 'transfer']
                        if category_type not in valid_types:
                            raise ValueError(f"Invalid category type: {category_type}")
                    
                    categorized_transactions.extend(chunk_transactions)
                    
                    # Log successful categorization
                    log_entry = {
                        "chunk_num": chunk_num,
                        "attempt": retry_count + 1,
                        "transactions_count": len(chunk),
                        "prompt": categorization_prompt,
                        "response": response.choices[0].message.content,
                        "status": "success",
                        "categories_found": {
                            tx['category']: sum(1 for t in chunk_transactions if t['category'] == tx['category'])
                            for tx in chunk_transactions
                        }
                    }
                    categorization_logs.append(log_entry)
                    print(f"      ✓ Successfully categorized {len(chunk_transactions)} transactions")
                    break  # Success, exit retry loop
                
                except json.JSONDecodeError as e:
                    error_msg = f"Invalid JSON response in chunk {chunk_num}: {str(e)}"
                    print(f"      - Warning: {error_msg}")
                    log_entry = {
                        "chunk_num": chunk_num,
                        "attempt": retry_count + 1,
                        "transactions_count": len(chunk),
                        "prompt": categorization_prompt,
                        "response": response.choices[0].message.content if 'response' in locals() else None,
                        "status": "error",
                        "error": error_msg
                    }
                    categorization_logs.append(log_entry)
                    retry_count += 1
                except ValueError as e:
                    error_msg = f"Validation error in chunk {chunk_num}: {str(e)}"
                    print(f"      - Warning: {error_msg}")
                    log_entry = {
                        "chunk_num": chunk_num,
                        "attempt": retry_count + 1,
                        "transactions_count": len(chunk),
                        "prompt": categorization_prompt,
                        "response": response.choices[0].message.content if 'response' in locals() else None,
                        "status": "error",
                        "error": error_msg
                    }
                    categorization_logs.append(log_entry)
                    retry_count += 1
                except Exception as e:
                    error_msg = f"Error processing chunk {chunk_num}: {str(e)}"
                    print(f"      - Warning: {error_msg}")
                    log_entry = {
                        "chunk_num": chunk_num,
                        "attempt": retry_count + 1,
                        "transactions_count": len(chunk),
                        "prompt": categorization_prompt,
                        "response": response.choices[0].message.content if 'response' in locals() else None,
                        "status": "error",
                        "error": error_msg
                    }
                    categorization_logs.append(log_entry)
                    retry_count += 1
                
                if retry_count < max_retries:
                    print(f"      - Retrying chunk {chunk_num} (attempt {retry_count + 1}/{max_retries})...")
                else:
                    print(f"      ! Failed to process chunk {chunk_num} after {max_retries} attempts")
                    # Add original transactions with default category
                    for transaction in chunk:
                        transaction['category'] = 'expense.others'  # Default category
                        categorized_transactions.append(transaction)
                    print(f"      - Applied default category to {len(chunk)} transactions")

        print(f"\n   ℹ Found total {len(categorization_logs)} log entries")
        
        # Save all logs to file
        with open(log_file, 'w', encoding='utf-8') as f:
            json.dump({
                "timestamp": timestamp,
                "total_chunks": total_chunks,
                "total_transactions": len(transactions),
                "successfully_categorized": len(categorized_transactions),
                "category_distribution": {
                    tx['category']: sum(1 for t in categorized_transactions if t['category'] == tx['category'])
                    for tx in categorized_transactions
                },
                "logs": categorization_logs
            }, f, indent=2, ensure_ascii=False)
        print(f"   ℹ Categorization logs saved to: {log_file}")

        if not categorized_transactions:
            raise Exception("No transactions were successfully categorized")

        return categorized_transactions

    except Exception as e:
        raise Exception(f"Failed to categorize transactions: {str(e)}")

# Home endpoint
@app.get("/")
async def home() -> JSONResponse:
    """
    Root endpoint that provides API information and available endpoints.
    Returns:
        JSONResponse: API information and available endpoints
    """
    return JSONResponse(
        content={
            "status": "success",
            "data": {
                "api_status": "online",
                "message": "Welcome to Bank Statement Analyzer API",
                "endpoints": {
                    "home": "GET /",
                    "analyze_statement": "POST /api/analyze-statement",
                    "docs": "GET /docs",
                    "redoc": "GET /redoc"
                }
            }
        },
        status_code=200
    )

# Analyze statement endpoint
@app.post("/api/analyze-statement")
async def analyze_statement(file: UploadFile = File(...)) -> JSONResponse:
    """
    Analyze a bank statement PDF and extract tables.
    """
    if not file.filename.lower().endswith('.pdf'):
        return JSONResponse(
            content={ "status": "error", "message": "Only PDF files are allowed", "data": None },
            status_code=400
        )
    
    try:
        print("\n=== Starting Bank Statement Analysis ===")
        print(f"Processing file: {file.filename}")
        
        # Extract tables using Textract
        print("\n1. Extracting Tables from PDF...")
        print("   - Uploading to S3...")
        tables = await extract_tables_from_pdf(file)
        print(f"   ✓ Successfully extracted {len(tables)} tables")
        
        # Analyze table structure using GPT
        print("\n2. Analyzing Table Structure...")
        table_analysis = await analyze_table_structure(tables)
        print("   ✓ Table structure analysis complete")
        print(f"   - Found {len(table_analysis['available_header'])} columns")
        
        # Extract transactions using the analysis context
        print("\n3. Extracting Transactions...")
        transactions = await extract_transactions(tables, table_analysis)
        print(f"   ✓ Successfully extracted {len(transactions)} transactions")
        
        # Categorize transactions
        print("\n4. Categorizing Transactions...")
        print(f"   - Processing in chunks of 40 transactions")
        categorized_transactions = await categorize_transactions(transactions)
        print(f"   ✓ Successfully categorized {len(categorized_transactions)} transactions")
        
        # Generate transaction breakdown
        print("\n5. Generating Transaction Analysis...")
        transaction_analysis = generate_transaction_breakdown(categorized_transactions)
        print("   ✓ Analysis complete")
        
        print("\n=== Analysis Complete ===\n")
        
        return JSONResponse(
            content={
                "status": "success",
                "message": f"Successfully analyzed {len(categorized_transactions)} transactions",
                "data": { 
                    "analysis": transaction_analysis
                }
            },
            status_code=200
        )
        
    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
        return JSONResponse(content={"status": "error","message": str(e),"data": None}, status_code=500)

# Run the app
if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv('APP_PORT')))
