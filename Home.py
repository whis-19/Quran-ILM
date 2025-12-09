import streamlit as st

# --- MAIN CONFIG ---
st.set_page_config(page_title="Quran-ILM", page_icon="☪️", layout="wide")

# --- AUTH CHECK ---
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "role" not in st.session_state:
    st.session_state.role = None

# --- NAVIGATION LOGIC ---
# --- BUTTON STYLES ---
# --- THEME STATE ---
if "theme" not in st.session_state:
    st.session_state.theme = "light"

def get_theme_css(theme):
    if theme == "dark":
        # Dark Mode Overrides
        return """
        <style>
            :root {
                --primary-color: #8B5CF6;
                --background-color: #0E1117;
                --secondary-background-color: #262730;
                --text-color: #FAFAFA;
            }
            .stApp {
                background-color: var(--background-color);
                color: var(--text-color);
            }
            section[data-testid="stSidebar"] {
                background-color: var(--secondary-background-color);
            }
            .stMarkdown, .stText, h1, h2, h3, h4, h5, h6, p, li, span {
                color: var(--text-color) !important;
            }
            .stTextInput > label, .stSelectbox > label {
                color: var(--text-color) !important;
            }
            /* Input Fields Background */
            .stTextInput input, .stTextArea textarea, .stSelectbox div[data-baseweb="select"] {
                color: var(--text-color);
                background-color: #1E1E1E; 
            }
        </style>
        """
    else:
        # Light Mode (Default Streamlit or forced Light)
        return """
        <style>
            :root {
                --primary-color: #8B5CF6;
                --background-color: #FFFFFF;
                --secondary-background-color: #F0F2F6;
                --text-color: #31333F;
            }
            .stApp {
                background-color: var(--background-color);
                color: var(--text-color);
            }
            section[data-testid="stSidebar"] {
                background-color: var(--secondary-background-color);
            }
            .stMarkdown, .stText, h1, h2, h3, h4, h5, h6, p, li, span {
                color: var(--text-color) !important;
            }
            /* Explicitly set Input Background to White/Light */
            .stTextInput input, .stTextArea textarea, .stSelectbox div[data-baseweb="select"] {
                color: var(--text-color);
                background-color: #FFFFFF; 
            }
        </style>
        """

# --- INJECT CSS ---
# 1. Inject Theme Overrides
st.markdown(get_theme_css(st.session_state.theme), unsafe_allow_html=True)

# 2. Base Button Styles (Violet) - Inject AFTER to override Theme
st.markdown("""
<style>
    /* Global Button Style (Violet Theme) */
    div.stButton > button, div.stFormSubmitButton > button, div.stDownloadButton > button {
        background-color: #8B5CF6 !important; 
        color: white !important;
        border-radius: 8px !important;
        padding: 0.5rem 1rem !important;
        font-weight: bold !important;
        border: none !important;
        transition: all 0.3s ease-in-out !important;
        width: 100%;
    }
    /* Explicitly target the p tag inside buttons with high specificity */
    div.stButton > button p, div.stFormSubmitButton > button p, div.stDownloadButton > button p {
        color: white !important;
    }
    div.stButton > button:hover, div.stFormSubmitButton > button:hover, div.stDownloadButton > button:hover {
        background-color: #7C3AED !important;
        transform: translateY(-2px);
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    
    /* Tertiary Button (Link Style) */
    div.stButton > button[kind="tertiary"] {
        background-color: transparent !important;
        color: #8B5CF6 !important;
        border: none !important;
        box-shadow: none !important;
        text-decoration: none !important;
        padding: 0 !important;
        width: auto !important;
        margin-top: 10px !important;
    }
    div.stButton > button[kind="tertiary"] p {
        color: #8B5CF6 !important;
        text-decoration: underline;
        font-weight: normal !important;
    }
    
    /* Hide Streamlit Menu */
    #MainMenu {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

# --- NAVIGATION LOGIC ---
if not st.session_state.authenticated:
    # --- GUEST (Login) ---
    pg = st.navigation([st.Page("views/login.py", title="Login", icon="🔐")])
    pg.run()
    
else:
    # --- AUTHENTICATED ---
    
    # Logout Logic in Sidebar
    with st.sidebar:
        st.write(f"Logged in as **{st.session_state.role.upper()}**")
        
        # Theme Toggle
        is_dark = st.session_state.theme == "dark"
        toggle = st.toggle("🌙 Dark Mode", value=is_dark)
        if toggle != is_dark:
            st.session_state.theme = "dark" if toggle else "light"
            st.rerun()
            
        st.divider()
        
        if st.button("🚪 Log Out"):
            st.session_state.authenticated = False
            st.session_state.role = None
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
        ]
        
        pg = st.navigation(
            {
                "Application": user_pages,
            }
        )
        pg.run()
