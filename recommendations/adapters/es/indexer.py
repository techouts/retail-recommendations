from elasticsearch import helpers
from ..es.client import get_es_client
import logging
import traceback
logger = logging.getLogger(__name__)


def push_to_es(INDEX_PREFIX, ALIAS_NAME, docs: list[dict]):
    es = get_es_client()   

    index = None
    backup_index = None

    try:
        logging.info("Starting Elasticsearch index process...")

        if es.indices.exists(index=f"{INDEX_PREFIX}_a"):
            index = f"{INDEX_PREFIX}_b"
            backup_index = f"{INDEX_PREFIX}_a"
        elif es.indices.exists(index=f"{INDEX_PREFIX}_b"):
            index = f"{INDEX_PREFIX}_a"
            backup_index = f"{INDEX_PREFIX}_b"
        else:
            index = f"{INDEX_PREFIX}_a"

        if not es.indices.exists(index=index):
            es.indices.create(index=index)

        actions = [{"_index": index, "_source": doc} for doc in docs]

        success, errors = helpers.bulk(es, actions)

        if errors:
            es.indices.delete(index=index)
            return

        #  Alias fix
        actions = []

        if backup_index and es.indices.exists(index=backup_index):
            actions.append({
                "remove": {"index": backup_index, "alias": ALIAS_NAME}
            })

        actions.append({
            "add": {"index": index, "alias": ALIAS_NAME}
        })

        es.indices.update_aliases(body={"actions": actions})

        # delete old index
        if backup_index and es.indices.exists(index=backup_index):
            es.indices.delete(index=backup_index)

    except Exception as e:
        logging.error(f"Exception: {e}")
        traceback.print_exc()


from ..es.client import get_es_client
import traceback


def get_data_from_es(ALIAS_NAME) -> list[dict]:
    es = get_es_client()   #  FIX

    try:
        # Check alias exists
        if not es.indices.exists_alias(name=ALIAS_NAME):
            print(f"Alias '{ALIAS_NAME}' does not exist.")
            return []

        response = es.search(
            index=ALIAS_NAME,
            body={"query": {"match_all": {}}},
            scroll="2m",
            size=1000   #  safer than 10000
        )

        scroll_id = response.get("_scroll_id")
        hits = response["hits"]["hits"]

        all_docs = [hit["_source"] for hit in hits]

        # Scroll loop
        while hits:
            scroll_response = es.scroll(scroll_id=scroll_id, scroll="2m")
            hits = scroll_response["hits"]["hits"]

            if not hits:
                break

            all_docs.extend([hit["_source"] for hit in hits])

        #  clear scroll (IMPORTANT)
        if scroll_id:
            es.clear_scroll(scroll_id=scroll_id)

        print(f"Retrieved {len(all_docs)} documents from alias '{ALIAS_NAME}'")
        return all_docs

    except Exception as e:
        print(f"Error fetching data from alias '{ALIAS_NAME}': {e}")
        traceback.print_exc()
        return []