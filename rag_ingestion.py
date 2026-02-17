import pymongo
import os
import sys
import re
import warnings
import time
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv
from tqdm import tqdm 
import google.generativeai as genai
from PyPDF2 import PdfReader
from gridfs import GridFS

# Suppress warnings
warnings.filterwarnings("ignore", category=UserWarning) 
warnings.filterwarnings("ignore", category=DeprecationWarning) 

# Load environment variables
# load_dotenv() - Handled by config
import config

# --- 1. CONFIGURATION & DATABASE CONNECTION ---

# Primary DB (Metadata) & Loading Config
MONGO_URI = config.MONGO_URI
DB_NAME = config.MONGO_DB_NAME 

if not MONGO_URI:
    print("[ERROR] MONGO_URI not found.")
    exit()

# Initialize Primary Client Early to load Config
try:
    client_meta = pymongo.MongoClient(MONGO_URI)
    db_meta = client_meta[DB_NAME]
    client_meta.admin.command('ismaster')
    print(f"[SUCCESS] Connected to Metadata DB: {DB_NAME}")
    
    # Initialize GridFS
    fs = GridFS(db_meta, collection="original_files_bucket")
    print(f"[SUCCESS] Connected to GridFS.")
except Exception as e:
    print(f"[ERROR] Error connecting to Metadata DB: {e}")
    exit()

# --- LOAD CONFIGURATION FROM MONGODB (llmConfig) ---
try:
    llm_config = db_meta["llmConfigs"].find_one({"config_id": "default_rag_config"}) or {}
    print(f"[INFO] Loaded configuration from llmConfig.")
except Exception as e:
    print(f"[WARNING] Failed to load llmConfig: {e}")
    llm_config = {}

# Helper to get config with priority: Env Var > DB > Default
def get_conf(key, default, cast_type=str):
    val = os.getenv(key) # 1. Environment Variable
    if val is None:
        val = llm_config.get(key) # 2. Database
    if val is None:
        return default # 3. Default
    try:
        return cast_type(val)
    except:
        return default

GOOGLE_API_KEY = get_conf("GOOGLE_API_KEY", "")
EMBEDDING_MODEL = get_conf("EMBEDDING_MODEL", "models/gemini-embedding-001")
# Ensure model name has 'models/' prefix for some versions of SDK, though simple name usually works
if not EMBEDDING_MODEL.startswith("models/"):
    EMBEDDING_MODEL = f"models/{EMBEDDING_MODEL}"

CHUNK_SIZE = get_conf("CHUNK_SIZE", 500, int)
CHUNK_OVERLAP = get_conf("CHUNK_OVERLAP", 50, int)
EMBEDDING_DIMENSIONS = 768 

print(f"[CONFIG] Model: {EMBEDDING_MODEL} | Chunk: {CHUNK_SIZE}/{CHUNK_OVERLAP}")

# Configure GenAI
if not GOOGLE_API_KEY:
    print("[ERROR] GOOGLE_API_KEY is missing.")
    exit()

genai.configure(api_key=GOOGLE_API_KEY)

# Secondary DB (RAG Vectors)
MONGO_RAG_URI = config.MONGO_RAG_URI
RAG_DB_NAME = config.MONGO_RAG_DB_NAME
VECTOR_COLLECTION_NAME = "ragChunks"

#Path
DATASET_ROOT_PATH = "./dataset" 

# --- 2. HELPERS ---

def get_utc_now():
    return datetime.now(timezone.utc)

class SimpleTextSplitter:
    def __init__(self, chunk_size, chunk_overlap):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def split_text(self, text):
        if not text:
            return []
        
        chunks = []
        start = 0
        text_len = len(text)
        
        while start < text_len:
            end = min(start + self.chunk_size, text_len)
            
            # Try to find a nice break point (newline or period) if we are not at end
            if end < text_len:
                # Look for last newline in the last 10% of the chunk
                lookback = int(self.chunk_size * 0.1)
                last_newline = text.rfind('\n', end - lookback, end)
                if last_newline != -1:
                    end = last_newline + 1
                else:
                    # Look for period
                    last_period = text.rfind('. ', end - lookback, end)
                    if last_period != -1:
                        end = last_period + 2 # Include period and space
            
            chunks.append(text[start:end])
            start += self.chunk_size - self.chunk_overlap
            
            # Avoid infinite loop if overlap >= size (bad config)
            if self.chunk_overlap >= self.chunk_size:
                start = end 
                
        return chunks

text_splitter = SimpleTextSplitter(CHUNK_SIZE, CHUNK_OVERLAP)


# --- 2.1 INITIALIZATION: VECTOR SEARCH INDEX ---

def create_vector_index(collection):
    """
    Attempts to create the Atlas Vector Search Index programmatically.
    """
    index_name = "default" 
    
    # Definition for Google Gemini (768 dim) + cosine similarity
    model = {
        "definition": {
            "fields": [
                {
                    "numDimensions": 768,
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
    
    print(f"[INFO] Checking/Creating Vector Search Index '{index_name}'...")
    try:
        # Check if index already exists 
        existing_indexes = list(collection.list_search_indexes())
        if any(idx.get("name") == index_name for idx in existing_indexes):
            print(f"[SUCCESS] Vector Search Index '{index_name}' already exists.")
            return

        collection.create_search_index(model)
        print(f"[SUCCESS] Vector Search Index '{index_name}' creation initiated.")
    except Exception as e:
        print(f"[WARNING] Automatic Index Creation Warning: {e}")

# Initialize Secondary MongoDB Client (Vectors)
try:
    if not MONGO_RAG_URI or "<INSERT" in MONGO_RAG_URI:
        raise ValueError("MONGO_RAG_URI is missing or invalid in .env")
        
    client_rag = pymongo.MongoClient(MONGO_RAG_URI)
    db_rag = client_rag[RAG_DB_NAME]
    client_rag.admin.command('ismaster')
    print(f"[SUCCESS] Connected to RAG Vector DB: {RAG_DB_NAME}")
    
    # Attempt to create index
    create_vector_index(db_rag[VECTOR_COLLECTION_NAME])
    
except Exception as e:
    print(f"[ERROR] Error connecting to RAG Vector DB: {e}")
    exit()

# --- 3. CORE RAG FUNCTIONS ---

def get_embedding(text):
    """Generates a vector embedding using Google GenAI SDK."""
    try:
        # Using the embed_content method directly
        result = genai.embed_content(
            model=EMBEDDING_MODEL,
            content=text,
            task_type="retrieval_document",
            title="Embedded Document",
            output_dimensionality=768 # Force 768 dimensions
        )
        return result['embedding']
    except Exception as e:
        # print(f"[EMBED ERROR] {e}") # Too noisy
        return None

def extract_text_and_split(abs_file_path):
    """Extracts text and returns chunks."""
    file_path = Path(abs_file_path)
    text_content = ""
    
    try:
        if file_path.suffix.lower() == '.pdf':
            reader = PdfReader(str(file_path))
            for page in reader.pages:
                text_content += page.extract_text() + "\n"
        elif file_path.suffix.lower() == '.txt':
            with open(file_path, 'r', encoding='utf-8') as f:
                text_content = f.read()
        else:
            return []
        
        return text_splitter.split_text(text_content)
        
    except Exception as e:
        print(f"⚠️ Could not load: {file_path.name}: {e}")
        return []

def process_and_insert_document(abs_file_path, relative_file_path, meta_data):
    """Embeds and Inserts document chunks into RAG MongoDB."""
    
    chunks = extract_text_and_split(abs_file_path)
    
    if not chunks:
        print(f" -> Skipped: No content for {relative_file_path}")
        return
        
    print(f"\nProcessing: {relative_file_path} ({len(chunks)} chunks)")

    vectors_to_insert = []
    
    # Batch embedding could be optimized, but ensuring strict rate limits is safer for free tier
    # We will do one by one or small batches. GenAI supports batching but sticking to simple loop for reliability.

    with tqdm(total=len(chunks), desc=f"Embedding {Path(relative_file_path).name}", unit="chunk") as pbar:
        for i, chunk_text in enumerate(chunks):
            
            if len(chunk_text.strip()) < 50: 
                pbar.update(1)
                continue 
            
            embedding_vector = get_embedding(chunk_text)
            
            if embedding_vector is None:
                # Retry once after small sleep
                time.sleep(1)
                embedding_vector = get_embedding(chunk_text)
                if embedding_vector is None:
                    pbar.update(1)
                    continue
            
            safe_id = f"{relative_file_path}_{i}".replace('.', '_').replace(' ', '_')
            
            chunk_doc = {
                "_id": safe_id,
                "text": chunk_text,
                "embedding": embedding_vector,
                "metadata": {
                    "source": relative_file_path,
                    "chunkIndex": i,
                    "dateCreated": get_utc_now(),
                    **meta_data
                }
            }
            vectors_to_insert.append(chunk_doc)
            pbar.update(1)
            time.sleep(0.2) # Avoid aggressive rate limiting

    if vectors_to_insert:
        try:
            try:
                db_rag[VECTOR_COLLECTION_NAME].insert_many(vectors_to_insert, ordered=False)
                new_count = len(vectors_to_insert)
            except pymongo.errors.BulkWriteError as bwe:
                new_count = bwe.details['nInserted']
            
            print(f"[SUCCESS] Inserted {new_count} chunks to RAG DB.")
            
            # Update Primary Metadata DB
            db_meta["datasets"].update_one(
                {"filePath": relative_file_path},
                {"$set": {"status": "INDEXED", "indexingDate": get_utc_now()}}
            )
            print(f"[SUCCESS] Updated status to INDEXED.")
            
        except Exception as e:
            print(f"[ERROR] Failed to insert chunks: {e}")

# --- 4. MAIN INGESTION PIPELINE ---

def run_ingestion_pipeline():
    """Scans dataset, processes unindexed files."""
    
    if not Path(DATASET_ROOT_PATH).exists():
        Path(DATASET_ROOT_PATH).mkdir(parents=True, exist_ok=True)
        # print(f"[ERROR] Error: Dataset path not found.")
        # return

    # Check for Target Files Filter (Selective Indexing)
    target_files_env = config.TARGET_FILES_LIST
    target_files_set = None
    if target_files_env:
        target_files_set = set(target_files_env.split(','))
        print(f"[INFO] Selective Indexing Active: Targeting {len(target_files_set)} files.")
        
        # GridFS Sync Logic for Targeted Files
        for relative_path in target_files_set:
            local_path = Path(DATASET_ROOT_PATH) / relative_path
            
            if not local_path.exists():
                print(f"[SYNC] File not found locally: {relative_path}. Attempting GridFS download...")
                try:
                    grid_file = fs.find_one({"filename": relative_path})
                    if grid_file:
                        # Ensure parent dirs exist
                        local_path.parent.mkdir(parents=True, exist_ok=True)
                        with open(local_path, 'wb') as f:
                            f.write(grid_file.read())
                        print(f"[SYNC] Downloaded {relative_path} from GridFS.")
                    else:
                        print(f"[WARNING] File not found in GridFS either: {relative_path}")
                except Exception as e:
                    print(f"[ERROR] Failed to download {relative_path}: {e}")

    files_to_process = []
    for root, _, files in os.walk(DATASET_ROOT_PATH):
        root_path = Path(root)
        
        if 'Quran' in root_path.parts:
            data_type = "Quran"
        elif 'Tafsirs' in root_path.parts:
            data_type = "Tafsir"
        else:
            data_type = "General"

        for file_name in files:
            abs_file_path = root_path / file_name
            relative_file_path = str(abs_file_path.relative_to(DATASET_ROOT_PATH)).replace('\\', '/')
            
            # 1. Selective Filter Check
            if target_files_set and relative_file_path not in target_files_set:
                continue

            # Check Status in Primary DB
            status_doc = db_meta["datasets"].find_one({"filePath": relative_file_path})
            
            if status_doc and status_doc.get("status") == "INDEXED":
                 continue
                
            # Prepare metadata
            meta_data = {"dataType": data_type}
            if data_type == "Tafsir":
                path_parts = relative_file_path.split('/')
                try:
                    tafsir_name = path_parts[1] 
                    meta_data["tafsirName"] = tafsir_name
                except:
                    pass
                
                volume_match = re.search(r'Vol(\d+)', file_name, re.IGNORECASE)
                if volume_match:
                    meta_data["volume"] = int(volume_match.group(1))

            files_to_process.append((abs_file_path, relative_file_path, meta_data))


    print(f"Found {len(files_to_process)} files to ingest.")
    total_files = len(files_to_process)
    
    for i, (abs_path, rel_path, meta) in enumerate(files_to_process):
        print(f"[UI_PROGRESS] {i+1}/{total_files}")
        sys.stdout.flush() 
        
        # Upsert Metadata PENDING
        db_meta["datasets"].update_one(
            {"filePath": rel_path},
            {"$set": {"dataType": meta['dataType'], "fileName": Path(rel_path).name, "status": "PENDING"},
             "$setOnInsert": {"indexingDate": None, "metaData": meta}},
            upsert=True
        )
        
        process_and_insert_document(abs_path, rel_path, meta)


if __name__ == "__main__":
    if not MONGO_URI or not DB_NAME:
        print("Missing Primary DB Config.")
    elif not MONGO_RAG_URI or not RAG_DB_NAME:
         print("Missing RAG DB Config.")
    elif not GOOGLE_API_KEY:
        print("Missing GOOGLE_API_KEY.")
    else:
        run_ingestion_pipeline()
    
    client_meta.close()
    if 'client_rag' in locals():
        client_rag.close()
    print("\n[INFO] Connections closed.")