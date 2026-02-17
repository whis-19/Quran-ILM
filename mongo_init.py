import pymongo
import os
from pymongo.operations import SearchIndexModel
from datetime import datetime, timezone
import config

# --- 1. CONFIGURATION (READ FROM CONFIG) ---
MONGO_URI = config.MONGO_URI
DB_NAME = config.MONGO_DB_NAME 

# --- COLLECTION NAMES ---
COLLECTION_CHATS = "chats"
COLLECTION_DATASETS = "datasets"
COLLECTION_LLM_CONFIGS = "llmConfigs"
COLLECTION_VOICE_REC = "voiceRecitations"
COLLECTION_VECTOR = "ragChunks"

# --- VECTOR CONFIGURATION (Must match your chosen model: gemini-embedding-001) ---
EMBEDDING_DIMENSIONS = 768 

# --- 2. CONNECT TO MONGODB ---
print(f"Attempting to connect to DB: {DB_NAME} using URI from environment...")

try:
    client = pymongo.MongoClient(MONGO_URI)
    db = client[DB_NAME]
    # Check connection status
    client.admin.command('ismaster') 
    print(f"✅ Successfully connected to MongoDB and database: {DB_NAME}")
except Exception as e:
    print(f"❌ Error connecting to MongoDB. Please check MONGO_URI and network settings: {e}")
    exit()

# Helper function
def get_utc_now():
    return datetime.now(timezone.utc)

# --- 3. EXPLICIT COLLECTION CREATION ---

def create_collections():
    """Explicitly creates collections for a clean setup."""
    collections_to_create = [
        COLLECTION_CHATS,
        COLLECTION_DATASETS,
        COLLECTION_LLM_CONFIGS,
        COLLECTION_VOICE_REC,
        COLLECTION_VECTOR
    ]
    
    existing_collections = db.list_collection_names()
    
    print("\n--- Creating Collections ---")
    for name in collections_to_create:
        if name not in existing_collections:
            # Explicitly create the collection
            db.create_collection(name)
            print(f"✅ Collection '{name}' created.")
        else:
            print(f"🔄 Collection '{name}' already exists.")

# --- 4. INDEX DEFINITION FOR PERFORMANCE ---

def setup_standard_indexes():
    """Sets up standard B-Tree indexes for fast lookups and uniqueness."""
    print("\n--- Setting up Standard B-Tree Indexes ---")
    
    # Chats Collection: Group conversations and sort by time
    db[COLLECTION_CHATS].create_index([("sessionId", pymongo.ASCENDING)], name="session_id_idx")
    db[COLLECTION_CHATS].create_index([("timestamp", pymongo.DESCENDING)], name="timestamp_desc_idx")
    
    # Datasets Collection: Ensure files are tracked uniquely and index by status
    db[COLLECTION_DATASETS].create_index([("filePath", pymongo.ASCENDING)], unique=True, name="filepath_unique_idx")
    db[COLLECTION_DATASETS].create_index([("status", pymongo.ASCENDING)], name="status_idx")
    
    # LLM Configs Collection: Ensure only one configuration per name
    db[COLLECTION_LLM_CONFIGS].create_index([("configName", pymongo.ASCENDING)], unique=True, name="config_name_unique_idx")
    
    # Voice Recitations Collection
    db[COLLECTION_VOICE_REC].create_index([("userId", pymongo.ASCENDING)], name="user_id_idx")
    
    print(f"✅ All standard B-Tree indexes created.")

# --- 5. VECTOR SEARCH INDEX SETUP ---

def setup_vector_index():
    """Creates the specialized Vector Search Index on the 'ragChunks' collection."""
    print(f"\n--- Setting up Vector Search Index on '{COLLECTION_VECTOR}' ({EMBEDDING_DIMENSIONS} dims) ---")
    
    vector_index_name = f"vector_index_rag_{EMBEDDING_DIMENSIONS}d"
    collection = db[COLLECTION_VECTOR]
    
    search_index_model = SearchIndexModel(
        definition={
            "fields": [
                {
                    "type": "vector",
                    "path": "embedding",
                    "numDimensions": EMBEDDING_DIMENSIONS,
                    "similarity": "cosine" 
                },
                # Filter paths allow for fast metadata filtering
                {
                    "type": "filter",
                    "path": "sourceFile" 
                },
                {
                    "type": "filter",
                    "path": "metaData.tafsirName" 
                }
            ]
        },
        name=vector_index_name,
        type="vectorSearch"
    )
    
    try:
        # This command initiates the specialized index build on MongoDB Atlas
        collection.create_search_index(model=search_index_model)
        print(f"✅ Vector index '{vector_index_name}' initiated. It will build in the background.")
        
    except pymongo.errors.OperationFailure as e:
        if "already exists" in str(e):
            print(f"🔄 Vector index '{vector_index_name}' already exists.")
        else:
            print(f"❌ Error creating vector index: {e}")

# --- 6. EXECUTE SETUP ---

if __name__ == "__main__":
    
    # 6.1 Create Collections
    create_collections()
    
    # 6.2 Setup Standard Indexes
    setup_standard_indexes()

    # 6.3 Setup Vector Index
    setup_vector_index()
    
    client.close()
    print("\n🔒 MongoDB connection closed. Database structure is complete and ready for ingestion.")