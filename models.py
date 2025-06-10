from pydantic import BaseModel
from typing import List, Dict

class Transaction(BaseModel):
    date: str
    description: str
    debit: float = 0.0
    credit: float = 0.0
    balance: float
    category: str = "uncategorized"

class AnalysisResponse(BaseModel):
    status: str
    transactions: List[Transaction]

class HomeResponse(BaseModel):
    status: str
    message: str
    endpoints: Dict[str, str] 