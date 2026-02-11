# tools.py
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from copilot.tools import define_tool

load_dotenv()

class SendEmailParams(BaseModel):
    to_email: str = Field(description="Recipient email address")
    subject: str = Field(description="Email subject line")
    html_body: str = Field(description="Full HTML email body (must be complete <html> structure)")
    embedded_images: dict = Field(  # key = cid name, value = local file path
        default_factory=dict,
        description="Dict of CID:name -> local image path (e.g. {'logo': 'logo.png', 'project': 'kitchen.jpg'})"
    )

@define_tool(description="Send a nicely formatted HTML referral email. Use this with generated HTML content. Embed images via CID if provided.")
async def send_email(params: SendEmailParams) -> dict:
    smtp_server = os.getenv("SMTP_SERVER")
    smtp_port = int(os.getenv("SMTP_PORT"))
    username = os.getenv("SMTP_USERNAME")
    password = os.getenv("SMTP_PASSWORD")
    from_email = os.getenv("FROM_EMAIL")
    from_name = os.getenv("FROM_NAME", "Your Construction Company")

    if not all([smtp_server, smtp_port, username, password, from_email]):
        return {"status": "error", "to": params.to_email, "error": "Missing SMTP config"}

    msg_root = MIMEMultipart('related')
    msg_root['Subject'] = params.subject
    msg_root['From'] = f"{from_name} <{from_email}>"
    msg_root['To'] = params.to_email

    # Alternative part for plain-text fallback + HTML
    msg_alt = MIMEMultipart('alternative')
    msg_root.attach(msg_alt)

    # Plain text fallback (very basic)
    plain_text = "This email requires HTML support to view properly."
    msg_alt.attach(MIMEText(plain_text, 'plain'))

    # HTML body
    msg_alt.attach(MIMEText(params.html_body, 'html'))

    # Embed images
    for cid, img_path in params.embedded_images.items():
        if not os.path.exists(img_path):
            return {"status": "error", "to": params.to_email, "error": f"Image not found: {img_path}"}
        try:
            with open(img_path, 'rb') as f:
                img_data = f.read()
            mime_img = MIMEImage(img_data)
            mime_img.add_header('Content-ID', f'<{cid}>')
            mime_img.add_header('Content-Disposition', 'inline', filename=os.path.basename(img_path))
            msg_root.attach(mime_img)
        except Exception as e:
            return {"status": "error", "to": params.to_email, "error": f"Failed to embed {cid}: {str(e)}"}

    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(username, password)
            server.send_message(msg_root)
        return {"status": "sent", "to": params.to_email}
    except Exception as e:
        return {"status": "failed", "to": params.to_email, "error": str(e)}