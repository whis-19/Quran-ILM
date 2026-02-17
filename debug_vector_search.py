
import pymongo
import os
import config
import google.generativeai as genai
import sys

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

# List indexes
print("\n--- Existing Search Indexes ---")
try:
    indexes = list(collection.list_search_indexes())
    for idx in indexes:
        print(idx)
    if not indexes:
        print("No search indexes found!")
    
    count = collection.count_documents({})
    print(f"\nTotal documents in collection: {count}")

    if count > 0:
        print("Sample document:")
        print(collection.find_one({}, {"embedding": 0})) # Hide embedding for brevity

except Exception as e:
    print(f"Error listing indexes: {e}")

# Try a dummy search
try:
    print("\n--- Attempting Dummy Vector Search ---")
    # Dummy 768-dim vector (non-zero)
    dummy_vector = [0.1] * 768
    
    pipeline = [
        {
            "$vectorSearch": {
                "index": "default", 
                "path": "embedding",
                "queryVector": dummy_vector,
                "numCandidates": 10, 
                "limit": 1
            }
        },
        {
            "$project": {
                "_id": 0,
                "score": {"$meta": "vectorSearchScore"}
            }
        }
    ]
    
    results = list(collection.aggregate(pipeline))
    print(f"Search successful. Found {len(results)} results.")
except Exception as e:
    print(f"\n[ERROR] Search Failed:\n{e}")

