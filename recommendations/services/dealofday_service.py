from ..exceptions.exceptions import BadRequestException , PipelineException
from ..pipelines.dealofday_pipleline import run_dod_pipeline
from recommendations.adapters.meili.searcher import search_meili
from recommendations.adapters.es.client import get_es_client



es = get_es_client()
# ALIAS="deal_ofthe_day"

import json
# ALIAS="deal_ofthe_day"
class DealOfDayService:
    
    def trainDealOfDay( self,dealofday_settings:dict , client: str , levels : list):
        try: 
            data= run_dod_pipeline(dealofday_settings,client ,levels)
            return {
                "success":True,
                "data":data
            }
        except PipelineException as e:
            raise PipelineException(f"Deal of Day pipleline failed : {str(e)}")
        
        
    
    def dealoftheday_fetch_l1(self, index_name: str, l1list: list, limit: int):
        query = {"query": {"terms": {"l1.keyword": l1list}}}
        resp = es.search(index=index_name, body=query, size=limit)
        all_hits = [hit["_source"] for hit in resp["hits"]["hits"]]
        return all_hits
        
    def dealoftheday_fetch_l2(self, index_name: str, l2list: list, limit: int):
        query = {"query": {"terms": {"l2.keyword": l2list}}}
        resp = es.search(index=index_name, body=query, size=limit)
        all_hits = [hit["_source"] for hit in resp["hits"]["hits"]]
        return all_hits
    
    def dealoftheday_fetch_l3(self, index_name: str, l3list: list, limit: int):
        query = {"query": {"terms": {"l3.keyword": l3list}}}
        resp = es.search(index=index_name, body=query, size=limit)
        all_hits = [hit["_source"] for hit in resp["hits"]["hits"]]
        return all_hits

    def dealoftheday_fetch_all(self, index_name: str, size=100):
        resp=es.search(index=index_name,size=size)
        hits=[hit["_source"] for hit in resp["hits"]["hits"]]
        return hits
