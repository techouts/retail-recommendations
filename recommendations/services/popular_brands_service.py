from ..exceptions.exceptions import BadRequestException , PipelineException
from ..pipelines.popular_brands_pipeline import run_popular_brands
from recommendations.adapters.es.client import get_es_client
from recommendations.adapters.es.searcher import search_es



es = get_es_client()

class PopularBrandsService:
    def train_popular_brands_service(self, popular_brands_settings:dict , client : str):
        try:
            data = run_popular_brands(popular_brands_settings,client)
            return {
                "success": True,
                "count": len(data),
                "data":data
            }
        except PipelineException as e:
            raise PipelineException(f"Popular brands pipeline failed : ", {str(e)})
        
    
    def fetch_popular_brands(self, brand: str, index_name: str, top_n: int):
        try:
            if not brand:
                raise ValueError("brand is required")

            if not index_name:
                raise ValueError("index_name is required")

            query = {
                "query": {
                    "bool": {
                        "should": [
                            {"term": {"brand.keyword": brand}},
                            {"term": {"brand": brand}},
                            {"match": {"brand": brand}}
                        ],
                        "minimum_should_match": 1
                    }
                }
            }

            result = search_es(index_name, query=query, limit=top_n, offset=0)
            hits = result.get("hits", [])

            if not hits:
                return {"error": f"Brand {brand} not found in {index_name}"}

            return {
                "brand": brand,
                "results": hits[:top_n]
            }
        except Exception as e:
            raise PipelineException(f"Popular products fetch failed: {str(e)}")