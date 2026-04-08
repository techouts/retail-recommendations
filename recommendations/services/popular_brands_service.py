from ..exceptions.exceptions import BadRequestException , PipelineException
from ..pipelines.popular_brands_pipeline import run_popular_brands
from elasticsearch import Elasticsearch
from elasticsearch_dsl import Search
from dotenv import load_dotenv
import os

load_dotenv()
ES_HOST = os.getenv("ELASTICSEARCH_HOST")
ES_PORT = os.getenv("ELASTICSEARCH_PORT")

es = Elasticsearch(f"http://{ES_HOST}:{ES_PORT}")

class PopularBrandsService:
    def train_popular_brands_service(self, popular_brands_settings:dict , client : str):
        try:
            data = run_popular_brands(popular_brands_settings,client)
            return {
                "success": True,
                "data":data
            }
        except PipelineException as e:
            raise PipelineException(f"Popular brands pipeline failed : ", {str(e)})
        
    
    def fetch_popular_brands(self, brand: str, index_name: str, top_n: int):
        try:
            s = Search(using=es, index=index_name).query(
                "term",
                brand=brand   
            )
            response = s.execute()
            if not response.hits:
                return {"error": f"Brand {brand} not found in {index_name}"}
            hits = [hit.to_dict() for hit in response.hits]
            return {
                "brand": brand,
                "results": hits[:top_n]
            }
        except Exception as e:
            raise PipelineException(f"Popular products fetch failed: {str(e)}")