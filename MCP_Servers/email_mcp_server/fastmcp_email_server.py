from mcp.server.fastmcp import FastMCP
import os
import smtplib
import imaplib
import email
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import decode_header
from dotenv import load_dotenv
from typing import Optional
import sys

# =================== LOAD CONFIG ===================
load_dotenv()

EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
IMAP_SERVER = os.getenv("IMAP_SERVER", "imap.gmail.com")
IMAP_PORT = int(os.getenv("IMAP_PORT", "993"))

if not EMAIL_ADDRESS or not EMAIL_PASSWORD:
    print("❌ Missing EMAIL_ADDRESS or EMAIL_PASSWORD in .env", file=sys.stderr)
    sys.exit(1)

print(f"✅ Email configured for {EMAIL_ADDRESS}", file=sys.stderr)

# =================== HELPERS ===================
def decode_mime_str(s):
    if s is None:
        return ""
    decoded_parts = decode_header(s)
    decoded_string = ""
    for part, encoding in decoded_parts:
        if isinstance(part, bytes):
            decoded_string += part.decode(encoding or 'utf-8', errors='ignore')
        else:
            decoded_string += part
    return decoded_string

def get_email_body(msg):
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and "attachment" not in str(part.get("Content-Disposition")):
                try:
                    body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                    break
                except:
                    pass
    else:
        try:
            body = msg.get_payload(decode=True).decode('utf-8', errors='ignore')
        except:
            body = str(msg.get_payload())
    return body.strip()

# =================== FASTMCP SERVER ===================
mcp = FastMCP("email-mcp-server")

# =================== SEND ===================
@mcp.tool()
async def send_email(to: str, subject: str, body: str) -> str:
    """Send an email"""
    try:
        msg = MIMEMultipart()
        msg["From"] = EMAIL_ADDRESS
        msg["To"] = to
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            server.send_message(msg)

        return f"✅ Email sent to {to}"
    except Exception as e:
        return f"❌ Error: {str(e)}"

# =================== READ ===================
@mcp.tool()
async def get_emails(sender: Optional[str] = None, subject: Optional[str] = None, unread_only: bool = False, limit: int = 10) -> str:
    """Get emails by sender, subject, unread status, or get all"""
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
        mail.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        mail.select("INBOX")

        # Build search criteria
        criteria = []
        if unread_only:
            criteria.append("UNSEEN")
        if sender:
            criteria.append(f'FROM "{sender}"')
        if subject:
            criteria.append(f'SUBJECT "{subject}"')
        
        search_str = " ".join(criteria) if criteria else "ALL"
        status, messages = mail.search(None, search_str)
        
        if status != "OK" or not messages[0]:
            return "No emails found."

        email_ids = messages[0].split()[-limit:]
        result = f"Found {len(email_ids)} email(s):\n\n"
        
        for i, eid in enumerate(reversed(email_ids), 1):
            status, msg_data = mail.fetch(eid, "(RFC822)")
            if status != "OK":
                continue
            
            msg = email.message_from_bytes(msg_data[0][1])
            from_addr = decode_mime_str(msg.get("From", ""))
            subj = decode_mime_str(msg.get("Subject", ""))
            date = msg.get("Date", "")
            body = get_email_body(msg)
            preview = body[:100] + "..." if len(body) > 100 else body
            
            result += f"{i}. From: {from_addr}\n"
            result += f"   Subject: {subj}\n"
            result += f"   Date: {date}\n"
            result += f"   ID: {eid.decode()}\n"
            result += f"   Preview: {preview}\n\n"

        mail.close()
        mail.logout()
        return result
    except Exception as e:
        return f"❌ Error: {str(e)}"

@mcp.tool()
async def read_email(email_id: str) -> str:
    """Read full content of an email by ID"""
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
        mail.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        mail.select("INBOX")
        
        status, msg_data = mail.fetch(email_id, "(RFC822)")
        if status != "OK":
            return f"❌ Could not find email {email_id}"
        
        msg = email.message_from_bytes(msg_data[0][1])
        from_addr = decode_mime_str(msg.get("From", ""))
        to_addr = decode_mime_str(msg.get("To", ""))
        subject = decode_mime_str(msg.get("Subject", ""))
        date = msg.get("Date", "")
        body = get_email_body(msg)
        
        mail.close()
        mail.logout()
        
        return f"""📧 Email:
From: {from_addr}
To: {to_addr}
Date: {date}
Subject: {subject}
━━━━━━━━━━━━━━━━━━━━━━

{body}
"""
    except Exception as e:
        return f"❌ Error: {str(e)}"

@mcp.tool()
async def reply_email(email_id: str, body: str) -> str:
    """Reply to an email by ID"""
    try:
        # Get original email
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
        mail.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        mail.select("INBOX")
        
        status, msg_data = mail.fetch(email_id, "(RFC822)")
        if status != "OK":
            return f"❌ Could not find email {email_id}"
        
        original = email.message_from_bytes(msg_data[0][1])
        to_addr = original.get("From", "")
        orig_subject = decode_mime_str(original.get("Subject", ""))
        reply_subject = f"Re: {orig_subject}" if not orig_subject.startswith("Re:") else orig_subject
        
        mail.close()
        mail.logout()
        
        # Send reply
        msg = MIMEMultipart()
        msg["From"] = EMAIL_ADDRESS
        msg["To"] = to_addr
        msg["Subject"] = reply_subject
        msg["In-Reply-To"] = original.get("Message-ID", "")
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            server.send_message(msg)

        return f"✅ Reply sent to {to_addr}"
    except Exception as e:
        return f"❌ Error: {str(e)}"

# =================== RUN SERVER ===================
if __name__ == "__main__":
    print("📧 Email MCP Server starting...", file=sys.stderr)
    print("📋 Tools: send_email, get_emails, read_email, reply_email", file=sys.stderr)
    mcp.run()