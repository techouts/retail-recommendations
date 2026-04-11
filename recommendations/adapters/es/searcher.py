from ..es.client import get_es_client
import logging

logger = logging.getLogger(__name__)


def search_es(
    ALIAS_NAME: str,
    query: dict = None,
    filters: dict = None,
    limit: int = 20,
    offset: int = 0
):
    es = get_es_client()

    try:
        if not ALIAS_NAME:
            raise ValueError("ALIAS_NAME is required for Elasticsearch search")

        if not es.indices.exists_alias(name=ALIAS_NAME):
            raise ValueError(f"Alias '{ALIAS_NAME}' does not exist.")

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
        logger.exception("Elasticsearch search failed for alias '%s'", ALIAS_NAME)
        raise RuntimeError(f"Elasticsearch search failed for alias '{ALIAS_NAME}': {e}") from e
