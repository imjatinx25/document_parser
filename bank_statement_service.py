# from aws_service import extract_tables_from_pdf
from gpt_service import analyze_table_structure, extract_transactions, categorize_transactions
from aws_service import extract_tables_from_pdf
from analysis import generate_transaction_breakdown, calculate_median_summary, calculate_monthly_breakdown,calculate_monthly_summary
import pandas as pd
# from analysis import generate_transaction_breakdown

# async def process_bank_statement(file_bytes: bytes) -> dict:
#     # Step 1: Extract tables from PDF using AWS Textract
#     tables = await extract_tables_from_pdf(file_bytes)

#     if not tables:
#         return {"error": "No tables found in the provided PDF."}

#     # Step 2: Analyze the structure of the extracted tables
#     table_metadata = await analyze_table_structure(tables)

#     # Step 3: Extract transactions based on the analyzed table structure
#     transactions = await extract_transactions(tables, table_metadata)

#     # Step 4: Categorize the transactions
#     categorized_transactions = await categorize_transactions(transactions)

#     # Step 5: Generate transaction breakdown or summary
#     transaction_breakdown = generate_transaction_breakdown(categorized_transactions)

#     # Return the comprehensive processed data
#     return {
#         "transactions": categorized_transactions,
#         "breakdown": transaction_breakdown,
#         "metadata": table_metadata
#     }


from io import BytesIO
from progress_manager import progress_manager


async def process_bank_statement(file_bytes, task_id=None):
    await progress_manager.update_progress(task_id, 10, "Started Textract processing...")

    tables = await extract_tables_from_pdf(file_bytes)
    await progress_manager.update_progress(task_id, 40, "Completed Textract.", {"tables_extracted": len(tables)})

    metadata = await analyze_table_structure(tables)
    await progress_manager.update_progress(task_id, 60, "Analyzed table structure", {"headers": metadata.get('available_header', [])})

    transactions = await extract_transactions(tables, metadata)
    await progress_manager.update_progress(task_id, 80, "Extracted transactions", {"transactions_count": len(transactions)})

    categorized = await categorize_transactions(transactions)
    await progress_manager.update_progress(task_id, 90, "Categorization completed", {"categorized_count": len(categorized)})

    # ✅ Generate Summaries
    summary = generate_transaction_breakdown(categorized)
    monthly_breakdown = calculate_monthly_breakdown(pd.DataFrame(categorized))
    median_summary = calculate_median_summary(monthly_breakdown)

    final_data = {
        "transactions": categorized,
        "summary": summary,
        # "monthly_breakdown": monthly_breakdown,
        # "median_summary": median_summary
    }

    # await progress_manager.update_progress(task_id, 100, "Completed all processing", {"summary_generated": True})
    await progress_manager.update_progress(
    task_id,
    progress=100,
    message="Completed all processing",
    data=final_data
        )


    return final_data

