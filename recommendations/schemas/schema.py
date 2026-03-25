from pydantic import BaseModel

class   RecommendationCreate(BaseModel):
    user_id: int
    product_id: int
    score: int


class RecommendationResponse(BaseModel):
    id: int
    user_id: int
    product_id: int
    score: int

    class Config:
        from_attributes= True
