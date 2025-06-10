import json

def get_analysis_prompt(combined_text: str) -> str:
    return f"""
    The following text contains extracted tables from a bank statement.

    Your task is to **dynamically** extract the **headers** from the tables and identify the first **5 transactions** from the provided tables. Ensure that you align each transaction with the correct header columns.

    Important Notes:
    1. Carefully check the **transaction columns** and ensure they are correctly synced with the header.
    2. This output will be used as a **context for the next GPT prompt** to understand the format and extract transactions from similar text.
    3. Ensure that each **transaction row** is **aligned** with its corresponding header columns.
    4. Mark the extracted headers as **"Available Header"** and the transactions as **"Example Transactions Format"** in the text.
    5. Return the response in JSON format.

    Expected JSON Format:
    {{
        "available_header": ["column1", "column2", ...],
        "example_transactions": [
            ["value1", "value2", ...],
            ["value1", "value2", ...],
            ...
        ],
        "column_types": {{
            "date_column": index,
            "description_column": index,
            "debit_column": index,
            "credit_column": index,
            "balance_column": index
        }}
    }}

    ### Here are the tables:
    {combined_text}
    """

def get_extraction_prompt(text_context: str, combined_text: str) -> str:
    return f"""
    The following text contains extracted tables from a bank statement.

    Your task is to process the tables and extract the relevant **transactions**. Here are the guidelines for identifying and extracting the data:

    ### {text_context}

    ### **Your Task**:
    1. **Extract Transaction Data**:
       - For each table, identify the rows corresponding to **financial transactions**.
       - Each **transaction row** should contain:
         - **"date"**: Keep the date in the original format as shown in examples.
         - **"description"**: The exact description as it appears in the table.
         - **"debit"**: Amount from debit column (set to **0.0** if not applicable).
         - **"credit"**: Amount from credit column (set to **0.0** if not applicable).
         - **"balance"**: The balance after the transaction.

    2. **Transaction Extraction Rules**:
       - Match the format of example transactions exactly
       - Only extract rows that follow the same pattern as examples
       - Set debit or credit to 0.0 if empty
       - Ensure data aligns with the correct columns

    3. **Handle Non-Transactional Tables**:
       - If a table contains non-transactional data (account info, summary, etc.), return empty array
       - Skip header rows and summary rows

    4. **Response Format**:
       Return a JSON object in this EXACT format:
       {{
           "transactions": [
               {{
                   "date": "DD-MM-YYYY",
                   "description": "Transaction description",
                   "debit": 0.0,
                   "credit": 100.0,
                   "balance": 1000.0
               }},
               ...
           ]
       }}

    ### Tables to process:
    {combined_text}
    """

def get_categorization_prompt(transactions: list) -> str:
    return f"""
    You are a financial transaction analyzer. Your job is to categorize each transaction into a valid financial category based on the transaction details provided.

    ### Valid Categories (Case-Sensitive):

    **Income:**
    - income.salary
    - income.interest
    - income.business
    - income.refund
    - income.others

    **Expense:**
    - expense.food
    - expense.rent
    - expense.utilities
    - expense.shopping
    - expense.travel
    - expense.entertainment
    - expense.healthcare
    - expense.insurance
    - expense.loan_emi
    - expense.others

    **Transfers:**
    - transfer.self_transfer
    - transfer.external_transfer

    ### Rules for Categorization:
    1. Use the **description**, **amount**, and **transaction type** (credit or debit) to accurately assign a category from the list above.
    2. Use these indicators:
       - Recurring credits of large amounts (>₹30,000) early each month may indicate `income.salary`
       - Regular debits of ₹5,000-₹15,000 might suggest `expense.loan_emi` or `expense.rent`
       - Food delivery services, restaurants → expense.food
       - Shopping platforms, retail stores → expense.shopping
       - Movie tickets, entertainment services → expense.entertainment
       - Hospital, pharmacy, medical → expense.healthcare
       - Insurance premiums → expense.insurance
    3. Look for patterns: similar amounts and dates suggest recurring categories
    4. For vague or ambiguous descriptions (e.g., UPI/NEFT), use the **amount**, **frequency**, and **context**
    5. Do not invent any new category names — only use the ones provided exactly as written
    6. For transfers between own accounts or to other people, use appropriate transfer category

    Return a JSON object with the following structure:
    {{
        "transactions": [
            {{
                "date": "YYYY-MM-DD",
                "description": "Transaction Description",
                "debit": number (use 0.0 if no debit),
                "credit": number (use 0.0 if no credit),
                "balance": number,
                "category": "exact.subcategory"
            }},
            ...
        ]
    }}

    Here are the transactions to categorize:
    {json.dumps(transactions, indent=2)}
    """ 