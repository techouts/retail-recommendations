from pydantic import BaseModel
from typing import Dict, Any

class TrainTrendingRequest(BaseModel):
    Client: str
    settings: Dict[str, Any]