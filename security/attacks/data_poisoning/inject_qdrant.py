"""
Data Poisoning — Qdrant Injection Module

Manages SAR_collection state for the data-poisoning experiment:

  reset_collection()          — delete + recreate SAR_collection
  inject_clean()              — load 10 factually correct SAR chunks
  inject_poisoned(payload)    — add 3 poisoned chunks (A or B) alongside clean chunks

Usage (standalone):
    python inject_qdrant.py --mode clean
    python inject_qdrant.py --mode poison --payload A
    python inject_qdrant.py --mode poison --payload B
    python inject_qdrant.py --mode reset
"""

import argparse
import sys
from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from sentence_transformers import SentenceTransformer

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from security.attacks.data_poisoning.generate_clean_chunks import get_clean_chunks
from security.attacks.data_poisoning.generate_poisoned_chunks import (
    get_payload_a_chunks,
    get_payload_b_chunks,
)

QDRANT_URL = "http://localhost:6333"
COLLECTION_NAME = "SAR_collection"
VECTOR_SIZE = 384  # all-MiniLM-L6-v2

_client: QdrantClient | None = None
_model: SentenceTransformer | None = None


def _get_client() -> QdrantClient:
    global _client
    if _client is None:
        _client = QdrantClient(url=QDRANT_URL)
    return _client


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        print("[*] Loading sentence-transformer model…")
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model


def reset_collection() -> None:
    client = _get_client()
    existing = {c.name for c in client.get_collections().collections}
    if COLLECTION_NAME in existing:
        client.delete_collection(COLLECTION_NAME)
        print(f"[*] Deleted existing {COLLECTION_NAME}")
    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
    )
    print(f"[+] Created fresh {COLLECTION_NAME}")


def _upsert_chunks(chunks: list[dict], id_offset: int = 0) -> int:
    client = _get_client()
    model = _get_model()

    points = []
    for i, chunk in enumerate(chunks):
        embedding = model.encode(chunk["content"]).tolist()
        points.append(
            PointStruct(
                id=id_offset + i,
                vector=embedding,
                payload={
                    "provenance": chunk["provenance"],
                    "content": chunk["content"],
                },
            )
        )
    client.upsert(collection_name=COLLECTION_NAME, wait=True, points=points)
    return len(points)


def inject_clean() -> int:
    chunks = get_clean_chunks()
    n = _upsert_chunks(chunks, id_offset=0)
    print(f"[+] Inserted {n} clean chunks into {COLLECTION_NAME}")
    return n


def inject_poisoned(payload_type: str) -> int:
    payload_type = payload_type.upper()
    if payload_type == "A":
        chunks = get_payload_a_chunks()
    elif payload_type == "B":
        chunks = get_payload_b_chunks()
    else:
        raise ValueError(f"Unknown payload type: {payload_type!r}. Use 'A' or 'B'.")

    # Use high IDs so they don't collide with clean chunk IDs (0-9)
    client = _get_client()
    offset = client.count(collection_name=COLLECTION_NAME).count
    n = _upsert_chunks(chunks, id_offset=offset)
    print(f"[+] Inserted {n} Payload {payload_type} poisoned chunks into {COLLECTION_NAME}")
    return n


def collection_point_count() -> int:
    return _get_client().count(collection_name=COLLECTION_NAME).count


def main():
    parser = argparse.ArgumentParser(description="SAR_collection injection tool")
    parser.add_argument(
        "--mode",
        choices=["clean", "poison", "reset"],
        required=True,
        help="clean: insert clean baseline; poison: insert poisoned chunks; reset: wipe collection",
    )
    parser.add_argument(
        "--payload",
        choices=["A", "B"],
        help="Which poisoned payload to inject (required when --mode poison)",
    )
    args = parser.parse_args()

    if args.mode == "reset":
        reset_collection()
    elif args.mode == "clean":
        reset_collection()
        inject_clean()
        print(f"[*] Total points: {collection_point_count()}")
    elif args.mode == "poison":
        if not args.payload:
            parser.error("--payload A or B is required with --mode poison")
        reset_collection()
        inject_clean()
        inject_poisoned(args.payload)
        print(f"[*] Total points: {collection_point_count()}")


if __name__ == "__main__":
    main()
