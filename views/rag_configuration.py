import streamlit as st
import pymongo
import os
import sys
import subprocess
from admin_utils import init_connection
import config

# st.set_page_config(page_title="RAG Configuration", page_icon="⚙️", layout="wide")

# --- AUTH CHECK ---
if not st.session_state.get("authenticated"):
    st.switch_page("Home.py")
    st.stop()
if st.session_state.role != "admin":
    st.error("Unauthorized Access: Admins Only.")
    st.stop()
# ------------------

st.title("⚙️ RAG Configuration & Indexing")
st.markdown("Configure the parameters for the RAG ingestion pipeline. Settings are **saved to MongoDB**.")

# Connect
client, db, fs = init_connection()

if not client:
    st.error("Database connection failed.")
    st.stop()

# 1. Load Configuration from DB
try:
    current_config = db["llmConfigs"].find_one({"config_id": "default_rag_config"}) or {}
except Exception as e:
    st.error(f"Failed to load config from DB: {e}")
    current_config = {}

# Defaults if DB is empty
default_api = config.GOOGLE_API_KEY

with st.form("rag_config_form"):
    col1, col2 = st.columns(2)
    
    with col1:
        # Use dictionary .get() with fallback to empty string or default
        google_api_key = st.text_input(
            "Google API Key", 
            type="password", 
            value=current_config.get("GOOGLE_API_KEY", default_api)
        )
        llm_model = st.text_input(
            "LLM Model", 
            value=current_config.get("LLM_MODEL", "gemini-2.5-flash")
        )
        embedding_model = st.text_input(
            "Embedding Model", 
            value=current_config.get("EMBEDDING_MODEL", "gemini-embedding-001")
        )
        top_k = st.number_input(
            "Top K (Retrieval)",
            value=int(current_config.get("TOP_K", 5)),
            min_value=1,
            max_value=20
        )

    with col2:
        chunk_size = st.number_input(
            "Chunk Size", 
            value=int(current_config.get("CHUNK_SIZE", 500)), 
            min_value=100, 
            step=50
        )
        chunk_overlap = st.number_input(
            "Chunk Overlap", 
            value=int(current_config.get("CHUNK_OVERLAP", 50)), 
            min_value=0, 
            step=10
        )
        temperature = st.slider(
            "Temperature (Creativity)",
            value=float(current_config.get("TEMPERATURE", 0.3)),
            min_value=0.0,
            max_value=1.0,
            step=0.1
        )
        
    save_config = st.form_submit_button("💾 Save Configuration", type="primary")
    
    if save_config:
        if not google_api_key:
            st.error("Google API Key is required.")
        else:
            # 2. Save Configuration to DB
            new_config = {
                "config_id": "default_rag_config",
                "GOOGLE_API_KEY": google_api_key,
                "LLM_MODEL": llm_model,
                "EMBEDDING_MODEL": embedding_model,
                "CHUNK_SIZE": chunk_size,
                "CHUNK_OVERLAP": chunk_overlap,
                "TOP_K": top_k,
                "TEMPERATURE": temperature
            }
            
            try:
                db["llmConfigs"].update_one(
                    {"config_id": "default_rag_config"},
                    {"$set": new_config},
                    upsert=True
                )
                st.success("✅ Configuration saved to MongoDB.")
            except Exception as e:
                st.error(f"Failed to save config: {e}")

st.divider()

col_idx, _ = st.columns([1, 3])
with col_idx:
    start_indexing = st.button("⚡ Start Full Indexing (Process Unindexed Files)", type="secondary")

if start_indexing:
    # Load latest config for indexing
    indexing_conf = db["llmConfigs"].find_one({"config_id": "default_rag_config"}) or {}
    
    # Prepare Environment Variables
    current_env = os.environ.copy()
    current_env["GOOGLE_API_KEY"] = indexing_conf.get("GOOGLE_API_KEY", "") or os.getenv("GOOGLE_API_KEY", "")
    current_env["LLM_MODEL"] = indexing_conf.get("LLM_MODEL", "gemini-2.5-flash")
    current_env["EMBEDDING_MODEL"] = indexing_conf.get("EMBEDDING_MODEL", "gemini-embedding-001")
    current_env["CHUNK_SIZE"] = str(indexing_conf.get("CHUNK_SIZE", 500))
    current_env["CHUNK_OVERLAP"] = str(indexing_conf.get("CHUNK_OVERLAP", 50))
    
    st.info("Starting Ingestion Pipeline...")

    # Run the script as a subprocess
    try:
        progress_text = st.empty()
        progress_bar = st.progress(0)
        full_logs = []
        
        # Use Popen to stream output
        process = subprocess.Popen(
            [sys.executable, "rag_ingestion.py"],
            env=current_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, # Merge stderr into stdout
            text=True,
            bufsize=1
        )
        
        while True:
            line = process.stdout.readline()
            if not line and process.poll() is not None:
                break
            
            if line:
                full_logs.append(line)
                if "[UI_PROGRESS]" in line:
                    try:
                        parts = line.strip().split("] ")[1].split("/")
                        current = int(parts[0])
                        total = int(parts[1])
                        if total > 0:
                            progress_bar.progress(current / total)
                            progress_text.text(f"Processing file {current} of {total}...")
                    except:
                        pass

        if process.poll() == 0:
            progress_bar.progress(1.0)
            progress_text.text("Done!")
            st.success("✅ Indexing Completed Successfully!")
            with st.expander("Show Output Logs"):
                st.code("".join(full_logs))
        else:
            st.error("❌ Indexing Failed.")
            with st.expander("Show Error Logs"):
                st.code("".join(full_logs))
                    
    except Exception as e:
        st.error(f"Failed to execute script: {e}")
