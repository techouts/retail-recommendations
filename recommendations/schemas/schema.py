from pydantic import BaseModel

class  TrainRecommendationsRequest(BaseModel):
    settings: dict
    Client: str


class RecommendationResponse(BaseModel):
    id: int
    user_id: int
    product_id: int
    score: int

    class Config:
        from_attributes= True


from pydantic import BaseModel

class TrainTrendingRequest(BaseModel):
    settings: dict
    Client: str


class TrainPopularCategoriesRequest(BaseModel):
    settings: dict
    Client: dict
    
class TrainDodRequest(BaseModel):
    client : str
    settings : dict
    levels : list
    
class TrainFbtProductsRequest(BaseModel):
    client : str
    settings : dict
    
class TrainPopularBrandsRequest(BaseModel):
    client : str
    settings : dict