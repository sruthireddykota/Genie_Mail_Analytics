import pandas as pd
from collections import defaultdict

from gmail.email_fetch import fetch_new_email
from agents.genie_agent import ask_genie, continue_conversation
from agents.email_creator_agent import run_email_creator_agent
from agents.question_splitter_agent import run_question_splitter
from mongodb.mongo_store import MongoStore
from agents.visualization_agent import run_visualization_agent
from utils.logger import get_logger

logger=get_logger()
store = MongoStore()


def is_single_count(dataframe: pd.DataFrame) -> bool:
    if dataframe is None or dataframe.empty:
        return False
    if len(dataframe) == 1 and len(dataframe.columns) == 1:
        try:
            pd.to_numeric(dataframe.iloc[0, 0])
            return True
        except (ValueError, TypeError):
            pass
    return False


def coerce_numeric(dataframe: pd.DataFrame) -> pd.DataFrame:
    for col in dataframe.columns:
        try:
            dataframe[col] = pd.to_numeric(dataframe[col])
        except Exception:
            pass
    return dataframe


def run_pipeline() -> list[dict] | None:

    email_data = fetch_new_email()
    if not email_data:
        logger.info({"Email data is not found"})
        return None

    sender = email_data["sender"]
    subject = email_data["subject"]
    body = email_data["body"]
    in_reply_to = email_data["in_reply_to"]
    references = email_data.get("references")
    message_id = email_data.get("message_id")
    domain_hint = email_data.get("domain_hint")


    session = store.get_session_by_reply(in_reply_to) if in_reply_to else None

    if session:
        logger.info(f"Follow-up detected")

        context = store.build_context_string(session["session_id"])
        enriched_q = f"{body}\n\n{context}" if context else body
        genie_resp = continue_conversation(session["genie_conv_id"], enriched_q)
        sql = genie_resp.get("sql", "")
        answer = genie_resp.get("answer", "").strip() or "The requested data is not available."
        dataframe = coerce_numeric(genie_resp.get("dataframe", pd.DataFrame()))
        conv_id = genie_resp.get("conversation_id", session["genie_conv_id"])

        draft = run_email_creator_agent(
            sender=sender,
            subject=subject,
            question=body,
            genie_answer=answer,
            dataframe=dataframe,
        )
        viz_spec = run_visualization_agent(question=body, sql=sql, dataframe=dataframe)

        result = {
            "sender": sender,
            "subject": subject,
            "question": body,
            "domain":  session["domain"],
            "questions": [body],
            "qa_pairs": [{"question": body, "answer": answer}],
            "genie_answer": answer,
            "dataframe": dataframe,
            "draft_email": draft,
            "conversation_id": conv_id,
            "session_id": session["session_id"],
            "is_followup":  True,
            "single_count": is_single_count(dataframe),
            "in_reply_to": message_id,
            "references": references,
            "viz_spec": viz_spec,
        }

        pending_id = store.save_pending_email(result)
        result["pending_id"] = pending_id

        return [result]

    logger.info("New email - splitting into questions")
    questions = run_question_splitter(body, domain_hint=domain_hint)

    domain_groups = defaultdict(list)
    for item in questions:
        domain_groups[item["domain"]].append(item["question"])

    results = []

    for domain, domain_questions in domain_groups.items():
        logger.info(f"Processing domain: {domain} ({len(domain_questions)} question(s))")

        qa_pairs = []
        last_conv_id = None
        combined_df  = pd.DataFrame()
        last_sql = ""

        for question in domain_questions:
            genie_resp  = ask_genie(question)
            sql = genie_resp.get("sql", "")
            last_sql = sql
            answer  = genie_resp.get("answer", "").strip() or "The requested data is not available."
            dataframe = coerce_numeric(genie_resp.get("dataframe", pd.DataFrame()))
            last_conv_id = genie_resp.get("conversation_id")

            qa_pairs.append({"question": question, "answer": answer})

            if not dataframe.empty and (combined_df.empty or len(dataframe) > len(combined_df)):
                combined_df = dataframe

        combined_qa = "\n\n".join(
            f"Q: {pair['question']}\nA: {pair['answer']}"
            for pair in qa_pairs
        )

        draft = run_email_creator_agent(
            sender=sender,
            subject=f"{domain} Query",
            question=combined_qa,
            genie_answer=combined_qa,
            dataframe=combined_df,
        )
        combined_questions_text = " | ".join(domain_questions)
        viz_spec = run_visualization_agent(
            question=combined_questions_text,
            sql=last_sql,
            dataframe=combined_df,
        )

        result = {
            "sender": sender,
            "subject": subject,
            "domain":  domain,
            "questions": domain_questions,
            "qa_pairs": qa_pairs,
            "dataframe":  combined_df,
            "draft_email": draft,
            "conversation_id": last_conv_id,
            "session_id": None,
            "is_followup": False,
            "single_count": is_single_count(combined_df),
            "in_reply_to": message_id,
            "references": references,
            "viz_spec": viz_spec,
        }

        pending_id = store.save_pending_email(result)
        result["pending_id"] = pending_id

        results.append(result)

    return results