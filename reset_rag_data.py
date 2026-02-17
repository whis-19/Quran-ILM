
import pymongo
import config
import sys

# Connect to DBs
mongo_uri = config.MONGO_URI
db_name = config.MONGO_DB_NAME
mongo_rag_uri = config.MONGO_RAG_URI
rag_db_name = config.MONGO_RAG_DB_NAME
vector_collection_name = "ragChunks"

if not mongo_uri or not mongo_rag_uri:
    print("Error: Missing MONGO_URI or MONGO_RAG_URI")
    sys.exit(1)

client_meta = pymongo.MongoClient(mongo_uri)
db_meta = client_meta[db_name]

client_rag = pymongo.MongoClient(mongo_rag_uri)
db_rag = client_rag[rag_db_name]
collection_rag = db_rag[vector_collection_name]

print("--- RAG Data Reset Tool ---")

# 1. Clear Vector Collection
count = collection_rag.count_documents({})
print(f"Found {count} documents in {vector_collection_name}.")
if count > 0:
    print(f"Deleting {count} documents from {vector_collection_name}...")
    collection_rag.delete_many({})
    print("Deletion complete.")
else:
    print("Vector collection is already empty.")

# 2. Reset Metadata Status
print("Resetting 'datasets' status to PENDING...")
result = db_meta["datasets"].update_many(
    {}, 
    {"$set": {"status": "PENDING", "indexingDate": None}}
)
print(f"Updated {result.modified_count} documents in 'datasets'.")

print("\n[SUCCESS] RAG data reset. You can now run the ingestion script to re-index with correct dimensions.")
