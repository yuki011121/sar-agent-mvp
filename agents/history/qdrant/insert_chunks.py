from sentence_transformers import SentenceTransformer
import json
from xmlrpc import client
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams
from qdrant_client.models import PointStruct

client = QdrantClient(url="http://localhost:6333")
COLLECTION_NAME = "SAR_collection"
VECTOR_SIZE = 384  # vector size for model all-MiniLM-L6-v2
EXTRACTED_FILE_PATHS = [
                        # "./example.json"
                        # "path/to/extracted_chunks.json",
                        ]

def create_collection():
    collections = client.get_collections().collections
    collection_names = [c.name for c in collections]

    if COLLECTION_NAME in collection_names:
        print(f"Collection {COLLECTION_NAME} exists")
    else:
        print(f"Creating Collection: {COLLECTION_NAME}")
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
        )
    
def create_embeddings(model):
    files_embeddings = []
    for file in EXTRACTED_FILE_PATHS:
        print(f"Creating embeddings for {file}...")
        embeddings = []
        with open(file, "r") as f:
            data = json.load(f)
            for chunk in data:
                text = chunk["content"]
                embedding = model.encode(text).tolist()  # Convert numpy array to list
                embeddings.append(embedding)
        files_embeddings.append(embeddings)
    return files_embeddings

def main():
    # 1. Load a pretrained Sentence Transformer model
    model = SentenceTransformer("all-MiniLM-L6-v2")

    create_collection()

    # 2. Create embeddings for the extracted chunks
    file_embeddings = create_embeddings(model)

    for embedding, data in zip(file_embeddings, EXTRACTED_FILE_PATHS):
        print(f"Embedding and uploading chunks from {data} to Qdrant...")
        with open(data, "r", encoding="utf-8") as f:
            chunks = json.load(f)
            points = []
            offset = client.count(collection_name=COLLECTION_NAME).count

            for i, (chunk, vector) in enumerate(zip(chunks, embedding)):
                point = PointStruct(
                    id=i + offset,
                    vector=vector,
                    payload={
                        "provenance": chunk["provenance"],
                        "content": chunk["content"]
                    }
                )
                points.append(point)
            client.upsert(
                collection_name=COLLECTION_NAME,
                wait=True,
                points=points
            )
    pass

if __name__ == '__main__':
    main()