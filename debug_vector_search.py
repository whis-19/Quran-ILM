
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
        print("Sample document structure:")
        doc = collection.find_one({})
        print(f"Keys: {list(doc.keys())}")
        if 'embedding' in doc:
            print(f"Embedding length: {len(doc['embedding'])}")
            # Check first few elements
            print(f"Embedding sample: {doc['embedding'][:5]}...")
        else:
            print("WARNING: 'embedding' field missing!")
            
        if 'metadata' in doc:
            print(f"Metadata: {doc['metadata']}")

except Exception as e:
    print(f"Error listing indexes: {e}")

# Try a dummy search
try:
    print("\n--- Attempting Real Vector Search ('Bismillah') ---")
    
    # Configure GenAI
    import google.generativeai as genai
    apiKey = config.get_env("GOOGLE_API_KEY")
    if not apiKey:
        print("API Key missing")
        exit()
        
    genai.configure(api_key=apiKey)
    
    # Generate Embedding
    model = "models/gemini-embedding-001" # Or pull from config
    print(f"Embedding query with {model}...")
    
    embedding_result = genai.embed_content(
        model=model,
        content="What is the significance of Bismillah?",
        task_type="retrieval_query",
        output_dimensionality=3072
    )
    query_vector = embedding_result['embedding']
    print(f"Generated Vector Length: {len(query_vector)}")
    
    pipeline = [
        {
            "$vectorSearch": {
                "index": "default", 
                "path": "embedding",
                "queryVector": query_vector,
                "numCandidates": 100, 
                "limit": 5
            }
        },
        {
            "$project": {
                "_id": 0,
                "text": 1,
                "score": {"$meta": "vectorSearchScore"}
            }
        }
    ]
    
    results = list(collection.aggregate(pipeline))
    print(f"\nSearch successful. Found {len(results)} results.")
    
    for i, doc in enumerate(results):
        print(f"\nResult {i+1} (Score: {doc.get('score', 0):.4f}):")
        print(f"Text: {doc.get('text', '')[:200]}...") # truncate
        
except Exception as e:
    print(f"\n[ERROR] Search Failed:\n{e}")
