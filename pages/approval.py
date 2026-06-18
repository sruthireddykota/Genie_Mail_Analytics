import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import re
import time
import streamlit as st
import pandas as pd
from pipeline import run_pipeline
from agents.email_sender_agent import send_email
from mongodb.mongo_store import MongoStore

st.markdown("""
    <style>
        [data-testid="stSidebarNav"] { display: none; }
    </style>
""", unsafe_allow_html=True)

if "customer_email" not in st.session_state or st.session_state.customer_email is None:
    st.switch_page("app.py")

store = MongoStore()

if "selected_domain" not in st.session_state:
    st.session_state.selected_domain = "All"

if "last_fetch" not in st.session_state:
    st.session_state.last_fetch = 0

if "auto_fetch" not in st.session_state:
    st.session_state.auto_fetch = True


def clean_subject(subject: str) -> str:
    subject = re.sub(r'^(Re:\s*)+', '', subject, flags=re.IGNORECASE).strip()
    subject = re.sub(r'\[\w+\]\s*', '', subject).strip()
    return subject

now = time.time()
if st.session_state.auto_fetch and (now - st.session_state.last_fetch) > 5:
    new_results = run_pipeline()
    st.session_state.last_fetch = now
    if new_results:
        print(f"Auto-fetch: {len(new_results)} new domain(s) found")


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
        pending = store.get_pending_emails(domain)
        count   = len(pending)
        label   = f" {domain} ({count} pending)" if count > 0 else f"{domain}"
        if st.button(label, use_container_width=True, key=f"sidebar_{domain}"):
            st.session_state.selected_domain = domain
            st.rerun()

    st.divider()
    st.session_state.auto_fetch = st.toggle(
        " Auto-fetch (5s)", value=st.session_state.auto_fetch
    )

    if st.button("📥 :green[Fetch Email]"):
        with st.spinner("Fetching..."):
            new_results = run_pipeline()
            st.session_state.last_fetch = time.time()
        if new_results:
            st.success(f"Fetched {len(new_results)} domain(s)")
            st.rerun()
        else:
            st.warning("No new emails found.")

st.title("📧 Email Approvals")
st.divider()

selected_domain = st.session_state.selected_domain

all_sessions = store.get_all_sessions()
domain_sessions = {}
for session in all_sessions:
    d = session["domain"]
    if d not in domain_sessions:
        domain_sessions[d] = []
    domain_sessions[d].append(session)

pending_emails = store.get_pending_emails(selected_domain)

domains_to_show = (
    ["Sales", "Franchise", "Customer", "Miscellaneous"]
    if selected_domain == "All"
    else [selected_domain]
)

for domain in domains_to_show:

    sessions_in_domain = domain_sessions.get(domain, [])
    all_messages = []
    
    domain_pending = [p for p in pending_emails if p["domain"] == domain]

    if domain_pending:

        for pending in domain_pending:
            pending_id = pending["pending_id"]

            st.markdown("**Question:**")
            with st.container(border=True):
                if pending.get("questions"):
                    for q in pending["questions"]:
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
                store.update_pending_draft(pending_id, edited_draft)
            
            viz_spec = pending.get("viz_spec")
            df = pending.get("dataframe")

            if viz_spec and df is not None and not df.empty:
                chart_type = viz_spec["visualization"]
                x_col  = viz_spec["x_axis"]
                y_col = viz_spec["y_axis"]

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
                        conversation_id=pending.get("conversation_id"),
                        sender_email=pending["sender"],
                        question=" | ".join(pending.get("questions", [])),
                        dataframe=pending.get("dataframe") if has_data else None,  
                        attachment_name=f"{domain.lower()}_data.xlsx",
                        in_reply_to=pending.get("in_reply_to"),
                        references=pending.get("references"),
                    )

                    if sent_message_id:
                        store.update_pending_status(pending_id, "approved")

                        existing_session = store.get_session_by_domain(domain)
                        if existing_session:
                            session_id = existing_session["session_id"]
                            store.update_session_message_id(session_id, sent_message_id)
                        else:
                            session_id = store.create_session(
                                customer_email=pending["sender"],
                                customer_name=pending["sender"].split("<")[0].strip(),
                                domain=domain,
                                genie_conv_id=pending.get("conversation_id", ""),
                                message_id=sent_message_id,
                            )

                        store.save_conversation(
                            message_id=sent_message_id,
                            conversation_id=pending.get("conversation_id", ""),
                            session_id=session_id,
                            sender=pending["sender"],
                            question=" | ".join(pending.get("questions", [])),
                        )

                        for pair in pending.get("qa_pairs", []):
                            if not store.message_exists(session_id, "customer", pair["question"]):
                                store.save_message(session_id, domain, "customer", pair["question"])

                        if not store.message_exists(session_id, "agent", pending["draft_email"]):
                            store.save_message(session_id, domain, "agent", pending["draft_email"])

                        st.success(f"{domain} reply sent.")
                        st.rerun()
                    else:
                        st.error(f"Failed to send {domain} reply.")

            with col_reject:
                if st.button(":red[Reject]", key=f"reject_{pending_id}"):
                    store.update_pending_status(pending_id, "rejected")
                    st.warning(f"{domain} reply rejected.")
                    st.rerun()
    for session in sessions_in_domain:
        msgs = store.get_messages(session["session_id"])
        all_messages.extend(msgs)
    all_messages.sort(key=lambda m: m["timestamp"])

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