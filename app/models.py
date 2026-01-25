from pydantic import BaseModel
from typing import List, Optional, Dict

class FraudQuery(BaseModel):
    user_story: str
    top_k: Optional[int] = 5

class TopMatch(BaseModel):
    id: str
    similarity: float
    metadata: Dict

class FraudResponse(BaseModel):
    probability: float
    top_matches: List[TopMatch]
    markdown: str



# ---------- REQUEST ----------
class CompensationQuery(BaseModel):
    user_message: str


# ---------- RESPONSE ----------
class CompensationResponse(BaseModel):
    transaction_amount: str
    transaction_date: str
    compensation_eligible: bool
    compensation_amount: str
    other_info: str
    bank_name: Optional[str] = None
    links: Optional[dict] = None


