import streamlit as st
from dotenv import load_dotenv
import os
load_dotenv()


st.set_page_config(
    page_title="Genie Analytics",
    page_icon="📬",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown("""
    <style>
        [data-testid="stSidebarNav"] { display: none; }
    </style>
""", unsafe_allow_html=True)

ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "").lower()

if "customer_email" not in st.session_state:
    st.session_state.customer_email = None

if st.session_state.customer_email is None:

    with st.empty().container(border=True):
        col1, _ = st.columns([7, 1])
        with col1:
            st.header("Genie Analytics — Admin Portal")
            st.write("")
            email_input = st.text_input("Email Address", placeholder="admin@example.com", key="login_email")
            st.write("")
            _, login_col, _ = st.columns([1, 3, 1])
            with login_col:
                if st.button("Login", key="login_button", use_container_width=True, type="primary"):
                    if len(email_input.strip()) < 5:
                        st.error("Please enter a valid email address.")
                    elif email_input.strip().lower() != ADMIN_EMAIL:
                        st.error("Access denied. Invalid admin email.")
                    else:
                        st.session_state.customer_email = email_input.strip().lower()
                        st.rerun()
    st.stop()

with st.sidebar:
    if st.button("Logout", use_container_width=True):
        st.session_state.customer_email = None
        st.rerun()

st.title("Genie Analyticsr")
st.divider()
col1, col2 = st.columns(2, gap="large")

with col1:
    with st.container(border=True):
        st.markdown("## 📧")
        st.markdown("### Email Approvals")
        st.write("Review drafted email replies grouped by domain ")
        st.write("")
        if st.button("Open Approvals", use_container_width=True, type="primary", key="go_approval"):
            st.session_state.launched_from = "app"
            st.switch_page("pages/approval.py")

with col2:
    with st.container(border=True):
        st.markdown("## 💬")
        st.markdown("### Ask Genie")
        st.write("Chat directly with Genie to explore data and verify answers before approving replies.")
        st.write("")
        if st.button("Open Chatbot", use_container_width=True, type="primary", key="go_chatbot"):
            st.session_state.launched_from = "app"
            st.switch_page("pages/chatbot.py")