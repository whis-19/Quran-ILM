import streamlit as st
import pandas as pd
from datetime import datetime
from admin_utils import init_connection

# st.set_page_config(page_title="Feedback Review", page_icon="📝", layout="wide")

# --- AUTH CHECK ---
if not st.session_state.get("authenticated"):
    st.switch_page("Home.py")
    st.stop()
if st.session_state.role != "admin":
    st.error("Unauthorized Access: Admins Only.")
    st.stop()
# ------------------

st.title("📝 User Feedback Review")

# Connect
client, db, fs = init_connection()

if not client:
    st.error("Database connection failed.")
    st.stop()
    
# --- DUMMY DATA SEEDING ---
feedback_collection = db["feedback"]

if feedback_collection.count_documents({}) == 0:
    st.info("Initializing Dummy Feedback Data...")
    dummy_data = [
        {
            "user": "Abdullah",
            "rating": 5,
            "comment": "The search is very accurate, mashallah.",
            "date": datetime(2024, 10, 15, 14, 30)
        },
        {
            "user": "Ayesha",
            "rating": 4,
            "comment": "Good, but the chatbot is a bit slow sometimes.",
            "date": datetime(2024, 10, 16, 9, 15)
        },
        {
            "user": "Omar",
            "rating": 5,
            "comment": "Excellent resource for students.",
            "date": datetime(2024, 10, 17, 18, 45)
        },
        {
            "user": "Fatima",
            "rating": 3,
            "comment": "Needs more Tafsir options.",
            "date": datetime(2024, 10, 18, 11, 0)
        },
        {
            "user": "Guest_12",
            "rating": 4,
            "comment": "Very helpful UI.",
            "date": datetime(2024, 10, 19, 16, 20)
        }
    ]
    feedback_collection.insert_many(dummy_data)
    st.success("Dummy data inserted!")
    st.rerun()

# --- DISPLAY FEEDBACK ---
st.markdown("### Recent Feedback")

# Metrics
total_feedback = feedback_collection.count_documents({})
avg_rating_cursor = feedback_collection.aggregate([
    {"$group": {"_id": None, "avgRating": {"$avg": "$rating"}}}
])
avg_rating = 0
try:
    avg_rating = list(avg_rating_cursor)[0]["avgRating"]
except:
    pass

col1, col2 = st.columns(2)
col1.metric("Total Reviews", total_feedback)
col2.metric("Average Rating", f"{avg_rating:.1f} ⭐")

st.divider()

# Fetch Data
feedback_cursor = feedback_collection.find({}, {"_id": 0}).sort("date", -1)
feedback_list = list(feedback_cursor)

if feedback_list:
    df = pd.DataFrame(feedback_list)
    # Reorder columns
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])
    
    st.dataframe(
        df,
        column_config={
            "user": "User Name",
            "rating": st.column_config.NumberColumn(
                "Rating",
                help="Stars (1-5)",
                format="%d ⭐"
            ),
            "comment": "Comment",
            "date": st.column_config.DatetimeColumn(
                "Date",
                format="D MMM YYYY, h:mm a"
            )
        },
        use_container_width=True,
        hide_index=True
    )
else:
    st.info("No feedback available yet.")
