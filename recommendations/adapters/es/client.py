from elasticsearch import Elasticsearch
import os
from dotenv import load_dotenv
import logging

from recommendations.core.config import settings



load_dotenv()

ES_HOST = os.getenv("ES_HOST")
ES_PORT = os.getenv("ES_PORT", "9200")  
ES_SCHEME = os.getenv("ES_SCHEME", "http")

logger = logging.getLogger(__name__)

# ES_HOST = os.getenv("ELASTICSEARCH_HOST" )
# ES_PORT = os.getenv("ELASTICSEARCH_PORT" )  

# print("ES_HOST:", ES_HOST)
# print("ES_PORT:", ES_PORT)

def get_es_client():
    if not ES_HOST:
        raise ValueError("ES_HOST is required")

    url = f"{ES_SCHEME}://{ES_HOST}:{ES_PORT}"
    if settings.require_tls and not url.startswith("https://"):
        raise ValueError("TLS is required but Elasticsearch URL is not using https.")

    logger.debug("Connecting to Elasticsearch")
    return Elasticsearch(url)

