import meilisearch

from recommendations.core.config import settings

MEILI_URL = settings.meili_url
MEILI_API_KEY = settings.api_key

if settings.require_tls and not MEILI_URL.startswith("https://"):
	raise ValueError("TLS is required but MEILI_URL is not using https.")

client = meilisearch.Client(MEILI_URL, MEILI_API_KEY)
