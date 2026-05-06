import logging
import os
import json
from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams
from joblib import load

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

load_dotenv()
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_API_ADMIN_KEY = os.getenv("QDRANT_API_ADMIN_KEY", None)
COLLECTION_NAME = "ISRID_collection"

try:
    client = QdrantClient(url=QDRANT_URL,
                      api_key=QDRANT_API_ADMIN_KEY)
    logging.info(f"Successfully connected to Qdrant at {QDRANT_URL}")
except Exception as e:
    logging.critical(f"Could not connect to Qdrant: {e}")
    exit(1)

def create_collection(VECTOR_SIZE: int):
    collections = client.get_collections().collections
    collection_names = [c.name for c in collections]

    if COLLECTION_NAME in collection_names:
        logging.info(f"Collection {COLLECTION_NAME} exists")
    else:
        logging.info(f"Creating Collection: {COLLECTION_NAME}")
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
        )

def main():
    # Prefer loading preformatted data if available; otherwise build it from CSV
    FILE_LOCATION = '.data/formatted_isrid.json'
    formatted_rows = None

    if os.path.exists(FILE_LOCATION):
        logging.info(f"Loading preformatted ISRID data from {FILE_LOCATION}")
        try:
            with open(FILE_LOCATION, 'r', encoding='utf-8') as f:
                formatted_rows = json.load(f)
        except Exception as e:
            logging.error(f"Failed to read formatted file: {e}. Will reformat from CSV.")

    if formatted_rows is None:
        logging.error("couldn't load preformatted data")
        exit(1)

    logging.info("Attempting to insert ISRID dataset to Qdrant vector DB")
    
    points = []
    # Load existing vectorizer if available, otherwise fit a new one and save it
    VECT_FILE = '../../models/isrid_tfidf_vectorizer.joblib'
    if os.path.exists(VECT_FILE):
        try:
            vectorizer = load(VECT_FILE)
            logging.info(f"Loaded vectorizer from {VECT_FILE}")
            vectorized = vectorizer.transform([entry["content"] for entry in formatted_rows])
        except Exception as e:
            logging.error(f"Failed to load vectorizer: {e}.")
            exit(1)
    else:
        logging.error(f"Vectorizer file {VECT_FILE} not found.")
        exit(1)
    
    for idx, (row, vector) in enumerate(zip(formatted_rows, vectorized)):
        point = {
            "id": idx,
            "vector": vector.toarray().flatten().tolist(),
            "payload": row
        }
        points.append(point)

    VECTOR_SIZE = len(points[0]["vector"])

    # Create collection if it doesn't exist

    create_collection(VECTOR_SIZE)

    try:
        client.upsert(
            collection_name=COLLECTION_NAME,
            wait=True,
            points=points
        )
    except Exception as e:
        logging.critical(f"Failed to upsert points to Qdrant: {e}")
        exit(1)

    
if __name__ == "__main__":
    main()