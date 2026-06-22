import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import re
import time
import requests
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from gmail.email_sender import send_email
from config.settings import settings

load_dotenv()

API_BASE_URL = settings.API_BASE_URL

st.markdown("""
    <style>
        [data-testid="stSidebarNav"] { display: none; }
    </style>
""", unsafe_allow_html=True)

if "customer_email" not in st.session_state or st.session_state.customer_email is None:
    st.switch_page("app.py")


def trigger_pipeline_api():
    return requests.post(f"{API_BASE_URL}/pipeline/run").json()

def get_pending_api(domain=None):
    params = {"domain": domain} if domain else {}
    return requests.get(f"{API_BASE_URL}/pending", params=params).json()

def update_pending_draft_api(pending_id, draft_email):
    requests.patch(f"{API_BASE_URL}/pending/draft", json={
        "pending_id": pending_id, "draft_email": draft_email,
    })

def approve_pending_api(pending_id):
    requests.post(f"{API_BASE_URL}/pending/approve", json={"pending_id": pending_id})

def reject_pending_api(pending_id):
    requests.post(f"{API_BASE_URL}/pending/reject", json={"pending_id": pending_id})

def get_domain_messages_api(domain):
    return requests.get(f"{API_BASE_URL}/sessions/{domain}/messages").json()

def get_session_by_domain_api(domain):
    return requests.get(f"{API_BASE_URL}/sessions/domain/{domain}").json()

def create_session_api(customer_email, customer_name, domain, genie_conv_id, message_id):

    res = requests.post(f"{API_BASE_URL}/sessions/create", json={
        "customer_email": customer_email,
        "customer_name":  customer_name,
        "domain":         domain,
        "genie_conv_id":  genie_conv_id,
        "message_id":     message_id,
    })
    return res.json().get("session_id")

def update_session_message_id_api(session_id, message_id):
    requests.patch(f"{API_BASE_URL}/sessions/message-id", json={
        "session_id": session_id, "message_id": message_id,
    })

def save_conversation_api(message_id, conversation_id, session_id, sender, question):

    requests.post(f"{API_BASE_URL}/conversations", json={
        "message_id":      message_id,
        "conversation_id": conversation_id,
        "session_id":      session_id,
        "sender":          sender,
        "question":        question,
    })

def message_exists_api(session_id, role, content):
    res = requests.get(f"{API_BASE_URL}/messages/exists", params={
        "session_id": session_id, "role": role, "content": content,
    })
    return res.json().get("exists", False)

def save_message_api(session_id, domain, role, content):
    requests.post(f"{API_BASE_URL}/messages", json={
        "session_id": session_id, "domain": domain, "role": role, "content": content,
    })


def clean_subject(subject: str) -> str:
    subject = re.sub(r'^(Re:\s*)+', '', subject, flags=re.IGNORECASE).strip()
    subject = re.sub(r'\[\w+\]\s*', '', subject).strip()
    return subject


if "selected_domain" not in st.session_state:
    st.session_state.selected_domain = "All"
if "last_fetch" not in st.session_state:
    st.session_state.last_fetch = 0
if "auto_fetch" not in st.session_state:
    st.session_state.auto_fetch = True


now = time.time()
if st.session_state.auto_fetch and (now - st.session_state.last_fetch) > 5:
    trigger_pipeline_api()
    st.session_state.last_fetch = now


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
    st.markdown("### Domains")

    for domain in ["Sales", "Franchise", "Customer", "Miscellaneous"]:
        pending = get_pending_api(domain)
        count = len(pending)
        label = f"{domain} ({count} pending)" if count > 0 else f"{domain}"
        if st.button(label, use_container_width=True, key=f"sidebar_{domain}"):
            st.session_state.selected_domain = domain
            st.rerun()

    st.divider()
    st.session_state.auto_fetch = st.toggle("Auto-fetch (5s)", value=st.session_state.auto_fetch)

    if st.button("📥 :green[Fetch Email]"):
        with st.spinner("Fetching..."):
            result = trigger_pipeline_api()
            st.session_state.last_fetch = time.time()
        if result.get("status") == "success":
            st.success(f"Fetched {result.get('count')} domain(s)")
            st.rerun()
        else:
            st.warning("No new emails found.")


st.title("📧 Email Approvals")
st.divider()

selected_domain = st.session_state.selected_domain
domains_to_show = (
    ["Sales", "Franchise", "Customer", "Miscellaneous"]
    if selected_domain == "All"
    else [selected_domain]
)

for domain in domains_to_show:

    domain_pending = get_pending_api(domain)

    if domain_pending:
        for pending in domain_pending:
            pending_id = pending["pending_id"]

            st.markdown("**Question:**")
            with st.container(border=True):
                for q in pending.get("questions", []):
                    st.markdown(f"{q}")

            st.markdown("**Reply**")
            edited_draft = st.text_area(
                label="Draft Reply",
                value=pending["draft_email"],
                height=300,
                key=f"draft_{pending_id}",
                label_visibility="collapsed"
            )
            if edited_draft != pending["draft_email"]:
                update_pending_draft_api(pending_id, edited_draft)

            viz_spec   = pending.get("viz_spec")
            df_records = pending.get("dataframe_records", [])
            df_columns = pending.get("dataframe_columns", [])
            df = pd.DataFrame(df_records, columns=df_columns) if df_records else pd.DataFrame()

            if viz_spec and not df.empty:
                chart_type = viz_spec["visualization"]
                x_col, y_col = viz_spec["x_axis"], viz_spec["y_axis"]
                if x_col in df.columns and y_col in df.columns:
                    chart_df = df[[x_col, y_col]].copy()
                    if chart_type == "bar":
                        st.bar_chart(chart_df.set_index(x_col)[y_col])
                    elif chart_type == "line":
                        st.line_chart(chart_df.set_index(x_col)[y_col])
                    elif chart_type == "pie":
                        st.bar_chart(chart_df.set_index(x_col)[y_col])

            has_data = len(pending.get("qa_pairs", [])) > 0 and not pending.get("single_count", False)
            if has_data:
                st.info(f"📎 {domain.lower()}_data.xlsx will be attached")
            else:
                st.warning("No data attachment for this reply.")

            col_approve, col_reject, _ = st.columns([1, 1, 4])

            with col_approve:
                if st.button(":green[Approve]", key=f"approve_{pending_id}"):
                    original_subject = clean_subject(pending["subject"])
                    final_subject = f"Re: {original_subject} [{domain}]"
                    final_body = st.session_state.get(f"draft_{pending_id}", pending["draft_email"])

                    sent_message_id = send_email(
                        recipient=pending["sender"],
                        subject=final_subject,
                        body=final_body,
                        dataframe=df if has_data else None,
                        attachment_name=f"{domain.lower()}_data.xlsx",
                        in_reply_to=pending.get("in_reply_to"),
                        references=pending.get("references"),
                    )

                    if sent_message_id:
                        approve_pending_api(pending_id)

                        existing_session = get_session_by_domain_api(domain)
                        if existing_session:
                            session_id = existing_session["session_id"]
                            update_session_message_id_api(session_id, sent_message_id)
                        else:
                            session_id = create_session_api(
                                customer_email=pending["sender"],
                                customer_name=pending["sender"].split("<")[0].strip(),
                                domain=domain,
                                genie_conv_id=pending.get("conversation_id", ""),
                                message_id=sent_message_id,
                            )

                        save_conversation_api(
                            message_id=sent_message_id,
                            conversation_id=pending.get("conversation_id", ""),
                            session_id=session_id,
                            sender=pending["sender"],
                            question=" | ".join(pending.get("questions", [])),
                        )

                        for pair in pending.get("qa_pairs", []):
                            if not message_exists_api(session_id, "customer", pair["question"]):
                                save_message_api(session_id, domain, "customer", pair["question"])

                        if not message_exists_api(session_id, "agent", pending["draft_email"]):
                            save_message_api(session_id, domain, "agent", pending["draft_email"])

                        st.success(f"{domain} reply sent.")
                        st.rerun()
                    else:
                        st.error(f"Failed to send {domain} reply.")

            with col_reject:
                if st.button(":red[Reject]", key=f"reject_{pending_id}"):
                    reject_pending_api(pending_id)
                    st.warning(f"{domain} reply rejected.")
                    st.rerun()

    all_messages = get_domain_messages_api(domain)

    if all_messages:
        i = 0
        while i < len(all_messages):
            msg = all_messages[i]
            if msg["role"] == "customer":
                st.markdown("**Question**")
                with st.container(border=True):
                    st.write(msg["content"])
                if i + 1 < len(all_messages) and all_messages[i + 1]["role"] == "agent":
                    st.markdown("**Reply**")
                    with st.container(border=True):
                        for line in all_messages[i + 1]["content"].split("\n"):
                            st.write(line)
                    i += 2
                else:
                    i += 1
            else:
                i += 1

    if not all_messages and not domain_pending:
        st.info(f"No emails for {domain} yet.")

    st.divider()

if st.session_state.auto_fetch:
    time.sleep(5)
    st.rerun()