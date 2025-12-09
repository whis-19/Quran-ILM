import pymongo
import os
from datetime import datetime
from pathlib import Path
from gridfs import GridFS
from tqdm import tqdm
import config

# --- 1. CONFIGURATION ---

# Read from CONFIG
MONGO_URI = config.MONGO_URI
DB_NAME = config.MONGO_DB_NAME 

# --- PATH & COLLECTION NAMES ---
DATASET_ROOT_PATH = "./dataset" 
GRIDFS_BUCKET_NAME = "original_files_bucket" # GridFS creates fs.files and fs.chunks collections

# --- 2. INITIALIZATION ---

# Initialize MongoDB Client
try:
    client = pymongo.MongoClient(MONGO_URI)
    db = client[DB_NAME]
    client.admin.command('ismaster')
    print(f"Connected to MongoDB Atlas DB: {DB_NAME}")
except Exception as e:
    print(f"Error connecting to MongoDB: {e}")
    exit()

# Initialize GridFS Instance
# This implicitly creates the collections (fs.files and fs.chunks) if they don't exist
fs = GridFS(db, collection=GRIDFS_BUCKET_NAME) 
print(f"Initialized GridFS with bucket name: {GRIDFS_BUCKET_NAME}")

# --- 3. CORE UPLOAD FUNCTION ---

def upload_file_to_gridfs(abs_file_path, relative_file_path):
    """
    Uploads a single file to GridFS, using the relative path as the filename 
    and ensuring it's not uploaded if the filename already exists.
    """
    
    abs_path = Path(abs_file_path)
    
    # 1. Check if the file already exists in GridFS (based on the relative path/filename)
    if fs.exists({"filename": relative_file_path}):
        print(f" -> Skipping {relative_file_path}: Already exists in GridFS.")
        return 0
    
    # 2. Upload the file
    try:
        # GridFS handles opening the file in binary mode and chunking automatically
        with open(abs_path, 'rb') as file_data:
            file_id = fs.put(
                file_data, 
                filename=relative_file_path,
                contentType=f"application/{abs_path.suffix.strip('.')}", # e.g., application/pdf
                # Store the absolute path as metadata for easier debugging
                metadata={"absolute_path": str(abs_path), "upload_date": datetime.utcnow()}
            )

        # 3. Sync with 'datasets' collection
        dataset_meta = {
            "filePath": relative_file_path,
            "filename": relative_file_path, # Redundant but useful
            "dataType": "Ingested",
            "fileId": str(file_id),
            "uploadDate": datetime.utcnow(),
            "status": "PENDING", # RAG status
            "indexingDate": None,
            "metaData": {
                "source": "gridfs_ingestion_script",
                "original_path": str(abs_path)
            }
        }
        
        db["datasets"].update_one(
            {"filePath": relative_file_path},
            {"$set": dataset_meta},
            upsert=True
        )
        
        print(f"Uploaded {relative_file_path} with File ID: {file_id} and synced to 'datasets'")
        return 1
        
    except Exception as e:
        print(f"Failed to upload {relative_file_path} to GridFS: {e}")
        return 0

# --- 4. MAIN INGESTION PIPELINE ---

def run_gridfs_pipeline():
    """Scans the dataset directory and uploads all files to GridFS."""
    
    if not Path(DATASET_ROOT_PATH).exists():
        print(f"Error: Dataset path not found: {DATASET_ROOT_PATH}.")
        return

    # Ensure Indexes on datasets collection for fast lookup
    print("Creating indexes on 'datasets' collection...")
    try:
        db["datasets"].create_index("filePath", unique=True)
        db["datasets"].create_index("status")
        print("Indexes checked/created.")
    except Exception as e:
        print(f"Warning: Index creation failed (potentially already exists): {e}")

    files_to_upload = []
    
    # First pass: Collect all files and determine total count for tqdm
    for root, _, files in os.walk(DATASET_ROOT_PATH):
        root_path = Path(root)
        
        for file_name in files:
            abs_file_path = root_path / file_name
            # Use the relative path as the unique filename key in GridFS
            relative_file_path = str(abs_file_path.relative_to(DATASET_ROOT_PATH)).replace('\\', '/')
            files_to_upload.append((abs_file_path, relative_file_path))

    total_files = len(files_to_upload)
    uploaded_count = 0
    
    # Second pass: Upload files with tqdm bar
    with tqdm(total=total_files, desc="GridFS Upload Progress", unit="file") as pbar:
        for abs_path, rel_path in files_to_upload:
            uploaded = upload_file_to_gridfs(abs_path, rel_path)
            uploaded_count += uploaded
            pbar.update(1)

    print(f"\n--- GridFS Upload Summary ---")
    print(f"Total files found in directory: {total_files}")
    print(f"Total new files uploaded: {uploaded_count}")
    print(f"Total files currently in GridFS (files collection): {db[f'{GRIDFS_BUCKET_NAME}.files'].count_documents({})}")


if __name__ == "__main__":
    
    if not MONGO_URI or not DB_NAME:
        print("FATAL ERROR: MONGO_URI or DB_NAME is missing from the environment.")
    else:
        run_gridfs_pipeline()
    
    client.close()
    print("\n🔒 MongoDB connection closed. GridFS ingestion complete.")