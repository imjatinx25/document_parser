from openai import AsyncOpenAI
import os
import json
from typing import Dict, List
from dotenv import load_dotenv
from prompts import get_analysis_prompt, get_extraction_prompt, get_categorization_prompt
from gpt_client import run_gpt
import asyncio
import time
from dotenv import load_dotenv
load_dotenv()

# Validate OpenAI API key
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')


if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY environment variable is required")

DEFAULT_CHUNK_SIZE = 5  # Default if dynamic calculation is skipped


def calculate_dynamic_chunk_size(total_items, average_table_length=0):
    """
    Determine chunk size dynamically based on total items and average table length.

    Args:
        total_items (int): Total number of tables.
        average_table_length (int): Average number of rows per table.

    Returns:
        int: Chunk size
    """
    if average_table_length >= 50:
        return 2
    elif average_table_length >= 20:
        return 5
    elif total_items <= 20:
        return 5
    elif total_items <= 50:
        return 10
    else:
        return 15



# Initialize OpenAI client
openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)

async def analyze_table_structure(tables: Dict[str, List[List[str]]]) -> Dict:
    """
    Analyze the structure of extracted tables to understand headers and format.
    
    Args:
        tables (Dict[str, List[List[str]]]): Dictionary of extracted tables
    
    Returns:
        Dict: Analysis result containing headers, example transactions, and column mapping
    """
    try:
        # Check if tables are empty
        if not tables:
            raise Exception("No tables found in the PDF")
        
        # Check if any table has data
        has_data = False
        for table_data in tables.values():
            if table_data and len(table_data) > 0:
                has_data = True
                break
        
        if not has_data:
            raise Exception("No data found in the extracted tables")
        
        # Combine all tables into a single text for analysis
        combined_text = ""
        for table_key, table_data in tables.items():
            combined_text += f"\n Table {table_key}\n"
            for row in table_data:
                combined_text += f"[{' | '.join(str(cell) for cell in row)}]" + "\n"

        print("   - Analyzing table structure...")
        max_retries = 3
        retry_count = 0

        while retry_count < max_retries:
            try:
                analysis_prompt = get_analysis_prompt(combined_text)

                response = await openai_client.chat.completions.create(
                    model='gpt-4.1-nano',
                    messages=[
                        {
                            "role": "system", 
                            "content": "You are a financial data analysis expert. Analyze table structure and extract headers and example transactions."
                        },
                        {"role": "user", "content": analysis_prompt}
                    ],
                    response_format={ "type": "json_object" },
                    temperature=0.0  # Use deterministic output
                )

                result = json.loads(response.choices[0].message.content)
                
                # Validate response structure
                required_fields = ['available_header', 'example_transactions', 'column_types']
                if not all(field in result for field in required_fields):
                    raise ValueError("Missing required fields in analysis response")
                
                if not result['example_transactions']:
                    raise ValueError("No example transactions found")
                
                print(f"   ✓ Found {len(result['available_header'])} headers and {len(result['example_transactions'])} example transactions")
                return result

            except json.JSONDecodeError as e:
                error_msg = f"Invalid JSON response: {str(e)}"
                print(f"   - Warning: {error_msg}")
                retry_count += 1
            except ValueError as e:
                error_msg = f"Validation error: {str(e)}"
                print(f"   - Warning: {error_msg}")
                retry_count += 1
            except Exception as e:
                error_msg = f"Error analyzing table structure: {str(e)}"
                print(f"   - Warning: {error_msg}")
                retry_count += 1
            
            if retry_count < max_retries:
                print(f"   - Retrying analysis (attempt {retry_count + 1}/{max_retries})...")
            else:
                print(f"   ! Failed to analyze table structure after {max_retries} attempts")
                raise Exception("Failed to analyze table structure after maximum retries")

    except Exception as e:
        raise Exception(f"Failed to analyze table structure: {str(e)}")

async def process_chunk_async(chunk_tables: List[str], tables: Dict[str, List[List[str]]], text_context: str, chunk_num: int, max_retries: int = 3) -> List[Dict]:
    """
    Process a single chunk of tables asynchronously.
    
    Args:
        chunk_tables: List of table keys in this chunk
        tables: Dictionary of all tables
        text_context: Context information for extraction
        chunk_num: Chunk number for logging
        max_retries: Maximum number of retry attempts
    
    Returns:
        List[Dict]: List of transactions extracted from this chunk
    """
    start_time = time.time()
    print(f"   🚀 [CHUNK {chunk_num}] Starting parallel processing (tables: {', '.join(chunk_tables)})...")
    combined_text = ""
    retry_count = 0

    # Format tables in the chunk
    for table_key in chunk_tables:
        combined_text += f"\n Table {table_key}\n"
        for row in tables[table_key]:
            combined_text += f"[{' | '.join(str(cell) for cell in row)}]" + "\n"

    while retry_count < max_retries:
        try:
            print(f"      📡 [CHUNK {chunk_num}] Sending to GPT API (attempt {retry_count + 1}/{max_retries})...")
            extraction_prompt = get_extraction_prompt(text_context, combined_text)

            response = await openai_client.chat.completions.create(
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
                    
                    elapsed = time.time() - start_time
                    print(f"      ✅ [CHUNK {chunk_num}] Completed in {elapsed:.1f}s - Found {len(transactions_list)} transactions")
                    return transactions_list
                else:
                    raise ValueError(f"Invalid transactions format in chunk {chunk_num}")
            elif isinstance(chunk_transactions, list):
                # Validate each transaction has required fields
                for tx in chunk_transactions:
                    required_fields = ['date', 'description', 'debit', 'credit', 'balance']
                    if not all(field in tx for field in required_fields):
                        raise ValueError("Missing required fields in transaction")
                
                elapsed = time.time() - start_time
                print(f"      ✅ [CHUNK {chunk_num}] Completed in {elapsed:.1f}s - Found {len(chunk_transactions)} transactions")
                return chunk_transactions
            else:
                raise ValueError(f"Invalid response format for chunk {chunk_num}")

        except json.JSONDecodeError as e:
            error_msg = f"Invalid JSON response in chunk {chunk_num}: {str(e)}"
            print(f"      ⚠️ [CHUNK {chunk_num}] Warning: {error_msg}")
            retry_count += 1
        except ValueError as e:
            error_msg = f"Validation error in chunk {chunk_num}: {str(e)}"
            print(f"      ⚠️ [CHUNK {chunk_num}] Warning: {error_msg}")
            retry_count += 1
        except Exception as e:
            error_msg = f"Error processing chunk {chunk_num}: {str(e)}"
            print(f"      ⚠️ [CHUNK {chunk_num}] Warning: {error_msg}")
            retry_count += 1
        
        if retry_count < max_retries:
            print(f"      🔄 [CHUNK {chunk_num}] Retrying (attempt {retry_count + 1}/{max_retries})...")
        else:
            print(f"      ❌ [CHUNK {chunk_num}] Failed after {max_retries} attempts")
            # Return empty list for failed chunk
            return []

async def extract_transactions(tables: Dict[str, List[List[str]]], context: Dict) -> List[Dict]:
    """
    Extract transactions from tables using the context from analyze_table_structure.
    Processes tables in chunks using asyncio.gather for parallel processing.
    
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
        max_retries = 3

        # Get context information
        headers = context['available_header']
        example_transactions = context['example_transactions']
        column_types = context['column_types']

        print(f"   - Processing {len(table_keys)} tables in chunks of 2 using parallel processing...")

        # Create text context from example transactions
        text_context = f"""
        Based on the analyzed tables, here's the transaction format:
        1. Headers: {json.dumps(headers)}
        2. Example Transaction:
           {json.dumps(example_transactions[0], indent=2)}
        3. Column Mapping: {json.dumps(column_types, indent=2)}
        """

        # Create chunks
        chunks = []
        for i in range(0, len(table_keys), chunk_size):
            chunk_tables = table_keys[i:i+chunk_size]
            chunk_num = i // chunk_size + 1
            chunks.append((chunk_tables, chunk_num))

        # Process all chunks in parallel using asyncio.gather
        start_time = time.time()
        print(f"   🚀 Starting parallel processing of {len(chunks)} chunks at {time.strftime('%H:%M:%S')}...")
        chunk_results = await asyncio.gather(
            *[process_chunk_async(chunk_tables, tables, text_context, chunk_num, max_retries) 
              for chunk_tables, chunk_num in chunks],
            return_exceptions=True
        )

        # Combine results from all chunks
        final_transactions = []
        total_time = time.time() - start_time
        print(f"   🎉 All chunks completed in {total_time:.1f}s! Combining results...")
        
        for i, result in enumerate(chunk_results):
            if isinstance(result, Exception):
                print(f"   ❌ Chunk {i+1} failed with exception: {str(result)}")
            elif isinstance(result, list):
                final_transactions.extend(result)
                print(f"   ✅ Chunk {i+1} completed with {len(result)} transactions")
            else:
                print(f"   ❌ Chunk {i+1} returned unexpected result type: {type(result)}")

        if not final_transactions:
            raise Exception("No transactions were successfully extracted")

        print(f"   ✓ Total transactions extracted: {len(final_transactions)}")
        
        # Verify we have all transactions
        expected_total = sum(len(tables[table_key]) for table_key in table_keys)
        print(f"   - Expected transactions from {len(table_keys)} tables: ~{expected_total} (approximate)")
        print(f"   - Actual transactions extracted: {len(final_transactions)}")
        
        return final_transactions

    except Exception as e:
        raise Exception(f"Failed to extract transactions: {str(e)}")


async def process_categorization_chunk_async(chunk: List[Dict], chunk_num: int, total_chunks: int, max_retries: int = 3) -> List[Dict]:
    """
    Process a single chunk of transactions for categorization asynchronously.
    
    Args:
        chunk: List of transactions in this chunk
        chunk_num: Chunk number for logging
        total_chunks: Total number of chunks
        max_retries: Maximum number of retry attempts
    
    Returns:
        List[Dict]: List of categorized transactions from this chunk
    """
    import time
    start_time = time.time()
    print(f"   🚀 [CATEGORY CHUNK {chunk_num}/{total_chunks}] Starting categorization ({len(chunk)} transactions)...")
    retry_count = 0

    while retry_count < max_retries:
        try:
            print(f"      📡 [CATEGORY CHUNK {chunk_num}] Sending to GPT API (attempt {retry_count + 1}/{max_retries})...")
            categorization_prompt = get_categorization_prompt(chunk)

            response = await openai_client.chat.completions.create(
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
            
            elapsed = time.time() - start_time
            print(f"      ✅ [CATEGORY CHUNK {chunk_num}] Completed in {elapsed:.1f}s - Categorized {len(chunk_transactions)} transactions")
            return chunk_transactions
        
        except json.JSONDecodeError as e:
            error_msg = f"Invalid JSON response in chunk {chunk_num}: {str(e)}"
            print(f"      ⚠️ [CATEGORY CHUNK {chunk_num}] Warning: {error_msg}")
            retry_count += 1
        except ValueError as e:
            error_msg = f"Validation error in chunk {chunk_num}: {str(e)}"
            print(f"      ⚠️ [CATEGORY CHUNK {chunk_num}] Warning: {error_msg}")
            retry_count += 1
        except Exception as e:
            error_msg = f"Error processing chunk {chunk_num}: {str(e)}"
            print(f"      ⚠️ [CATEGORY CHUNK {chunk_num}] Warning: {error_msg}")
            retry_count += 1
        
        if retry_count < max_retries:
            print(f"      🔄 [CATEGORY CHUNK {chunk_num}] Retrying (attempt {retry_count + 1}/{max_retries})...")
        else:
            print(f"      ❌ [CATEGORY CHUNK {chunk_num}] Failed after {max_retries} attempts - Applying default categories")
            # Add original transactions with default category
            for transaction in chunk:
                transaction['category'] = 'expense.others'  # Default category
            return chunk

async def categorize_transactions(transactions: List[Dict]) -> List[Dict]:
    """
    Categorize transactions using GPT.
    Process transactions in chunks using asyncio.gather for parallel processing.
    
    Args:
        transactions (List[Dict]): List of transactions to categorize
    
    Returns:
        List[Dict]: List of categorized transactions
    """
    try:
        chunk_size = 40  # Process 40 transactions at a time
        max_retries = 3

        print(f"   - Input transactions count: {len(transactions)}")

        # Create chunks
        chunks = []
        total_chunks = (len(transactions) + chunk_size - 1) // chunk_size
        print(f"   - Creating {total_chunks} chunks with chunk_size={chunk_size}")
        
        for i in range(0, len(transactions), chunk_size):
            chunk = transactions[i:i + chunk_size]
            chunk_num = i // chunk_size + 1
            chunks.append((chunk, chunk_num))
            print(f"   - Chunk {chunk_num}: {len(chunk)} transactions (indices {i} to {min(i+chunk_size, len(transactions))-1})")

        # Verify total transactions in chunks
        total_in_chunks = sum(len(chunk) for chunk, _ in chunks)
        print(f"   - Total transactions in chunks: {total_in_chunks}")
        if total_in_chunks != len(transactions):
            print(f"   ⚠️ WARNING: Transaction count mismatch! Input: {len(transactions)}, Chunks: {total_in_chunks}")

        print(f"   - Processing {len(transactions)} transactions in {total_chunks} chunks using parallel categorization...")

        # Process all chunks in parallel using asyncio.gather
        start_time = time.time()
        print(f"   🚀 Starting parallel categorization of {total_chunks} chunks at {time.strftime('%H:%M:%S')}...")
        chunk_results = await asyncio.gather(
            *[process_categorization_chunk_async(chunk, chunk_num, total_chunks, max_retries) 
              for chunk, chunk_num in chunks],
            return_exceptions=True
        )

        # Combine results from all chunks
        categorized_transactions = []
        total_time = time.time() - start_time
        print(f"   🎉 All categorization chunks completed in {total_time:.1f}s! Combining results...")
        
        for i, result in enumerate(chunk_results):
            if isinstance(result, Exception):
                print(f"   ❌ Categorization chunk {i+1} failed with exception: {str(result)}")
                # Apply default categories to failed chunk
                chunk_start = i * chunk_size
                chunk_end = min(chunk_start + chunk_size, len(transactions))
                failed_chunk = transactions[chunk_start:chunk_end]
                for transaction in failed_chunk:
                    transaction['category'] = 'expense.others'
                categorized_transactions.extend(failed_chunk)
                print(f"   ✅ Applied default categories to {len(failed_chunk)} transactions from failed chunk {i+1}")
            elif isinstance(result, list):
                categorized_transactions.extend(result)
                print(f"   ✅ Categorization chunk {i+1} completed with {len(result)} transactions")
            else:
                print(f"   ❌ Categorization chunk {i+1} returned unexpected result type: {type(result)}")

        if not categorized_transactions:
            raise Exception("No transactions were successfully categorized")

        print(f"   ✓ Total transactions categorized: {len(categorized_transactions)}")
        if len(categorized_transactions) != len(transactions):
            print(f"   ⚠️ WARNING: Final count mismatch! Input: {len(transactions)}, Output: {len(categorized_transactions)}")
            print(f"   ⚠️ Missing: {len(transactions) - len(categorized_transactions)} transactions")
        
        return categorized_transactions

    except Exception as e:
        raise Exception(f"Failed to categorize transactions: {str(e)}")


