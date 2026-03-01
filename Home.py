import streamlit as st

# --- MAIN CONFIG ---
st.set_page_config(page_title="Quran-ILM", page_icon="quran_ilm.png", layout="wide")

# --- AUTH CHECK ---
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "role" not in st.session_state:
    st.session_state.role = None

# --- NAVIGATION LOGIC ---
# --- BUTTON STYLES ---
# --- BUTTON STYLES ---
st.markdown("""
<style>
    /* Global Button Style (Gold Theme) */
    div.stButton > button, div.stFormSubmitButton > button, div.stDownloadButton > button {
        background-color: #D4AF37 !important; 
        color: white !important;
        border-radius: 8px !important;
        padding: 0.5rem 1rem !important;
        font-weight: bold !important;
        border: none !important;
        transition: all 0.3s ease-in-out !important;
        width: 100%;
    }
    /* Ensure text inside buttons is white */
    div.stButton > button p, div.stFormSubmitButton > button p, div.stDownloadButton > button p {
        color: white !important;
        font-weight: 600 !important;
    }
    div.stButton > button:hover, div.stFormSubmitButton > button:hover, div.stDownloadButton > button:hover {
        background-color: #B5952F !important;
        transform: translateY(-2px);
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    
    /* Tertiary Button (Link Style) */
    div.stButton > button[kind="tertiary"] {
        background-color: transparent !important;
        color: #D4AF37 !important;
        border: none !important;
        box-shadow: none !important;
        text-decoration: none !important;
        padding: 0 !important;
        width: auto !important;
        margin-top: 10px !important;
    }
    div.stButton > button[kind="tertiary"] p {
        color: #D4AF37 !important;
        text-decoration: underline;
        font-weight: normal !important;
    }
    
    /* Hide Streamlit Menu */
    #MainMenu {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

# --- NAVIGATION LOGIC ---
if not st.session_state.authenticated:
    # Initialize guest navigation flag
    if "show_login_page" not in st.session_state:
        st.session_state.show_login_page = False

    if st.session_state.show_login_page:
        # --- LOGIN PAGE ---
        pg = st.navigation([st.Page("views/login.py", title="Login", icon="🔐")])
        pg.run()
    else:
        # --- GUEST MODE: Direct access to chatbot (no login wall) ---
        pg = st.navigation(
            [st.Page("views/chatbot.py", title="Chatbot", icon="🤖", default=True)],
            position="hidden"  # Hide nav tabs for guests
        )
        pg.run()

else:
    # --- AUTHENTICATED ---
    
    # Logout Logic in Sidebar
    with st.sidebar:
        st.logo("quran_ilm.png")
        st.write(f"Logged in as **{st.session_state.role.upper()}**")
        
        if st.button("🚪 Log Out"):
            st.session_state.authenticated = False
            st.session_state.role = None
            st.session_state.user_email = None
            st.session_state.guest_question_count = 0
            st.session_state.show_login_page = False
            st.session_state.auth_mode = "login"
            st.rerun()
            
    if st.session_state.role == "admin":
        # --- ADMIN ROUTES ---
        admin_pages = [
            st.Page("views/admin_dashboard.py", title="Dashboard", icon="📊", default=True),
            st.Page("views/file_manager.py", title="File Manager", icon="📂"),
            st.Page("views/rag_configuration.py", title="RAG Config", icon="⚙️"),
            st.Page("views/analytics.py", title="Analytics", icon="📈"),
            st.Page("views/feedback_review.py", title="Feedback", icon="📝"),
        ]
        
        pg = st.navigation(
            {
                "Admin Panel": admin_pages,
            }
        )
        pg.run()
        
    else:
        # --- USER ROUTES ---
        user_pages = [
            st.Page("views/chatbot.py", title="Chatbot", icon="🤖", default=True),
            st.Page("views/user_feedback.py", title="Feedback", icon="✍️"),
        ]
        
        pg = st.navigation(
            {
                "Application": user_pages,
            }
        )
        pg.run()
