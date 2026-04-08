import meilisearch
import os 
from dotenv import load_dotenv

load_dotenv()

MEILI_URL =  os.getenv("MEILI_URL")
MEILI_API_KEY = os.getenv("MEILI_API_KEY")


client = meilisearch.Client(MEILI_URL, MEILI_API_KEY)
