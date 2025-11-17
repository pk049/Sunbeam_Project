# ============================================
# 📧 email_agent.py — Gemini + FastMCP Email Agent
# ============================================

import asyncio
import google.generativeai as genai
import json
import os
import re
from dotenv import load_dotenv
from dataclasses import dataclass
from fastmcp import Client

# =================== CONFIG ===================
load_dotenv()

@dataclass
class Config:
    gemini_api_key: str
    model_name: str = "gemini-2.0-flash-exp"

    @classmethod
    def from_env(cls):
        key = os.getenv("GEMINI_API_KEY")
        if not key:
            raise ValueError("❌ GEMINI_API_KEY not found in .env")
        return cls(gemini_api_key=key)

config = Config.from_env()
genai.configure(api_key=config.gemini_api_key)
model = genai.GenerativeModel(config.model_name)

# =================== GEMINI AGENT ===================
class EmailAgent:
    SYSTEM_PROMPT = """You are an intelligent email assistant managing emails via MCP tools.

Available tools:

1. send_email - Send an email
   Example: {"tool": "send_email", "args": {"to": "user@example.com", "subject": "Hello", "body": "Hi there!"}}

2. fetch_emails - Retrieve emails from mailbox
   Example: {"tool": "fetch_emails", "args": {"mailbox": "INBOX", "limit": 10, "unread_only": false}}

3. search_emails - Search emails by subject or sender
   Example: {"tool": "search_emails", "args": {"query": "meeting", "mailbox": "INBOX", "limit": 10}}

4. mark_as_read - Mark an email as read
   Example: {"tool": "mark_as_read", "args": {"email_id": "123", "mailbox": "INBOX"}}

5. delete_email - Delete an email
   Example: {"tool": "delete_email", "args": {"email_id": "123", "mailbox": "INBOX"}}

6. list_mailboxes - List all available mailboxes
   Example: {"tool": "list_mailboxes", "args": {}}

CRITICAL: Respond with ONLY valid JSON:
{"tool": "tool_name", "args": {...}}

Examples:
- "Send email to john@example.com saying meeting at 3pm" → {"tool": "send_email", "args": {"to": "john@example.com", "subject": "Meeting", "body": "Meeting at 3pm"}}
- "Send email to john@example.com with cc to sarah@example.com" → {"tool": "send_email", "args": {"to": "john@example.com", "subject": "Update", "body": "Here's the update", "cc": "sarah@example.com"}}
- "Show my last 5 emails" → {"tool": "fetch_emails", "args": {"mailbox": "INBOX", "limit": 5, "unread_only": false}}
- "Find emails from Sarah" → {"tool": "search_emails", "args": {"query": "Sarah", "mailbox": "INBOX", "limit": 10}}
- "Show unread emails" → {"tool": "fetch_emails", "args": {"mailbox": "INBOX", "limit": 10, "unread_only": true}}
"""

    HUMANIZE_PROMPT = """You are a friendly email assistant helping users manage their inbox.

The user asked: "{user_query}"

You executed the tool: {tool_name} with arguments: {args}

The tool returned this result:
{tool_result}

Please provide a natural, conversational response that:
1. Summarizes what was done
2. Presents the key information in a friendly, easy-to-read format
3. Uses emojis where appropriate to make it engaging
4. For email lists, format them nicely with key details (from, subject, date, etc.)
5. For sent emails, confirm what was sent
6. For searches, summarize what was found
7. Be concise but informative

Respond naturally as if you're chatting with a friend about their email."""

    def __init__(self, model):
        self.model = model

    def extract_json(self, text: str):
        """Extract JSON safely from Gemini output"""
        text = re.sub(r'```(?:json)?', '', text, flags=re.IGNORECASE).strip('`').strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # fallback: find balanced braces
        start, count = -1, 0
        for i, c in enumerate(text):
            if c == '{':
                if count == 0:
                    start = i
                count += 1
            elif c == '}':
                count -= 1
                if count == 0 and start != -1:
                    try:
                        return json.loads(text[start:i+1])
                    except:
                        pass
        return None

    async def plan_tool_call(self, user_query: str):
        """Ask Gemini to decide which MCP tool to call"""
        prompt = f"{self.SYSTEM_PROMPT}\nUser Query: {user_query}"
        response = self.model.generate_content(prompt)
        tool_call = self.extract_json(response.text)
        return tool_call

    async def humanize_response(self, user_query: str, tool_name: str, args: dict, tool_result: str):
        """Convert tool result into natural, conversational response"""
        prompt = self.HUMANIZE_PROMPT.format(
            user_query=user_query,
            tool_name=tool_name,
            args=json.dumps(args, indent=2),
            tool_result=tool_result
        )
        response = self.model.generate_content(prompt)
        return response.text

# =================== MAIN CLIENT ===================
async def main():
    """Main client loop"""
    print("📧 Email Agent with FastMCP + Gemini")
    print("=" * 50)
    print("Commands you can try:")
    print("  • Send email to john@example.com about meeting")
    print("  • Show my last 10 emails")
    print("  • Show unread emails")
    print("  • Search for emails from Sarah")
    print("  • List all mailboxes")
    print("=" * 50)
    print()
    
    # Connect to email MCP server
    async with Client("fastmcp_email_server.py") as mcp_client:
        print("✅ Connected to Email MCP server\n")

        # List available tools
        try:
            tools_response = await mcp_client.list_tools()
            tools = tools_response.tools if hasattr(tools_response, 'tools') else tools_response
            print("🧰 Available Email Tools:")
            for t in tools:
                tool_name = t.name if hasattr(t, 'name') else t.get('name')
                tool_desc = t.description if hasattr(t, 'description') else t.get('description', '')
                print(f"  • {tool_name}: {tool_desc}")
            print()
        except Exception as e:
            print(f"⚠️  Could not list tools: {e}")
            print()

        agent = EmailAgent(model)

        # Interactive loop
        while True:
            try:
                user_query = input("📧 You: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n")
                break
                
            if user_query.lower() in ["exit", "quit", "bye"]:
                break
            if not user_query:
                continue

            try:
                # Step 1: Plan the tool call
                tool_call = await agent.plan_tool_call(user_query)
                if not tool_call:
                    print("❌ Could not understand your request. Try being more specific.")
                    continue

                tool_name = tool_call.get("tool")
                args = tool_call.get("args", {})

                print(f"\n🔧 Executing: {tool_name}({args})")
                
                # Step 2: Execute the tool
                result = await mcp_client.call_tool(tool_name, arguments=args)

                # Extract raw tool result
                raw_result = ""
                if hasattr(result, 'content'):
                    content = result.content
                    if isinstance(content, list) and len(content) > 0:
                        raw_result = content[0].text if hasattr(content[0], 'text') else str(content[0])
                    else:
                        raw_result = str(content)
                elif isinstance(result, dict) and "content" in result:
                    content = result["content"]
                    if isinstance(content, list) and len(content) > 0:
                        raw_result = content[0].get("text") if isinstance(content[0], dict) else str(content[0])
                    else:
                        raw_result = json.dumps(result, indent=2)
                else:
                    raw_result = json.dumps(result, indent=2, default=str)

                # Step 3: Humanize the response
                print("\n🤖 Assistant: ", end="", flush=True)
                humanized = await agent.humanize_response(user_query, tool_name, args, raw_result)
                print(humanized)
                print()
                    
            except Exception as e:
                print(f"❌ Error: {e}\n")
                continue

    print("👋 Disconnected from Email MCP server.")

# =================== ENTRY ===================
if __name__ == "__main__":
    asyncio.run(main())