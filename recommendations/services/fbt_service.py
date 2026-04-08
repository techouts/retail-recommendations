from ..exceptions.exceptions import BadRequestException , PipelineException
from ..pipelines.fbt_pipeline import run_fbt_pipeline
from recommendations.adapters.meili.searcher import search_meili 
import json
from elasticsearch import Elasticsearch
from elasticsearch_dsl import Search
from dotenv import load_dotenv
import os

load_dotenv()
ES_HOST = os.getenv("ELASTICSEARCH_HOST")
ES_PORT = os.getenv("ELASTICSEARCH_PORT")

es = Elasticsearch(f"http://{ES_HOST}:{ES_PORT}")
# FBT_INDEX = "fbt"


class FrequentlyBoughtTogetherService:
    
    def trainFrequentlyBoughtTogether(self,fbt_settings:dict,client:str):
        try:
            data = run_fbt_pipeline(fbt_settings  , client )
            return {    
                "success": True,
                "data":data
            }
        except PipelineException as e:
            raise PipelineException(f"Fbt pipeline failed : {str(e)}")
    
    def fetch_fbt_products(self, product_id: str , index_name: str , top_n: int):
        """
        Fetch FBT recommendations for a given product_id   product_id_A    skuid_A__keyword
        """
        s = Search(using=es, index=index_name).query("term", skuid_A__keyword=product_id)
        response = s.execute()

        if not response.hits:
            return {"error": f"Product {product_id} not found in {index_name}"}

        product_doc = response.hits[0].to_dict()
        fbt_pairs = product_doc.get("pairs", [])

        return {
            "product_id": product_id,
            "fbt": fbt_pairs
        }