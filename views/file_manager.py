import streamlit as st
import time
import pandas as pd
from datetime import datetime
from utils.admin_utils import init_connection, normalize_path, delete_files
import os
import pymongo
import subprocess
import sys
from utils import config

# st.set_page_config(page_title="File Manager", page_icon="📂", layout="wide")

# --- AUTH CHECK ---
if not st.session_state.get("authenticated"):
    st.switch_page("Home.py")
    st.stop()
if st.session_state.role != "admin":
    st.error("Unauthorized Access: Admins Only.")
    st.stop()
# ------------------

st.title("File Manager")

# Connect
client, db, fs = init_connection()

if not client:
    st.error("Database connection failed.")
    st.stop()

# --- UPLOAD SECTION ---
st.subheader("⬆️ Upload Files")

with st.expander("Upload Settings & File Select", expanded=True):
    col1, col2 = st.columns([1, 2])
    
    with col1:
        target_folder = st.text_input(
            "Target Folder (Optional)", 
            placeholder="e.g., quran/tafsir",
            help="Files will be stored as 'folder/filename.pdf'"
        ).strip()
        
    with col2:
        uploaded_files = st.file_uploader(
            "Select PDF or TXT files:",
            type=["pdf", "txt"],
            accept_multiple_files=True
        )

    if uploaded_files and st.button("Start GridFS Upload", type="primary"):
        success_count = 0
        progress_bar = st.progress(0)
        status_text = st.empty()
        total_files = len(uploaded_files)
        
        for i, file in enumerate(uploaded_files):
            status_text.text(f"Processing {i+1}/{total_files}: {file.name}")
            
            # Construct full path
            clean_filename = file.name
            if target_folder:
                full_rel_path = f"{normalize_path(target_folder)}/{clean_filename}"
            else:
                full_rel_path = clean_filename
            
            # Check existance
            if fs.exists({"filename": full_rel_path}):
                st.warning(f"Skipped '{full_rel_path}': Already exists.")
                progress_bar.progress((i + 1) / total_files)
                continue

            try:
                # Upload to GridFS
                file_id = fs.put(
                    file, 
                    filename=full_rel_path,
                    contentType=f"application/{file.name.split('.')[-1]}",
                    metadata={"source": "streamlit_upload"}
                )
                
                # Sync to datasets collection
                dataset_meta = {
                    "filePath": full_rel_path,
                    "filename": full_rel_path,
                    "dataType": "Uploaded",
                    "fileId": str(file_id),
                    "uploadDate": datetime.utcnow(),
                    "status": "PENDING",
                    "indexingDate": None,
                    "metaData": {
                        "source": "streamlit_upload",
                        "uploaded_by": "admin"
                    }
                }
                
                db["datasets"].update_one(
                    {"filePath": full_rel_path},
                    {"$set": dataset_meta},
                    upsert=True
                )
                success_count += 1
                
            except Exception as e:
                st.error(f"Failed to upload {full_rel_path}: {e}")
            
            progress_bar.progress((i + 1) / total_files)

        status_text.text("Done!")
        if success_count > 0:
            st.success(f"Successfully uploaded {success_count} files!")
            st.cache_data.clear()
            st.rerun()

# --- MANAGEMENT SECTION ---
st.divider()
st.subheader("📋 Dataset Inventory")

# --- RAG DB Sync Logic ---
rag_indexed_files = set()
try:
    # Connect to RAG DB to check actual status
    rag_uri = config.MONGO_RAG_URI
    rag_db_name = config.MONGO_RAG_DB_NAME
    
    if rag_uri and "<INSERT" not in rag_uri:
        client_rag = pymongo.MongoClient(rag_uri)
        db_rag = client_rag[rag_db_name]
        # Get list of files that have chunks
        distinct_sources = db_rag["ragChunks"].distinct("metadata.source")
        rag_indexed_files = set(distinct_sources)
        client_rag.close()
except Exception as e:
    st.warning(f"Could not sync with RAG DB: {e}")

# --- Fetch Primary Metadata ---
metadata_cursor = db["datasets"].find({}, {"_id": 0, "filePath": 1, "status": 1, "dataType": 1, "uploadDate": 1})
data = list(metadata_cursor)

if not data:
    st.info("No files found in the dataset.")
else:
    df = pd.DataFrame(data)
    
    # 1. Ensure Columns Exist
    required_cols = ["filePath", "status", "dataType", "uploadDate"]
    for col in required_cols:
        if col not in df.columns:
            df[col] = None

    # 2. Sync Status with RAG DB
    def get_synced_status(row):
        if row["filePath"] in rag_indexed_files:
            return "INDEXED"
        return row.get("status", "PENDING")

    df["status"] = df.apply(get_synced_status, axis=1)

    # Helper column for display
    df["Selected"] = False
    
    # Reorder columns
    df = df[["Selected", "filePath", "status", "dataType", "uploadDate"]]

    # Display Data Editor with Selection
    edited_df = st.data_editor(
        df,
        column_config={
            "Selected": st.column_config.CheckboxColumn(
                "Select",
                help="Select files to delete",
                default=False,
            ),
            "filePath": "File Name / Path",
            "status": "RAG Status",
            "uploadDate": st.column_config.DatetimeColumn("Uploaded At", format="D MMM YYYY, h:mm a"),
        },
        disabled=["filePath", "status", "dataType", "uploadDate"],
        hide_index=True,
        width='stretch',  # Updated as per warning
        key="data_editor"
    )

    # Actions on Selected Rows
    selected_rows = edited_df[edited_df["Selected"] == True]
    
    if not selected_rows.empty:
        st.write(f"**{len(selected_rows)} files selected**")
        
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("🗑️ Delete Selected Files", type="primary"):
                files_to_delete = selected_rows["filePath"].tolist()
                
                with st.spinner("Deleting files..."):
                    count, errors = delete_files(files_to_delete, db, fs)
                
                if errors:
                    for err in errors:
                        st.error(err)
                
                if count > 0:
                    st.success(f"Deleted {count} files.")
                    st.cache_data.clear()
                    st.rerun()

        with col2:
            if st.button("⚡ Index Selected Files (RAG)", type="secondary"):
                files_to_index = selected_rows["filePath"].tolist()
                
                # Fetch Config
                try:
                    rag_config = db["llmConfigs"].find_one({"config_id": "default_rag_config"}) or {}
                except Exception as e:
                    st.error(f"Error loading config: {e}")
                    rag_config = {}

                if not rag_config.get("GOOGLE_API_KEY") and not os.getenv("GOOGLE_API_KEY"):
                     st.error("Google API Key missing. Please configure it in the RAG Configuration tab.")
                else:
                    # Prepare Env
                    current_env = os.environ.copy()
                    
                    # Augment with DB Config
                    for k, v in rag_config.items():
                         if k in ["GOOGLE_API_KEY", "LLM_MODEL", "EMBEDDING_MODEL", "CHUNK_SIZE", "CHUNK_OVERLAP"]:
                             current_env[k] = str(v)
                    
                    # Set Target List
                    current_env["TARGET_FILES_LIST"] = ",".join(files_to_index)
                    
                    st.info(f"Starting indexing for {len(files_to_index)} files...")
                    
                    try:
                        progress_text = st.empty()
                        progress_bar = st.progress(0)
                        full_logs = []
                        
                        # Use Popen to stream output
                        process = subprocess.Popen(
                            [sys.executable, "scripts/ingestion/rag_ingestion.py"],
                            env=current_env,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, # Merge stderr into stdout
                            text=True,
                            bufsize=1 # Line buffered
                        )
                        
                        # Stream Output
                        while True:
                            line = process.stdout.readline()
                            if not line and process.poll() is not None:
                                break
                            
                            if line:
                                full_logs.append(line)
                                # Check for custom progress tag
                                if "[UI_PROGRESS]" in line:
                                    try:
                                        # Expected: [UI_PROGRESS] 1/17
                                        parts = line.strip().split("] ")[1].split("/")
                                        current = int(parts[0])
                                        total = int(parts[1])
                                        if total > 0:
                                            progress_bar.progress(current / total)
                                            progress_text.text(f"Processing file {current} of {total}...")
                                    except:
                                        pass

                        return_code = process.poll()
                        
                        if return_code == 0:
                            progress_bar.progress(1.0)
                            progress_text.text("Done!")
                            st.success("✅ Indexing job completed.")
                            with st.expander("Output Logs"):
                                st.code("".join(full_logs))
                            st.cache_data.clear()
                            time.sleep(2)
                            st.rerun()
                        else:
                            st.error("❌ Indexing job failed.")
                            with st.expander("Error Logs"):
                                st.code("".join(full_logs))
                                
                    except Exception as e:
                         st.error(f"Subprocess error: {e}")
