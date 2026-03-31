from ..exceptions.exceptions import BadRequestException , PipelineException
from ..pipelines.dealofday_pipleline import run_dod_pipeline
from recommendations.adapters.meili.searcher import search_meili
import json
# ALIAS="deal_ofthe_day"
class DealOfDayService:
    
    def trainDealOfDay(self , dealofday_settings:dict , client: str , levels : list):
        try:
            data= run_dod_pipeline(dealofday_settings,client ,levels)
            return {
                "success":True,
                "data":data
            }
        except PipelineException as e:
            raise PipelineException(f"Deal of Day pipleline failed : {str(e)}")
        
    def dealofday_fetch_l1(index_name : str, l1list : list , limit: int , offset:int ):
        query=""
        # filters = f"l1 IN {l1list}"
        filters = f'l1 IN {l1list}'
        response = search_meili(index_name=index_name,query=query,filters=filters,limit=limit,offset=offset)
        return response

    def dealofday_fetch_l2(index_name : str, l2list : list , limit : int, offset :int):
        query=""
        filters = f'l2 IN {l2list}'
        response = search_meili(index_name=index_name,query=query,filters=filters,limit=limit,offset=offset)
        return response

    def dealofday_fetch_l3(index_name : str , l3list : list , limit : int, offset : int):
        query=""
        filters = f'l3 IN {l3list}'
        response = search_meili(index_name=index_name,query=query,filters=filters,limit=limit,offset=offset)
        return response

    def dealofday_fetch(index_name : str, l1list : list, l2list: list , limit : int, offset : int):
        query=""
        l1_filter = f"l1 IN {json.dumps(l1list)}"
        l2_filter = f"l2 IN {json.dumps(l2list)}"

        filters = f"{l1_filter} AND {l2_filter}"
        
        response = search_meili(index_name=index_name,query=query,filters=filters,limit=limit,offset=offset)
        return response