
import pymongo
from utils import config
import sys
import time

# Load config
mongo_rag_uri = config.MONGO_RAG_URI
rag_db_name = config.MONGO_RAG_DB_NAME
vector_collection_name = "ragChunks"

if not mongo_rag_uri:
    print("Error: MONGO_RAG_URI not found.")
    sys.exit(1)

client = pymongo.MongoClient(mongo_rag_uri)
db = client[rag_db_name]
collection = db[vector_collection_name]

print(f"Connected to {rag_db_name}.{vector_collection_name}")

index_name = "default"
new_dimensions = 3072

# Definition for 3072 dims
model = {
    "definition": {
        "fields": [
            {
                "numDimensions": new_dimensions,
                "path": "embedding",
                "similarity": "cosine",
                "type": "vector"
            },
            {
                "path": "metadata.sourceFile",
                "type": "filter"
            }
        ]
    },
    "name": index_name,
    "type": "vectorSearch"
}

try:
    print(f"Checking existing indexes...")
    indexes = list(collection.list_search_indexes())
    idx_names = [i.get("name") for i in indexes]
    
    if index_name in idx_names:
        print(f"Index '{index_name}' exists. Dropping it to update definition...")
        collection.drop_search_index(index_name)
        print("Drop command sent. Waiting 30 seconds for probagation...")
        time.sleep(30)
    
    print(f"Creating new Vector Search Index '{index_name}' with {new_dimensions} dimensions...")
    collection.create_search_index(model)
    print("Creation initiated. Note: Indexing may take a minute to complete on Atlas.")

except Exception as e:
    print(f"[ERROR] Failed to update index: {e}")
