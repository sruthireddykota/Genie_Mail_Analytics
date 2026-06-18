import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st

from mongodb.mongo_store import MongoStore
from agents.genie_agent import ask_genie, continue_conversation
from utils.chat_title import generate_chat_title

st.markdown("""
    <style>
        [data-testid="stSidebarNav"] { display: none; }
    </style>
""", unsafe_allow_html=True)

if "customer_email" not in st.session_state or st.session_state.customer_email is None:
    st.switch_page("app.py")

store = MongoStore()
customer_email = st.session_state.customer_email

if "active_chat_id" not in st.session_state:
    st.session_state.active_chat_id = None

def new_chat():
    st.session_state.active_chat_id = None

def clear_chat():
    if st.session_state.active_chat_id:
        store.clear_chat(st.session_state.active_chat_id)

def delete_chat(chat_id):
    store.delete_chat(chat_id)
    if st.session_state.active_chat_id == chat_id:
        st.session_state.active_chat_id = None

with st.sidebar:
    col1, col2 = st.columns([5, 5])
    with col1:
        if st.button("🏠 Home", use_container_width=True):
            st.switch_page("app.py")
    with col2:
        if st.button("Logout", use_container_width=True):
            st.session_state.customer_email = None
            st.switch_page("app.py")

    st.divider()
    col1, col2 = st.columns([5, 5])
    with col1:
        st.button(":blue[New Chat]", on_click=new_chat)
    with col2:
        st.button(":red[Clear Chat]", on_click=clear_chat)

    st.markdown("### Sessions")

    chats = store.get_chats_by_customer(customer_email)
    for chat in chats:
        chat_id = chat["chat_id"]
        label = chat.get("title", "Chat")
        label = f"🔵 {label[:24]}" if chat_id == st.session_state.active_chat_id else f"⚪ {label[:24]}"
        col1, col2 = st.columns([5, 2])
        with col1:
            if st.button(label, key=f"chat_{chat_id}", use_container_width=True):
                st.session_state.active_chat_id = chat_id
                st.rerun()
        with col2:
            if st.button(":red[Delete]", key=f"delete_{chat_id}", use_container_width=True):
                delete_chat(chat_id)
                st.rerun()

st.title("💬 Ask Genie")
st.divider()

active_chat_id = st.session_state.active_chat_id

if active_chat_id:
    messages = store.get_chat_messages(active_chat_id)
    for msg in messages:
        role = "user" if msg["role"] == "user" else "assistant"
        with st.chat_message(role):
            st.write(msg["content"])

user_input = st.chat_input("Ask Genie anything...")
if user_input:
    with st.chat_message("user"):
        st.write(user_input)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):

            if active_chat_id:
                chat = store.get_chat(active_chat_id)
                context = store.build_chat_context(active_chat_id)
                enriched_q = f"{user_input}\n\n{context}" if context else user_input
                genie_resp = continue_conversation(chat["genie_conv_id"], enriched_q)

            else:
                title  = generate_chat_title(user_input)
                genie_resp = ask_genie(user_input)
                conv_id  = genie_resp.get("conversation_id")
                active_chat_id = store.create_chat(customer_email, title, conv_id)
                st.session_state.active_chat_id = active_chat_id

            answer = genie_resp.get("answer", "").strip() or "The requested data is not available."
            st.write(answer)

    store.save_chat_message(active_chat_id, "user",  user_input)
    store.save_chat_message(active_chat_id, "genie", answer)
    st.rerun()