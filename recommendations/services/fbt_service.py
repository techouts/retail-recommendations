from itertools import count

from ..exceptions.exceptions import BadRequestException , PipelineException
from ..pipelines.fbt_pipeline import run_fbt_pipeline
from recommendations.adapters.meili.searcher import search_meili 
import json
from recommendations.adapters.es.client import get_es_client
from recommendations.adapters.es.searcher import search_es




es = get_es_client()
# FBT_INDEX = "fbt"


class FrequentlyBoughtTogetherService:
    
    def trainFrequentlyBoughtTogether(self,fbt_settings:dict,client:str):
        try:
            data = run_fbt_pipeline(fbt_settings  , client )
            return {
                "success": True,
                "message": "fbt training complete",
                "client": client,
                "data": data  
            }
        except PipelineException as e:
            raise PipelineException(f"Fbt pipeline failed : {str(e)}")
    
    def fetch_fbt_products(self, product_id: str , index_name: str , top_n: int):
        """
        Fetch FBT recommendations for a given product_id   product_id_A    skuid_A__keyword
        """
        if not product_id:
            raise ValueError("product_id is required")

        if not index_name:
            raise ValueError("index_name is required")

        query = {
            "query": {
                "bool": {
                    "should": [
                        {"term": {"skuid_A.keyword": product_id}},
                        {"term": {"skuid_A": product_id}},
                        {"match": {"skuid_A": product_id}}
                    ],
                    "minimum_should_match": 1
                }
            }
        }

        result = search_es(index_name, query=query, limit=1, offset=0)
        hits = result.get("hits", [])

        if not hits:
            return {"error": f"Product {product_id} not found in {index_name}"}

        product_doc = hits[0]
        fbt_pairs = product_doc.get("pairs", [])

        return {
            "product_id": product_id,
            "fbt": fbt_pairs[:top_n]
        }