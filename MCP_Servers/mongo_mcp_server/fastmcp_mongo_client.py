# ============================================
# 🧠 fastmcp_gemini_client_v2.py — Gemini + FastMCP v2.x
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
class GeminiAgent:
    SYSTEM_PROMPT = """You are an intelligent assistant managing a student database via MCP tools.

Available tools:
1. insert_student - Add a new student
   Example: {"tool": "insert_student", "args": {"name": "Alice", "age": 20, "course": "CS"}}

2. fetch_students - Query and retrieve students
   Example: {"tool": "fetch_students", "args": {"query": {"course": "AI"}}}

3. delete_students - Delete students by query
   Example: {"tool": "delete_students", "args": {"query": {"name": "Bob"}}}

CRITICAL: Respond with ONLY valid JSON:
{"tool": "tool_name", "args": {...}}
"""

    HUMANIZE_PROMPT = """You are a friendly assistant helping users interact with a student database.

The user asked: "{user_query}"

You executed the tool: {tool_name} with arguments: {args}

The tool returned this result:
{tool_result}

Please provide a natural, conversational response that:
1. Summarizes what was done
2. Presents the key information in a friendly, easy-to-read format
3. Uses emojis where appropriate to make it engaging
4. If there's data, format it nicely (but don't use markdown tables unless there are many records)
5. Be concise but informative

Respond naturally as if you're chatting with a friend."""

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
    print("🎓 FastMCP v2.x + Gemini Client")
    print("============================\n")
    
    # Connect to local MCP server - FastMCP auto-detects stdio transport
    async with Client("fastmcp_mongo_server.py") as mcp_client:
        print("✅ Connected to MCP server\n")

        # List tools
        try:
            tools_response = await mcp_client.list_tools()
            # Handle both object and list responses
            tools = tools_response.tools if hasattr(tools_response, 'tools') else tools_response
            print("🧰 Available Tools:")
            for t in tools:
                tool_name = t.name if hasattr(t, 'name') else t.get('name')
                tool_desc = t.description if hasattr(t, 'description') else t.get('description', '')
                print(f" - {tool_name}: {tool_desc}")
            print()
        except Exception as e:
            print(f"⚠️  Could not list tools: {e}")
            print()

        agent = GeminiAgent(model)

        # Interactive loop
        while True:
            try:
                user_query = input("💬 You: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n")
                break
                
            if user_query.lower() in ["exit", "quit"]:
                break
            if not user_query:
                continue

            try:
                # Step 1: Plan the tool call
                tool_call = await agent.plan_tool_call(user_query)
                if not tool_call:
                    print("❌ Could not understand your request.")
                    continue

                tool_name = tool_call.get("tool")
                args = tool_call.get("args", {})

                print(f"\n🧩 Executing: {tool_name}({args})")
                
                
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

    print("👋 Disconnected from MCP server.")

# =================== ENTRY ===================
if __name__ == "__main__":
    asyncio.run(main())
    
    
    