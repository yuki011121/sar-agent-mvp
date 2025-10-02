import redis
import logging
import os
import sys
import openai
from dotenv import load_dotenv
# import required module
from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import ApiException
import ast
from typing import List, Optional
from joblib import load
#for pub/sub for redis

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from main import find_match, qdrant_query, qdrant_ISRID_filter

load_dotenv()
#REST api port for qdrant
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", None)
AGENT_VERSION = "3.0.0"
OPENAI_KEY = os.getenv("OPENAI_KEY", None)
ISRID_VECTORIZER_PATH = "agents/history/models/isrid_tfidf_vectorizer.joblib"
QDRANT_ISRID_COLLECTION = "ISRID_collection"
TOP_K = 3

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)


if OPENAI_KEY is None:
    logging.info("Couldn't find a api key for OPENAI")
    exit(1)

if QDRANT_COLLECTION is None:
    logging.info("Couldn't find a collection name for QDRANT")
    exit(1)

client = openai.OpenAI(api_key=OPENAI_KEY)

try:
    client_Qdrant = QdrantClient(url=QDRANT_URL)
    logging.info(f"Successfully connected to Qdrant at {QDRANT_URL}")
except ApiException as e:
    logging.critical(f"Exception when calling QdrantClient: {e}")
    exit(1)
except Exception as e:
    logging.critical(f"Could not connect to Qdrant: {e}")
    exit(1)

try:
    ISRID_VECTORIZER = load(ISRID_VECTORIZER_PATH)
    logging.info("Successfully loaded ISRID vectorizer")
except Exception as e:
    logging.critical(f"Error loading ISRID vectorizer: {e}. Fix by running isrid_parsing.py")
    logging.critical(f"Make sure the path {ISRID_VECTORIZER_PATH} is correct" +  
                     " or run agents/history/isrid_parsing.py to create it.")
    exit(1)


mock_payload = {
    'outcome': 'search',
    'terrain': 'mountainous',
    'category': 'hiker',
    'filter': {
        'type': 'location',
        'filter_value': "us-ky"
    }
}

mock_payload2 = {
    'outcome': 'public',
    'terrain': 'mountainous',
    'filter': {
        'type': 'category',
        'filter_value': "atv"
    }
}


bad_payload = {
    'outcome': 'search',
    'terrain': 'mountainous',
    'category': 'hiker',
    'filter': {
        'type': 'location',
        'filter_value': "invalid_location_123"
    }
}

age_payload = {
    'outcome': 'search',
    'terrain': 'mountainous',
    'category': 'hiker',
    'filter': {
        'type': 'aGe',
        'filter_value': "100"
    }
}
def test_basic_isrid_qdrant():
    assert len(find_match(dict(mock_payload))) == 3 

def test_fallback():
    assert len(find_match(dict(bad_payload))) == 3


def test_no_fallback_1():
    query_filter = bad_payload["filter"] if "filter" in bad_payload else None
    assert query_filter is not None
    filter = qdrant_ISRID_filter(query_filter)
    assert len(filter) == 1

def test_no_fallback_2():
    copy_bad_payload = dict(bad_payload)
    query_filter = copy_bad_payload["filter"] if "filter" in copy_bad_payload else None
    copy_bad_payload.pop('filter', None)
    copy_bad_payload.pop('additional', None)
    query_as_string = " ".join(copy_bad_payload.values()).lower()
    query_vector = ISRID_VECTORIZER.transform([query_as_string]).toarray()[0]
    filter = qdrant_ISRID_filter(query_filter)
    query_res = qdrant_query(query_vector, QDRANT_ISRID_COLLECTION, TOP_K
                           , filter)
    assert len(query_res) == 0

def test_age_filter():
    #NOTE tha max age in the dataset is 99 but the filter should add a delta for a range that will capture
    #this point(s)
    res = find_match(dict(age_payload))
    print([payload["Age"] for payload in res])
    assert (len(res)) > 0

def test_location():
    res = find_match(dict(mock_payload))
    assert len(res) == 3
    #mock-payload asks to filter by location using "us-ky". Therefore, all results must have "us-ky" as a location
    assert len(["us-ky" for payload in res if payload["Data_Source"] == "us-ky"]) == 3


def test_category():
    res = find_match(dict(mock_payload2))
    assert len(res) == 3
    #mock-payload asks to filter by location using "us-ky". Therefore, all results must have "us-ky" as a location
    assert len(["stub" for payload in res if payload["Subject_Category"] == "atv"]) == 3