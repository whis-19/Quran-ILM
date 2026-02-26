import streamlit as st
import pymongo
import os
import pandas as pd
import altair as alt
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Load env
# load_dotenv() - Handled by config
from utils import config

# --- CONFIG ---
# st.set_page_config(page_title="Quran-ILM Analytics", layout="wide", page_icon="📊")

# --- AUTH CHECK ---
if not st.session_state.get("authenticated"):
    st.switch_page("Home.py")
    st.stop()
if st.session_state.role != "admin":
    st.error("Unauthorized Access: Admins Only.")
    st.stop()
# ------------------

# --- INITIALIZATION ---
@st.cache_resource
def init_connections():
    # 1. Primary DB
    mongo_uri = config.MONGO_URI
    db_name = config.MONGO_DB_NAME
    if not mongo_uri:
        return None, None, None, None
    client_meta = pymongo.MongoClient(mongo_uri)
    db_meta = client_meta[db_name]

    # 2. RAG DB
    mongo_rag_uri = config.MONGO_RAG_URI
    rag_db_name = config.MONGO_RAG_DB_NAME
    client_rag = pymongo.MongoClient(mongo_rag_uri)
    db_rag = client_rag[rag_db_name]

    return client_meta, db_meta, client_rag, db_rag

client_meta, db_meta, client_rag, db_rag = init_connections()

if not client_meta:
    st.error("❌ Database connection failed. Check .env file.")
    st.stop()

st.title("📊 System Analytics Dashboard")

# --- TAB 1: DATABASE STATS ---
st.header("1. Database Storage & Collections")

col1, col2 = st.columns(2)

def get_db_stats(db, name):
    stats = db.command("dbStats")
    data_size_mb = stats.get("dataSize", 0) / (1024 * 1024)
    storage_size_mb = stats.get("storageSize", 0) / (1024 * 1024)
    objects = stats.get("objects", 0)
    avg_obj_size = stats.get("avgObjSize", 0)
    
    # Collection Breakdown
    collections = db.list_collection_names()
    coll_stats = []
    for coll in collections:
        c_stats = db.command("collStats", coll)
        coll_stats.append({
            "Collection": coll,
            "Count": c_stats.get("count", 0),
            "Size (MB)": round(c_stats.get("size", 0) / (1024 * 1024), 2),
            "Avg Size (KB)": round(c_stats.get("avgObjSize", 0) / 1024, 2)
        })
    
    return {
        "name": name,
        "data_mb": round(data_size_mb, 2),
        "storage_mb": round(storage_size_mb, 2),
        "objects": objects,
        "collections": pd.DataFrame(coll_stats)
    }

# Primary Stats
meta_stats = get_db_stats(db_meta, "Primary (Metadata & Chats)")
with col1:
    st.subheader(f"🗄️ {meta_stats['name']}")
    m1, m2, m3 = st.columns(3)
    m1.metric("Storage Size", f"{meta_stats['storage_mb']} MB")
    m2.metric("Total Documents", f"{meta_stats['objects']:,}")
    m3.metric("Collections", len(meta_stats['collections']))
    
    st.dataframe(meta_stats['collections'], hide_index=True, use_container_width=True)

# RAG Stats
rag_stats = get_db_stats(db_rag, "RAG (Vectors)")
with col2:
    st.subheader(f"🧠 {rag_stats['name']}")
    r1, r2, r3 = st.columns(3)
    r1.metric("Storage Size", f"{rag_stats['storage_mb']} MB")
    r2.metric("Total Chunks", f"{rag_stats['objects']:,}")
    r3.metric("Collections", len(rag_stats['collections']))
    
    st.dataframe(rag_stats['collections'], hide_index=True, use_container_width=True)

st.divider()

# --- TAB 2: CHAT ANALYTICS ---
st.header("2. Chat Traffic & Usage")

# Fetch Chat Data
chats_cursor = db_meta["chats"].find({}, {"timestamp": 1, "tokens": 1})
chats_df = pd.DataFrame(list(chats_cursor))

if not chats_df.empty:
    # Preprocessing
    chats_df["timestamp"] = pd.to_datetime(chats_df["timestamp"])
    chats_df["Date"] = chats_df["timestamp"].dt.date
    chats_df["Hour"] = chats_df["timestamp"].dt.hour
    
    # 2A. Key Metrics
    total_chats = len(chats_df)
    total_tokens = 0
    if "tokens" in chats_df.columns:
        # Sum nested dicts if exist, else 0
        def get_tok(x):
            if isinstance(x, dict):
                return x.get("total_tokens", 0)
            return 0
        total_tokens = chats_df["tokens"].apply(get_tok).sum()
    
    c1, c2, c3 = st.columns(3)
    c1.metric("Total Conversations", f"{total_chats:,}")
    c2.metric("Total Tokens Consumed", f"{total_tokens:,}")
    # Simple Cost Est ($0.50 / 1M tokens approx for Flash)
    est_cost = (total_tokens / 1_000_000) * 0.50
    c3.metric("Est. Cost (Gemini Flash)", f"${est_cost:.4f}")

    # 2B. Rush Hour (Heatmap/Bar)
    st.subheader("🕰️ Activity by Hour (Rush Hour)")
    hourly_counts = chats_df.groupby("Hour").size().reset_index(name="Count")
    
    chart = alt.Chart(hourly_counts).mark_bar().encode(
        x=alt.X("Hour:O", title="Hour of Day (UTC)"),
        y=alt.Y("Count:Q", title="Number of Chats"),
        color=alt.Color("Count:Q", scale=alt.Scale(scheme="viridis"))
    ).properties(height=300)
    
    st.altair_chart(chart, use_container_width=True)
    
    # 2C. Daily Trend
    st.subheader("📅 Daily Trend")
    daily_counts = chats_df.groupby("Date").size().reset_index(name="Count")
    line_chart = alt.Chart(daily_counts).mark_line(point=True).encode(
        x="Date:T",
        y="Count:Q",
        tooltip=["Date", "Count"]
    ).properties(height=300)
    st.altair_chart(line_chart, use_container_width=True)

else:
    st.info("No chat history found yet. Start using the chatbot to see analytics!")
