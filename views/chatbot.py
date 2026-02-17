import streamlit as st
import pymongo
import os
import google.generativeai as genai
from datetime import datetime
from datetime import datetime
import config

# --- CONFIGURATION (Default Fallbacks) ---
DEFAULT_RAG_DB = "Quran_RAG_Vectors"
VECTOR_COLLECTION = "ragChunks"

# --- 1. INITIALIZATION & CONFIG LOADING ---
@st.cache_resource
@st.cache_resource
def init_resources():
    # A. Connect to Primary DB (Metadata & Config)
    mongo_uri = config.MONGO_URI
    db_name = config.MONGO_DB_NAME
    
    if not mongo_uri:
        st.error("MONGO_URI not found.")
        st.stop()
        
    client_meta = pymongo.MongoClient(mongo_uri)
    db_meta = client_meta[db_name]
    
    # B. Load LLM Configuration from DB
    try:
        config_doc = db_meta["llmConfigs"].find_one({"config_id": "default_rag_config"}) or {}
    except Exception as e:
        st.warning(f"Could not load config from DB: {e}")
        config_doc = {}
        
    # Helper to resolve Config Priority: Env > DB > Default
    def get_conf(key, default):
        return config.get_env(key) or config_doc.get(key) or default

    google_api_key = get_conf("GOOGLE_API_KEY", "")
    llm_model_name = get_conf("LLM_MODEL", "gemini-2.5-flash")
    embedding_model_name = get_conf("EMBEDDING_MODEL", "gemini-embedding-001")
    top_k = int(get_conf("TOP_K", 5))
    temperature = float(get_conf("TEMPERATURE", 0.3))
    
    if not google_api_key:
        st.error("Google API Key not found. Please configure it in 'manage_dataset.py'.")
        st.stop()
        
    # Configure GenAI
    genai.configure(api_key=google_api_key)
        
    # C. Connect to RAG DB (Vectors)
    mongo_rag_uri = config.MONGO_RAG_URI
    rag_db_name = config.MONGO_RAG_DB_NAME
    
    if not mongo_rag_uri:
        st.error("MONGO_RAG_URI not found.")
        st.stop()
        
    client_rag = pymongo.MongoClient(mongo_rag_uri)
    db_rag = client_rag[rag_db_name]
    collection_rag = db_rag[VECTOR_COLLECTION]
    
    return collection_rag, db_meta, embedding_model_name, llm_model_name, top_k, temperature

# Initialize
try:
    collection_rag, db_meta, EMBEDDING_MODEL, LLM_MODEL, TOP_K, TEMPERATURE = init_resources()
except Exception as e:
    st.error(f"Initialization Error: {e}")
    st.stop()

# --- 2. VECTOR SEARCH FUNCTION ---
def vector_search(query, k=5):
    """
    Performs Atlas Vector Search using the raw MongoDB Aggregation pipeline.
    """
    # 1. Embed Query
    try:
        embedding_result = genai.embed_content(
            model=EMBEDDING_MODEL,
            content=query,
            task_type="retrieval_query",
            output_dimensionality=768 # Force 768 dimensions to match index
        )
        query_vector = embedding_result['embedding']
    except Exception as e:
        st.error(f"Embedding Error: {e}")
        return []

    # 2. Aggregation Pipeline
    pipeline = [
        {
            "$vectorSearch": {
                "index": "default", 
                "path": "embedding",
                "queryVector": query_vector,
                "numCandidates": 100, 
                "limit": k
            }
        },
        {
            "$project": {
                "_id": 0,
                "text": 1,
                "metadata": 1,
                "score": {"$meta": "vectorSearchScore"}
            }
        }
    ]
    
    # 3. Execute
    # 3. Execute
    try:
        results = list(collection_rag.aggregate(pipeline))
        return results
    except pymongo.errors.OperationFailure as e:
        st.error(f"MongoDB OperationFailure: {e.details}")
        print(f"MongoDB OperationFailure: {e.details}") # Log to console
        return []
    except Exception as e:
        st.error(f"Vector Search Error: {e}")
        print(f"Vector Search Error: {e}")
        return []

# --- 3. UI LAYOUT ---
# st.set_page_config(page_title="Quran AI Assistant", page_icon="🤖")

# --- AUTH CHECK ---
if not st.session_state.get("authenticated"):
    st.warning("Please Login first.")
    st.info("Redirecting to Login...")
    st.switch_page("Home.py")
    st.stop()
# ------------------

st.title("🤖 Quran-ILM AI Assistant")
st.caption("Ask questions about the Quran and Tafsir. Powered by RAG.")

# --- INTRO & GUIDELINES ---
with st.expander("ℹ️ How to use this Assistant"):
    st.markdown("""
    **Welcome!** This AI Assistant answers questions using a knowledgeable database of the Quran and Tafsir. 
    It uses **RAG (Retrieval-Augmented Generation)** to ensure answers are grounded in authentic sources.
    
    **Guidelines & Restrictions:**
    - **Scope**: Ask questions strictly related to Quranic verses, Tafsir, and Islamic history.
    - **Language**: Currently only supported in English. 
    - **Accuracy**: The AI attempts to provide answers from the provided context. Always verify with the provided references.
    
    **Sample Questions:**
    1. *What is the significance of Bismillah?*
    2. *What does the Quran say about patience (Sabr)?*
    3. *Who are the People of the Book?*
    4. *Explain the concept of Tawheed.*
    """)

# Chat History
if "messages" not in st.session_state:
    st.session_state.messages = []

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# --- 4. CHAT LOGIC ---
if prompt := st.chat_input("Ask a question..."):
    # Display User Message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
        
    # Generate Response
    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        full_response = ""
        token_usage = {} # Initialize token_usage
        
        with st.spinner("Searching knowledge base..."):
            # A. Retrieve Context
            results = vector_search(prompt, k=TOP_K)
            
            context_str = ""
            references = []
            
            if results:
                for idx, doc in enumerate(results):
                    text = doc.get('text', '')
                    meta = doc.get('metadata', {})
                    source = meta.get('source', 'Unknown File')
                    score = doc.get('score', 0)
                    
                    context_str += f"Source ({idx+1}): {source}\nContent: {text}\n\n"
                    
                    # Store details for display
                    ref_details = {
                        "source": source,
                        "text": text,
                        "score": score,
                        "meta": meta
                    }
                    references.append(ref_details)

            else:
                context_str = "No relevant context found in the database."

        # B. Generate Answer
        system_instruction = """You are a knowledgeable assistant specializing in the Quran and Tafsir.
Answer the user's question based ONLY on the following context.
If the context does not contain the answer, say "I cannot find the answer in the provided documents."
"""
        user_prompt = f"""Context:
{context_str}

Question: 
{prompt}

Answer:"""

        try:
            model = genai.GenerativeModel(
                model_name=LLM_MODEL, 
                system_instruction=system_instruction
            )
            
            # Stream response
            response = model.generate_content(
                user_prompt, 
                stream=True,
                generation_config=genai.types.GenerationConfig(temperature=TEMPERATURE)
            )
            
            for chunk in response:
                if chunk.text:
                    full_response += chunk.text
                    message_placeholder.markdown(full_response + "▌")
            
            # Capture Usage Metadata (if available)
            try:
                # After iteration, some SDK versions populate this
                if response.usage_metadata:
                    token_usage = {
                        "prompt_tokens": response.usage_metadata.prompt_token_count,
                        "candidates_tokens": response.usage_metadata.candidates_token_count,
                        "total_tokens": response.usage_metadata.total_token_count
                    }
            except:
                pass

            # Final output with references
            message_placeholder.markdown(full_response)
            
            if references:
                with st.expander("📚 References / Sources"):
                    for i, ref in enumerate(references):
                        st.markdown(f"**{i+1}. {ref['source']}** (Relevance: {ref['score']:.4f})")
                        if 'surah' in ref['meta']:
                            st.caption(f"Surah: {ref['meta']['surah']}")
                        st.text(ref['text']) # Show actual text content
                        st.divider()
                        
        except Exception as e:
            st.error(f"Error generating response: {e}")
            full_response = "I encountered an error while processing your request."
            message_placeholder.markdown(full_response)
            token_usage = {}

    # Save Assistant Message
    st.session_state.messages.append({"role": "assistant", "content": full_response})
    
    # --- SAVE TO MONGODB ---
    try:
        chat_log = {
            "timestamp": datetime.utcnow(),
            "question": prompt,
            "answer": full_response,
            "references": references,
            "tokens": token_usage
        }
        db_meta["chats"].insert_one(chat_log)
        print(f"[INFO] Chat saved to DB.")
    except Exception as e:
        print(f"[ERROR] Failed to save chat log: {e}")
