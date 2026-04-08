from elasticsearch import Elasticsearch
from ..es.client import get_es_client
import traceback


def search_es(
    ALIAS_NAME: str,
    query: dict = None,
    filters: dict = None,
    limit: int = 20,
    offset: int = 0
):
    es = get_es_client()
    print("es",es)

    try:
        if not es.indices.exists_alias(name=ALIAS_NAME):
            print(f"Alias '{ALIAS_NAME}' does not exist.")
            return {
                "hits": [],
                "nbHits": 0
            }

        # Base query
        body = query if query else {"query": {"match_all": {}}}

        # Add filters (optional)
        if filters:
            body = {
                "query": {
                    "bool": {
                        "must": body.get("query", {"match_all": {}}),
                        "filter": filters
                    }
                }
            }

        response = es.search(
            index=ALIAS_NAME,
            body=body,
            from_=offset,
            size=limit
        )

        hits = response["hits"]["hits"]

        return {
            "hits": [hit.get("_source", {}) for hit in hits],
            "nbHits": response["hits"]["total"]["value"]
        }

    except Exception as e:
        print(f"Error: {e}")
        traceback.print_exc()
        return {
            "hits": [],
            "nbHits": 0
        }