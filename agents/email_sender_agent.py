import smtplib
import io

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email.utils import make_msgid
from email import encoders

import pandas as pd
from config.settings import settings


SMTP_HOST = settings.SMTP_HOST
SMTP_PORT = settings.SMTP_PORT
SMTP_USER  = settings.SMTP_USER
SMTP_PASSWORD = settings.SMTP_PASSWORD



def send_email(
    recipient: str,
    subject: str,
    body: str,
    dataframe: pd.DataFrame = None,
    attachment_name: str = "analytics_data.xlsx",
    in_reply_to: str = None,  
    references: str = None,   
) -> str | None:
    if not isinstance(body, str):
        return None

    if not isinstance(subject, str):
        return None
    
    msg = MIMEMultipart()
    msg["From"] = SMTP_USER
    msg["To"]  = recipient
    msg["Subject"] = subject
    msg["Message-ID"] = make_msgid()
    
    if in_reply_to:
        
        msg["In-Reply-To"] = in_reply_to
        ref_ids = []
    
        if references:
            ref_ids.extend(references.split())

        if in_reply_to not in ref_ids:
            ref_ids.append(in_reply_to)

        msg["References"] = " ".join(ref_ids)
    else:
        print("DEBUG SEND: in_reply_to is None — email will start a new thread")

    msg.attach(MIMEText(str(body), "plain"))

    should_attach = (
        dataframe is not None
        and not dataframe.empty
        and not (dataframe.shape[0] == 1 and dataframe.shape[1] == 1)
    )

    if should_attach:
        buffer = io.BytesIO()

        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            dataframe.to_excel(writer, index=False, sheet_name="Analytics Data")

            worksheet = writer.sheets["Analytics Data"]
            for col_idx, col in enumerate(dataframe.columns, start=1):
                try:
                    max_len = max(
                        dataframe[col].astype(str).map(len).max(),
                        len(str(col))
                    ) + 2
                except Exception:
                    max_len = len(str(col)) + 2

                col_letter = worksheet.cell(row=1, column=col_idx).column_letter
                worksheet.column_dimensions[col_letter].width = min(max_len, 40)

        buffer.seek(0)
        part = MIMEBase("application", "vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        part.set_payload(buffer.read())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f'attachment; filename="{attachment_name}"')
        msg.attach(part)
    else:
        print("No Excel attachment needed.")

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_USER, recipient, msg.as_string())

        sent_message_id = msg.get("Message-ID")
       
        return sent_message_id

    except Exception as e:
        return e