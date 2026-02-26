import streamlit as st
from utils.admin_utils import init_connection

# st.set_page_config(
#     page_title="Quran-ILM Admin Panel",
#     page_icon="🗄️",
#     layout="wide"
# )

# --- AUTH CHECK ---
if not st.session_state.get("authenticated"):
    st.warning("Please Login first.")
    st.info("Redirecting to Login...")
    st.switch_page("Home.py")
    st.stop()
    
if st.session_state.role != "admin":
    st.error("Unauthorized Access: Admins Only.")
    st.stop()
# ------------------

st.title("🗄️ Quran-ILM Admin Panel")

client, db, fs = init_connection()

if client:
    st.success("✅ Connected to MongoDB Atlas")
    
    # Simple Dashboard Summary
    col1, col2, col3 = st.columns(3)
    with col1:
        file_count = db["datasets"].count_documents({})
        st.metric("Total Files in Library", file_count)
        
    with col2:
        try:
            rag_config = db["llmConfigs"].find_one({"config_id": "default_rag_config"}) or {}
            model = rag_config.get("LLM_MODEL", "Not Configured")
            st.metric("Active LLM Model", model)
        except:
            st.metric("Active LLM Model", "Error Loading")

    with col3:
        feedback_count = db["feedback"].count_documents({})
        st.metric("Total Feedback", feedback_count)

    st.markdown("### Navigation")
    st.info("👈 Select a module from the sidebar to begin.")
    st.markdown("""
    - **📂 File Manager**: Upload, view, and delete documents.
    - **⚙️ RAG Configuration**: Configure API keys, models, and run indexing.
    - **📊 Analytics**: View system health, chat traffic, and costs.
    - **📝 Feedback Review**: View user ratings and comments.
    """)
else:
    st.error("❌ Failed to connect to Database. Check .env file.")
