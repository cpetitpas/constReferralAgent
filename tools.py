# tools.py
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from copilot.tools import define_tool

load_dotenv()

class SendEmailParams(BaseModel):
    to_email: str = Field(description="Recipient email address")
    subject: str = Field(description="Email subject line")
    body: str = Field(description="Full email body in HTML or plain text")

@define_tool(description="Send a personalized referral email to a past customer. Always use this after generating the email content.")
async def send_email(params: SendEmailParams) -> dict:
    try:
        msg = MIMEMultipart()
        msg['From'] = f"{os.getenv('FROM_NAME')} <{os.getenv('FROM_EMAIL')}>"
        msg['To'] = params.to_email
        msg['Subject'] = params.subject
        msg.attach(MIMEText(params.body, 'html'))

        with smtplib.SMTP(os.getenv("SMTP_SERVER"), int(os.getenv("SMTP_PORT"))) as server:
            server.starttls()
            server.login(os.getenv("SMTP_USERNAME"), os.getenv("SMTP_PASSWORD"))
            server.send_message(msg)

        return {"status": "sent", "to": params.to_email}
    except Exception as e:
        return {"status": "error", "to": params.to_email, "error": str(e)}