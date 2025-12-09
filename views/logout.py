import streamlit as st
import time

def logout():
    st.session_state.authenticated = False
    st.session_state.role = None
    st.session_state.auth_mode = "login"
    st.info("Logging out...")
    time.sleep(0.5)
    st.rerun()

logout()
