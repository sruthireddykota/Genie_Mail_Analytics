
import streamlit as st
import requests

from agents.genie_agent import ask_genie, continue_conversation
from utils.chat_title import generate_chat_title
from config.settings import settings

API_BASE_URL = settings.API_BASE_URL

st.markdown("""
    <style>
        [data-testid="stSidebarNav"] { display: none; }
    </style>
""", unsafe_allow_html=True)

if "customer_email" not in st.session_state or st.session_state.customer_email is None:
    st.switch_page("app.py")

customer_email = st.session_state.customer_email


def create_chat_api(customer_email, title, genie_conv_id):
    res = requests.post(f"{API_BASE_URL}/chat/create", json={
        "customer_email": customer_email,
        "title": title,
        "genie_conv_id": genie_conv_id,
    })
    return res.json().get("chat_id")

def get_chats_by_customer_api(customer_email):
    res = requests.get(f"{API_BASE_URL}/chat/{customer_email}/sessions")
    return res.json()

def get_chat_api(chat_id):
    res = requests.get(f"{API_BASE_URL}/chat/{chat_id}")
    return res.json()

def get_chat_messages_api(chat_id):
    res = requests.get(f"{API_BASE_URL}/chat/{chat_id}/messages")
    return res.json()

def get_chat_context_api(chat_id, limit=5):
    res = requests.get(f"{API_BASE_URL}/chat/{chat_id}/context", params={"limit": limit})
    return res.json().get("context", "")

def save_chat_message_api(chat_id, role, content):
    requests.post(f"{API_BASE_URL}/chat/message", json={
        "chat_id": chat_id,
        "role": role,
        "content": content,
    })

def update_chat_conv_api(chat_id, genie_conv_id):
    requests.patch(f"{API_BASE_URL}/chat/conv", json={
        "chat_id": chat_id,
        "genie_conv_id": genie_conv_id,
    })

def delete_chat_api(chat_id):
    requests.delete(f"{API_BASE_URL}/chat/{chat_id}")

def clear_chat_api(chat_id):
    requests.delete(f"{API_BASE_URL}/chat/{chat_id}/messages")



if "active_chat_id" not in st.session_state:
    st.session_state.active_chat_id = None

def new_chat():
    st.session_state.active_chat_id = None

def clear_chat():
    if st.session_state.active_chat_id:
        clear_chat_api(st.session_state.active_chat_id)

def delete_chat(chat_id):
    delete_chat_api(chat_id)
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

    chats = get_chats_by_customer_api(customer_email)
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
    messages = get_chat_messages_api(active_chat_id)
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
                chat = get_chat_api(active_chat_id)
                context = get_chat_context_api(active_chat_id)
                enriched_q = f"{user_input}\n\n{context}" if context else user_input
                genie_resp = continue_conversation(chat["genie_conv_id"], enriched_q)
            else:
                title = generate_chat_title(user_input)
                genie_resp = ask_genie(user_input)
                conv_id = genie_resp.get("conversation_id")
                active_chat_id = create_chat_api(customer_email, title, conv_id)
                st.session_state.active_chat_id = active_chat_id

            answer = genie_resp.get("answer", "").strip() or "The requested data is not available."
            st.write(answer)

    save_chat_message_api(active_chat_id, "user",  user_input)
    save_chat_message_api(active_chat_id, "genie", answer)
    st.rerun()