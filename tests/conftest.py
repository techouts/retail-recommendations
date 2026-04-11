import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


os.environ.setdefault("HOST_URL", "http://localhost:7700")
os.environ.setdefault("API_KEY", "dummy_key")
os.environ.setdefault("ES_HOST", "localhost")
os.environ.setdefault("ES_PORT", "9200")
os.environ.setdefault("ES_SCHEME", "http")
os.environ.setdefault("FETCH_RATE_LIMIT_PER_MINUTE", "500")
