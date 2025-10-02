import pandas as pd
import numpy as np
import redis
import logging
import os
import json
import openai
from dotenv import load_dotenv
from datetime import datetime, timezone
# import required module
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from typing import List
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams
from joblib import dump

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

load_dotenv()
ISRID_PATH = os.getenv("ISRID_PATH", "isrid2searches4calpoly_output.csv")
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
COLLECTION_NAME = "ISRID_collection"

try:
    client = QdrantClient(url=QDRANT_URL)
    logging.info(f"Successfully connected to Qdrant at {QDRANT_URL}")
except Exception as e:
    logging.critical(f"Could not connect to Qdrant: {e}")
    exit(1)

def clean_dataset(rows: pd.DataFrame) -> List[str]:
    cleaned_rows = []
    for _, row in rows.iterrows():
        # Specific cleaning rules based on observed data issues
        row["Incident.Outcome"] = row["Incident.Outcome"].replace("/", " ")
        
        if "." in str(row["Age"]) and str(row["Age"]).split(".")[1] == "0":
            row["Age"] = str(row["Age"]).split(".")[0]

    #Convert to numeric to allow for searching by age in Qdrant
    rows["Age"] = pd.to_numeric(rows["Age"], errors="coerce")
    rows.fillna({"Age": 0}, inplace=True)
    rows.columns = [col.replace('.', '_') for col in rows.columns]


    for _, row in rows.iterrows():
        #removing the ".0" from any float that is actually an integer
        cleaned_row = ' '.join(row.astype(str).str.lower().str.strip()).replace(".0", "")
        cleaned_rows.append((cleaned_row, row.to_dict()))

    return cleaned_rows


def format_for_DB(row: List[str]) -> List[dict]:
    formatted_rows = []
    for row_str, row_dict in row:
        row_dict["Age"] = float(row_dict["Age"])
        formatted_entry = {
            "provenance": {
                "source": "ISRID Dataset",
                "author": "Bob Koester"
            },
            "content": row_str,
            "metadata": row_dict
        }
        formatted_rows.append(formatted_entry)
    return formatted_rows

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
    try:
        logging.info("Reading Isirid Dataset")
        isrid = pd.read_csv(ISRID_PATH, index_col=0)
    except FileNotFoundError as e:
        logging.critical(f"Couldn't find CSV dataset file: {e}")
        return
    except Exception as e:
        logging.critical(f"Error reading CSV file: {e}")

    cleaned_rows = clean_dataset(isrid)
    formatted_rows = format_for_DB(cleaned_rows)

    FILE_LOCATION = 'agents/history/data/formatted_isrid.json'
    with open(FILE_LOCATION, 'w', encoding='utf-8') as f:
        json.dump(formatted_rows, f, ensure_ascii=False, indent=4)

    logging.info(f"Finished formatting ISRID dataset. Saved to {FILE_LOCATION}")
    logging.info(f"Isrid dataset formatted for insertion to Qdrant vector DB")


    logging.info(f"attempting to insert ISRID dataset to Qdrant vector DB")
    
    points = []
    vectorizer = TfidfVectorizer()
    vectorized = vectorizer.fit_transform(
        [entry["content"] for entry in formatted_rows]
    )
    
    for idx, (row, vector) in enumerate(zip(formatted_rows, vectorized)):
        point = {
            "id": idx,
            "vector": vector.toarray().flatten().tolist(),
            "payload": row
        }
        points.append(point)

    VECTOR_SIZE = len(points[0]["vector"])

    try:
        FILE_LOCATION = 'agents/history/models/isrid_tfidf_vectorizer.joblib'
        dump(vectorizer, FILE_LOCATION)
        logging.info(f"Successfully saved vectorizer to {FILE_LOCATION}")
    except Exception as e:
        logging.critical(f"Failed to save vectorizer: {e}")
        logging.critical("Fixing this is critical as the vectorizer is needed for future queries")
        logging.critical("Exiting now to prevent further issues")
        exit(1)

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