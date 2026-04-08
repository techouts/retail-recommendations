from elasticsearch import Elasticsearch
import os
from dotenv import load_dotenv








load_dotenv()

ES_HOST = os.getenv("ES_HOST")

ES_PORT = os.getenv("ES_PORT", "9200")  

# ES_HOST = os.getenv("ELASTICSEARCH_HOST" )
# ES_PORT = os.getenv("ELASTICSEARCH_PORT" )  

# print("ES_HOST:", ES_HOST)
# print("ES_PORT:", ES_PORT)

def get_es_client():
    url = f"http://{ES_HOST}:{ES_PORT}"
    print("Connecting to:", url)
    return Elasticsearch(url)

