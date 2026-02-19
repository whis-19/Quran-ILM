import streamlit as st
from datetime import datetime
from admin_utils import init_connection
import uuid

# st.set_page_config(page_title="Submit Feedback", page_icon="✍️")

# --- AUTH CHECK ---
if not st.session_state.get("authenticated"):
    st.switch_page("Home.py")
    st.stop()

st.title("✍️ Submit Feedback")
st.markdown("We value your feedback! Please let us know how we can improve your experience.")

# Connect to DB
client, db, fs = init_connection()

if not client:
    st.error("Database connection failed.")
    st.stop()

feedback_collection = db["feedback"]

with st.form("feedback_form"):
    # 1. Rating
    st.subheader("How would you rate your experience?")
    rating = st.feedback("stars") # Streamlit 1.31+ feature
    
    # 2. Text Input
    st.subheader("Any comments or suggestions?")
    comment = st.text_area("Your Feedback", placeholder="Tell us what you liked or what we can improve...", height=150)
    
    submitted = st.form_submit_button("Submit Feedback", type="primary")
    
    if submitted:
        if rating is None:
            st.error("Please select a star rating.")
        else:
            # Construct Data
            user_email = st.session_state.get("user_email", "Anonymous")
            # If we had a username in session, we could use it. For now, email or part of it.
            user_name = user_email.split("@")[0] if "@" in user_email else user_email
            
            feedback_data = {
                "user": user_name, # Matching the schema in feedback_review.py
                "email": user_email,
                "rating": rating + 1, # st.feedback returns 0-4 index
                "comment": comment,
                "date": datetime.utcnow()
            }
            
            try:
                feedback_collection.insert_one(feedback_data)
                st.success("Thank you! Your feedback has been submitted.")
                st.balloons()
            except Exception as e:
                st.error(f"Error submitting feedback: {e}")
