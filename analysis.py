from typing import List, Dict, Union, Any
from datetime import datetime
from collections import defaultdict
import statistics
import logging
from pathlib import Path
import pandas as pd

# Set up logging
log_dir = Path("logs")
log_dir.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_dir / 'analysis.log'),
        logging.StreamHandler()
    ]
)

def validate_transaction(transaction: Dict[str, Any]) -> bool:
    """Validate if a transaction has all required fields and correct data types."""
    try:
        required_fields = {
            'date': str,
            'description': str,
            'debit': (int, float),
            'credit': (int, float),
            'balance': (int, float, str),  # Some balance values might be strings
            'category': str
        }
        
        # Check all required fields exist
        if not all(field in transaction for field in required_fields):
            missing_fields = [f for f in required_fields if f not in transaction]
            logging.error(f"Missing required fields in transaction: {missing_fields}")
            return False
        
        # Check data types
        for field, expected_type in required_fields.items():
            value = transaction[field]
            if field == 'balance' and isinstance(value, str):
                # Try to convert string balance to float
                try:
                    float(value.replace(',', ''))
                except ValueError:
                    logging.error(f"Invalid balance value in transaction: {value}")
                    return False
            elif not isinstance(value, expected_type):
                logging.error(f"Invalid type for {field}. Expected {expected_type}, got {type(value)}")
                return False
        
        # Validate category format
        if '.' not in transaction['category']:
            logging.error(f"Invalid category format: {transaction['category']}")
            return False
        
        return True
    except Exception as e:
        logging.error(f"Error validating transaction: {str(e)}")
        return False

def parse_date(date_str: str) -> Union[datetime, None]:
    """
    Parse date string to datetime object.
    Handles formats:
    - YYYY-MM-DD
    - DD-MM-YYYY
    - YY-MM-DD
    """
    try:
        return datetime.strptime(date_str, '%Y-%m-%d')
    except ValueError:
        try:
            return datetime.strptime(date_str, '%d-%m-%Y')
        except ValueError:
            try:
                # Handle YY-MM-DD format
                dt = datetime.strptime(date_str, '%y-%m-%d')
                # Assume 20xx for year
                return dt.replace(year=dt.year + 2000)
            except ValueError as e:
                logging.error(f"Failed to parse date {date_str}: {str(e)}")
                return None

def get_month_key(date_str: str) -> str:
    """Extract YYYY-MM from date string."""
    return date_str[:7]

def safe_float_conversion(value: Union[int, float, str]) -> float:
    """Safely convert a value to float."""
    try:
        if isinstance(value, str):
            return float(value.replace(',', ''))
        return float(value)
    except (ValueError, TypeError) as e:
        logging.error(f"Failed to convert value to float: {value}, Error: {str(e)}")
        return 0.0

def calculate_monthly_summary(transactions: List[Dict]) -> Dict:
    """
    Calculate monthly summary of transactions by category.
    
    Returns:
    {
        "2024-01": {
            "total_income": 50000.0,
            "total_expense": 30000.0,
            "net_cash_flow": 20000.0,
            "categories": {
                "income.salary": 45000.0,
                "income.others": 5000.0,
                "expense.food": 8000.0,
                ...
            },
            "transaction_count": 25
        },
        ...
    }
    """
    monthly_summary = defaultdict(lambda: {
        "total_income": 0.0,
        "total_expense": 0.0,
        "net_cash_flow": 0.0,
        "categories": defaultdict(float),
        "transaction_count": 0
    })
    
    for transaction in transactions:
        date = parse_date(transaction['date'])
        month_key = get_month_key(transaction['date'])
        category = transaction['category']
        
        # Update category amounts
        if transaction['credit'] > 0:
            monthly_summary[month_key]["total_income"] += transaction['credit']
            monthly_summary[month_key]["categories"][category] += transaction['credit']
        if transaction['debit'] > 0:
            monthly_summary[month_key]["total_expense"] += transaction['debit']
            monthly_summary[month_key]["categories"][category] += transaction['debit']
        
        # Update net cash flow
        monthly_summary[month_key]["net_cash_flow"] = (
            monthly_summary[month_key]["total_income"] - 
            monthly_summary[month_key]["total_expense"]
        )
        
        # Increment transaction count
        monthly_summary[month_key]["transaction_count"] += 1
    
    # Convert defaultdict to regular dict
    return {
        month: dict(data) for month, data in monthly_summary.items()
    }

def calculate_median_summary(monthly_summary: Dict) -> Dict:
    """
    Calculate median values across all months.
    
    Returns:
    {
        "median_income": 45000.0,
        "median_expense": 30000.0,
        "median_net_cash_flow": 15000.0,
        "median_by_category": {
            "income.salary": 45000.0,
            "expense.food": 8000.0,
            ...
        },
        "median_transaction_count": 25
    }
    """
    # Initialize lists to store monthly values
    all_incomes = []
    all_expenses = []
    all_net_cash_flows = []
    all_transaction_counts = []
    category_values = defaultdict(list)
    
    # Collect values across months
    for month_data in monthly_summary.values():
        all_incomes.append(month_data["total_income"])
        all_expenses.append(month_data["total_expense"])
        all_net_cash_flows.append(month_data["net_cash_flow"])
        all_transaction_counts.append(month_data["transaction_count"])
        
        # Collect category values
        for category, amount in month_data["categories"].items():
            category_values[category].append(amount)
    
    # Calculate medians
    median_summary = {
        "median_income": statistics.median(all_incomes) if all_incomes else 0.0,
        "median_expense": statistics.median(all_expenses) if all_expenses else 0.0,
        "median_net_cash_flow": statistics.median(all_net_cash_flows) if all_net_cash_flows else 0.0,
        "median_transaction_count": statistics.median(all_transaction_counts) if all_transaction_counts else 0,
        "median_by_category": {
            category: statistics.median(values) if values else 0.0
            for category, values in category_values.items()
        }
    }
    
    return median_summary

def prepare_transaction_dataframe(response_data: Dict[str, Any]) -> pd.DataFrame:
    """
    Convert API response data into a pandas DataFrame and prepare it for analysis.
    Handles both list and dict input formats.
    """
    # Extract transactions from response, handling both formats
    if isinstance(response_data, list):
        transactions = response_data
    elif isinstance(response_data, dict):
        transactions = response_data.get("data", {}).get("analysis", [])
    else:
        print(f"[ERROR] Unexpected input type: {type(response_data)}")
        return pd.DataFrame()
    
    # Create DataFrame
    df = pd.DataFrame(transactions)
    
    if df.empty:
        print("[WARNING] No transactions found in input data")
        return df
    
    try:
        # Convert date using mixed format parsing
        df['date'] = pd.to_datetime(df['date'], format='mixed', dayfirst=True)
        df['month'] = df['date'].dt.to_period('M')
        
        # Convert numeric columns
        df['debit'] = pd.to_numeric(df['debit'], errors='coerce').fillna(0.0)
        df['credit'] = pd.to_numeric(df['credit'], errors='coerce').fillna(0.0)
        
        # Split category into type and subcategory
        df['category_type'] = df['category'].str.split('.').str[0].str.lower()
        df['sub_category'] = df['category'].str.split('.').str[1]
        
        return df
    except Exception as e:
        print(f"[ERROR] Error preparing DataFrame: {str(e)}")
        return pd.DataFrame()

def calculate_monthly_breakdown(df: pd.DataFrame) -> List[Dict]:
    """
    Calculate monthly breakdown of transactions using pandas.
    """
    if df.empty:
        print("[WARNING] Empty DataFrame provided for monthly breakdown")
        return []
        
    try:
        # Group data by month, category type, and subcategory
        grouped_data = df.groupby(['month', 'category_type', 'sub_category']).agg({
            'debit': 'sum',
            'credit': 'sum'
        }).reset_index()
        
        monthly_breakdown = []
        
        # Process each month
        for month in sorted(df['month'].unique()):
            month_data = grouped_data[grouped_data['month'] == month]
            
            # Get income and expense data
            income_data = month_data[month_data['category_type'] == 'income']
            expense_data = month_data[month_data['category_type'] == 'expense']
            
            # Calculate totals
            income_amount = round(float(income_data['credit'].sum()), 2)
            expense_amount = round(float(expense_data['debit'].sum()), 2)
            savings = round(income_amount - expense_amount, 2)
            
            # Create category breakdowns
            income_breakdown = [
                {row['sub_category']: round(float(row['credit']), 2)}
                for _, row in income_data.iterrows()
                if row['credit'] > 0
            ]
            
            expense_breakdown = [
                {row['sub_category']: round(float(row['debit']), 2)}
                for _, row in expense_data.iterrows()
                if row['debit'] > 0
            ]
            
            # Create month entry
            month_entry = {
                "month": str(month),
                "income": income_amount,
                "expense": expense_amount,
                "savings": savings,
                "income_breakdown": sorted(income_breakdown, key=lambda x: list(x.keys())[0]),
                "expense_breakdown": sorted(expense_breakdown, key=lambda x: list(x.keys())[0])
            }
            
            monthly_breakdown.append(month_entry)
        
        return monthly_breakdown
    except Exception as e:
        print(f"[ERROR] Error calculating monthly breakdown: {str(e)}")
        return []

def flatten_breakdown(monthly_data: List[Dict], key: str) -> pd.DataFrame:
    """
    Flatten category breakdowns into a DataFrame for median calculations.
    """
    rows = []
    try:
        for entry in monthly_data:
            month = entry["month"]
            for cat in entry.get(key, []):
                for k, v in cat.items():
                    rows.append({"month": month, "category": k, "amount": v})
        return pd.DataFrame(rows)
    except Exception as e:
        print(f"[ERROR] flatten_breakdown: {e}")
        return pd.DataFrame()

def calculate_median_summary(monthly_breakdown: List[Dict]) -> Dict:
    """
    Calculate median values across all months.
    """
    try:
        # Convert main metrics to DataFrame
        df_metrics = pd.DataFrame(monthly_breakdown)
        
        # Calculate medians for main metrics
        median_income = df_metrics['income'].median()
        median_expense = df_metrics['expense'].median()
        median_savings = df_metrics['savings'].median()
        
        # Flatten and calculate medians for breakdowns
        df_income = flatten_breakdown(monthly_breakdown, "income_breakdown")
        df_expense = flatten_breakdown(monthly_breakdown, "expense_breakdown")
        
        # Calculate category medians
        median_income_cats = (
            df_income.groupby("category")["amount"].median().to_dict()
            if not df_income.empty else {}
        )
        
        median_expense_cats = (
            df_expense.groupby("category")["amount"].median().to_dict()
            if not df_expense.empty else {}
        )
        
        return {
            "median_income": round(float(median_income), 2),
            "median_expense": round(float(median_expense), 2),
            "median_savings": round(float(median_savings), 2),
            "median_income_breakdown": {
                k: round(float(v), 2) 
                for k, v in median_income_cats.items()
            },
            "median_expense_breakdown": {
                k: round(float(v), 2) 
                for k, v in median_expense_cats.items()
            }
        }
    except Exception as e:
        print(f"[ERROR] calculate_median_summary: {e}")
        return {}

def generate_transaction_breakdown(response_data: Dict[str, Any]) -> Dict:
    """
    Generate complete transaction analysis including monthly breakdown and median summary.
    """
    try:
        # print('response_data: ', response_data)
        # Prepare DataFrame
        df = prepare_transaction_dataframe(response_data)
        
        # Calculate monthly breakdown
        monthly_breakdown = calculate_monthly_breakdown(df)
        
        # Calculate median summary
        median_summary = calculate_median_summary(monthly_breakdown)
        
        return {
            "monthly_breakdown": monthly_breakdown,
            "median_summary": median_summary
        }
    except Exception as e:
        print(f"[ERROR] generate_transaction_breakdown: {e}")
        return {
            "monthly_breakdown": [],
            "median_summary": {}
        } 