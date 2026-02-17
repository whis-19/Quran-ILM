import pymongo
import os
import config

# --- Configuration ---
MONGO_URI = config.MONGO_URI
DB_NAME = config.MONGO_DB_NAME

# Default Settings to Upload
DEFAULT_CONFIG = {
    "config_id": "default_rag_config", # Unique ID to ensure singleton config
    "GOOGLE_API_KEY": config.GOOGLE_API_KEY, # Load from env or leave empty for user to fill
    "LLM_MODEL": "gemini-2.5-flash",
    "EMBEDDING_MODEL": "gemini-embedding-001",
    "CHUNK_SIZE": 500,
    "CHUNK_OVERLAP": 50
}

def upload_config():
    if not MONGO_URI:
        print("❌ Error: MONGO_URI not found in environment variables.")
        return

    try:
        # Connect to MongoDB
        client = pymongo.MongoClient(MONGO_URI)
        db = client[DB_NAME]
        collection = db["llmConfigs"]
        
        print(f"✅ Connected to DB: {DB_NAME}")
        
        # Upsert configuration (Update if exists, Insert if not)
        result = collection.update_one(
            {"config_id": "default_rag_config"},
            {"$set": DEFAULT_CONFIG},
            upsert=True
        )
        
        if result.upserted_id:
            print("✅ Successfully CREATED new RAG configuration.")
        else:
            print("✅ Successfully UPDATED existing RAG configuration.")
            
        print("\n--- Current Configuration in DB ---")
        print(DEFAULT_CONFIG)
        
    except Exception as e:
        print(f"❌ Error uploading config: {e}")
    finally:
        client.close()

if __name__ == "__main__":
    upload_config()
