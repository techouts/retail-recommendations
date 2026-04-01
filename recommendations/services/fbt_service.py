from ..exceptions.exceptions import BadRequestException , PipelineException
from ..pipelines.fbt_pipeline import run_fbt_pipeline
from recommendations.adapters.meili.searcher import search_meili 
import json

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
    
    def fetch_fbt_products(self, product_id :str , index_name : str, top_n : int):
        filters = f'skuid_A = "{product_id}"'
        response = search_meili(index_name=index_name , query="", filters=filters, limit=top_n)
        hits = response.get("hits",[])
        if not hits:
            return {"Error":f"product {product_id} not found in index {index_name}."}
        product_doc = hits[0]
        fbt_pairs = product_doc.get("pairs",[])[:top_n]
        return {
            "product_id": product_id,
            "fbt":fbt_pairs
        }