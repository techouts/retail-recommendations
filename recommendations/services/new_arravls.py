import json
from typing import List
from ..pipelines.new_arrivals_pipeline import run_new_arrivals_pipeline
# from recommendations.adapters.meili.searcher import search_es

from recommendations.adapters.es.searcher import search_es


class NewArrivalsService:
    ALIAS = "new_arrivals"

    def train_new_arrivals(self, settings: dict, client: str):
        if not client:
            raise ValueError("client is required")

        try:
            result_df = run_new_arrivals_pipeline(settings, client)

            return {
                "success": True,
                "message": "New Arrivals training complete",
                "count": len(result_df),
                "client": client,
                "data": result_df
            }

        except Exception as e:
            raise Exception(f"New Arrivals pipeline failed: {str(e)}")