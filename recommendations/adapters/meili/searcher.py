from adapters.meili.client import client


def search_meili(
    index_name: str,
    query: str = "",
    filters: str = None,
    limit: int = 20,
    offset: int = 0
):
    """
    Search documents from meili
    """

    index = client.index(index_name)

    search_params = {
        "limit": limit,
        "offset": offset,
    }

    if filters:
        search_params["filter"] = filters

    results = index.search(query, search_params)

    return {
        "hits": results.get("hits", []),
        "nbHits": results.get("estimatedTotalHits", 0),
    }