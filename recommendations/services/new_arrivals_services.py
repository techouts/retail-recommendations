from ..exceptions.exceptions import (
    BadRequestException,
    PipelineException
)

from ..pipelines.new_arrivals_pipeline import (
    run_new_arrivals_pipeline
)

from recommendations.adapters.es.searcher import (
    search_es
)


class NewArrivalsService:

    # ─────────────────────────────────────────────
    # Train New Arrivals
    # ─────────────────────────────────────────────

    def trainNewArrivals(
        self,
        new_arrival_settings: dict,
        client: str
    ):

        try:

            data = run_new_arrivals_pipeline(
                new_arrival_settings,
                client
            )

            return {
                "success": True,
                "count": len(data),
                "data": data
            }

        except Exception as e:

            raise PipelineException(
                f"New arrivals training failed: {str(e)}"
            )

    # ─────────────────────────────────────────────
    # Get New Arrivals
    # ─────────────────────────────────────────────

    def getNewArrivals(
        self,
        client: str,
        filters=None,
        limit=20
    ):

        try:

            alias_name = f"{client}_new_arrivals"

            # No filters
            if not filters:

                result = search_es(
                    alias_name,
                    limit=limit,
                    offset=0
                )

            else:

                must = []

                for field, value in filters.items():

                    must.append({
                        "match": {
                            field: {
                                "query": value,
                                "operator": "and"
                            }
                        }
                    })

                query = {
                    "query": {
                        "bool": {
                            "must": must
                        }
                    }
                }

                result = search_es(
                    alias_name,
                    query=query,
                    limit=limit,
                    offset=0
                )

            return {
                "count": result["nbHits"],
                "data": result["hits"]
            }

        except Exception as e:

            raise PipelineException(
                f"Fetching new arrivals failed: {str(e)}"
            )