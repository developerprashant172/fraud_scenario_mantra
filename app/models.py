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
