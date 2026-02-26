import streamlit as st
import pymongo
from gridfs import GridFS
from . import config

# --- Configuration ---
GRIDFS_BUCKET_NAME = "original_files_bucket"

# --- Initialization ---
@st.cache_resource(ttl=None)
def init_connection():
    try:
        mongo_uri = config.MONGO_URI
        db_name = config.MONGO_DB_NAME
        
        if not mongo_uri:
            raise ValueError("MongoDB URI not found.")
        
        client = pymongo.MongoClient(mongo_uri)
        db = client[db_name]
        fs = GridFS(db, collection=GRIDFS_BUCKET_NAME)
        return client, db, fs
    except Exception as e:
        st.error(f"Failed to connect to MongoDB Atlas: {e}")
        return None, None, None

def normalize_path(path):
    return path.strip("/").replace("\\", "/")

def delete_files(file_paths_to_delete, db, fs):
    """Deletes files from GridFS, datasets collection, AND RAG vector chunks."""
    deleted_count = 0
    errors = []
    
    # Connect to RAG DB for vector deletion
    client_rag = None
    db_rag = None
    try:
        rag_uri = config.MONGO_RAG_URI
        rag_db_name = config.MONGO_RAG_DB_NAME
        if rag_uri and "<INSERT" not in rag_uri:
            client_rag = pymongo.MongoClient(rag_uri)
            db_rag = client_rag[rag_db_name]
    except Exception as e:
        errors.append(f"Could not connect to RAG DB for deletion: {e}")

    for file_path in file_paths_to_delete:
        try:
            # 1. Delete from GridFS
            # Find file_id first
            gridfs_file = fs.find_one({"filename": file_path})
            if gridfs_file:
                fs.delete(gridfs_file._id)
            
            # 2. Delete from datasets collection (Metadata)
            db["datasets"].delete_one({"filePath": file_path})
            
            # 3. Delete from RAG DB (Vectors)
            if db_rag is not None:
                # Assuming 'ragChunks' is the collection name and 'metadata.source' stores the path
                result = db_rag["ragChunks"].delete_many({"metadata.source": file_path})
                # print(f"Deleted {result.deleted_count} chunks for {file_path}")

            deleted_count += 1
        except Exception as e:
            errors.append(f"Error deleting {file_path}: {e}")
            
    if client_rag is not None:
        client_rag.close()
            
    return deleted_count, errors
