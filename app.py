# ============================================
# 🌐 flask_agent_gateway.py - Unified API for All Agents
# ============================================

from flask import Flask, request, jsonify
from flask_cors import CORS
import asyncio
import google.generativeai as genai
import json
import os
import re
from dotenv import load_dotenv
from dataclasses import dataclass
from fastmcp import Client
from functools import wraps
from pymongo import MongoClient
from datetime import datetime


# ===================MONGO CLIENT===================
client = MongoClient("mongodb://localhost:27017/")
db = client['agent_logs']
collection = db['chats']

# =================== CONFIG ===================
load_dotenv()

@dataclass
class Config:
    gemini_api_key: str
    model_name: str = "gemini-2.5-flash"
    
    @classmethod
    def from_env(cls):
        key = os.getenv("GEMINI_API_KEY")
        if not key:
            raise ValueError("❌ GEMINI_API_KEY not found in .env")
        return cls(gemini_api_key=key)

config = Config.from_env()
genai.configure(api_key=config.gemini_api_key)







generation_config = {
    "temperature": 0.7,
    "top_p": 0.95,
    "top_k": 40,
    "max_output_tokens": 8192,
}

model = genai.GenerativeModel(
    model_name=config.model_name,
    generation_config=generation_config
)


# =================== FLASK APP ===================
app = Flask(__name__)
CORS(app)  # Enable CORS for React frontend

# =================== SESSION STORAGE ===================
# Store conversation history per session
conversation_sessions = {}

def get_or_create_session(session_id: str) -> list:
    """Get or create a conversation session"""
    if session_id not in conversation_sessions:
        conversation_sessions[session_id] = []
    return conversation_sessions[session_id]



def add_to_session(session_id: str, role: str, content: str):
    """Add message to session history"""
    session = get_or_create_session(session_id)
    session.append({"role": role, "content": content})
    # Keep last 20 messages to avoid memory issues
    if len(session) > 20:
        conversation_sessions[session_id] = session[-20:]
        
        
        


# =================== BASE AGENT CLASS ===================
class BaseAgent:
    """Base class for all agents with common functionality"""
    
    def __init__(self, model, system_prompt, humanize_prompt):
        self.model = model
        self.SYSTEM_PROMPT = system_prompt
        self.HUMANIZE_PROMPT = humanize_prompt

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

    async def plan_tool_call(self, user_query: str, conversation_history: list = None):
        """Ask Gemini to decide which MCP tool to call"""
        prompt = f"{self.SYSTEM_PROMPT}\n"
        
        # Add conversation history if available
        if conversation_history:
            prompt += "\nConversation History:\n"
            for msg in conversation_history[-6:]:  # Last 3 exchanges
                prompt += f"{msg['role'].capitalize()}: {msg['content']}\n"
            prompt += "\n"
        
        prompt += f"User Query: {user_query}"
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






# =================== EMAIL AGENT ===================
class EmailAgent(BaseAgent):
    SYSTEM_PROMPT = """You are an intelligent email assistant managing emails via MCP tools.

Available tools:
1. send_email(to, subject, body) - Send an email
2. get_emails(sender?, subject?, unread_only?, limit?) - Get emails with filters
3. read_email(email_id) - Read full email content
4. reply_email(email_id, body) - Reply to an email

Examples:
{"tool": "send_email", "args": {"to": "user@example.com", "subject": "Hello", "body": "Hi!"}}
{"tool": "get_emails", "args": {}}  // Get all emails
{"tool": "get_emails", "args": {"sender": "boss@company.com"}}  // From specific person
{"tool": "get_emails", "args": {"unread_only": true}}  // Only unread
{"tool": "get_emails", "args": {"subject": "meeting"}}  // By subject
{"tool": "read_email", "args": {"email_id": "123"}}
{"tool": "reply_email", "args": {"email_id": "123", "body": "Thanks!"}} """


    HUMANIZE_PROMPT = """You are a friendly email assistant helping users manage their inbox.

The user asked: "{user_query}"
You executed: {tool_name} with {args}
Result: {tool_result}

Provide a natural, conversational response that:
- Summarizes what was done clearly
- Presents key information in an easy-to-read format
- Uses emojis appropriately (📧, ✅, 🔍, 📊, etc.)
- For email lists, show key details nicely formatted
- Be concise but informative
- Sounds friendly and helpful

Respond naturally as if chatting with a friend."""

    def __init__(self, model):
        super().__init__(model, self.SYSTEM_PROMPT, self.HUMANIZE_PROMPT)




# =================== MONGODB AGENT ===================
class MongoAgent(BaseAgent):
    SYSTEM_PROMPT = """You are an intelligent assistant managing a student database via MCP tools.

Available tools:
1. add_student(name, age, course) - Add a new student
2. find_students(name?, age?, course?) - Find by any field or get all
3. update_student(student_id, name?, age?, course?) - Update student
4. delete_student(student_id) - Delete student

Examples:
{"tool": "find_students", "args": {}}  // Get all students
{"tool": "find_students", "args": {"name": "pat"}}  // Find by name
{"tool": "find_students", "args": {"course": "CS"}}  // Find by course
{"tool": "find_students", "args": {"age": 20}}  // Find by age
{"tool": "find_students", "args": {"name": "pat", "course": "AI"}}  // Combine filters
"""

    HUMANIZE_PROMPT = """You are a friendly assistant helping manage a student database.

The user asked: "{user_query}"
You executed: {tool_name} with {args}
Result: {tool_result}

Provide a natural, conversational response that:
- Summarizes what was done clearly
- Presents data in a friendly, easy-to-read format
- Uses emojis appropriately (📚, ✅, 📊, 🎓, etc.)
- Format lists and statistics nicely
- Be concise but informative
- Sounds helpful and encouraging

Respond naturally as if chatting with a friend."""

    def __init__(self, model):
        super().__init__(model, self.SYSTEM_PROMPT, self.HUMANIZE_PROMPT)


# =================== FILE SYSTEM AGENT ===================
class FileAgent(BaseAgent):
    SYSTEM_PROMPT = """You are an intelligent file system assistant managing files via MCP tools.

Available tools:
1. create_file(filename, path=".", content="") - Create a new file with optional content
   Example: {"tool": "create_file", "args": {"filename": "test.txt", "path": "desktop", "content": "Hello"}}

2. create_folder(folder_name, path=".") - Create a new folder
   Example: {"tool": "create_folder", "args": {"folder_name": "MyFolder", "path": "desktop"}}

3. create_folders_batch(folder_names, path=".") - Create multiple folders at once (max 10)
   Example: {"tool": "create_folders_batch", "args": {"folder_names": ["folder1", "folder2"], "path": "desktop"}}

4. list_directory(path=".") - List all files and folders in a directory
   Example: {"tool": "list_directory", "args": {"path": "desktop"}}

5. delete_file(file_path) - Delete a single file
   Example: {"tool": "delete_file", "args": {"file_path": "desktop/test.txt"}}

6. delete_folder(folder_path, recursive=False) - Delete a folder (use recursive=True for non-empty folders)
   Example: {"tool": "delete_folder", "args": {"folder_path": "desktop/old_folder", "recursive": true}}

7. rename_item(old_path, new_name) - Rename a file or folder
   Example: {"tool": "rename_item", "args": {"old_path": "desktop/old.txt", "new_name": "new.txt"}}

8. check_path_exists(path) - Check if a file or folder exists
   Example: {"tool": "check_path_exists", "args": {"path": "desktop/myfile.txt"}}

9. get_current_directory() - Get the current working directory
   Example: {"tool": "get_current_directory", "args": {}}

IMPORTANT PATH HANDLING:
- You can use "desktop" keyword in paths (e.g., "desktop/test.txt")
- Paths are automatically normalized for the user's OS
- Use "." for current directory

CRITICAL: Respond with ONLY valid JSON:
{"tool": "tool_name", "args": {...}}
"""

    HUMANIZE_PROMPT = """You are a friendly file system assistant helping users manage their files.

The user asked: "{user_query}"
You executed: {tool_name} with {args}
Result: {tool_result}

Provide a natural, conversational response that:
- Summarizes what was done clearly
- Presents file/folder information in an organized format
- Uses emojis appropriately (📁, 📄, ✅, 🔍, etc.)
- For file lists, show them in a readable way
- Be concise but informative
- Sounds helpful and friendly

Respond naturally as if chatting with a friend."""

    def __init__(self, model):
        super().__init__(model, self.SYSTEM_PROMPT, self.HUMANIZE_PROMPT)


# =================== SAFE RESULT EXTRACTION ===================
def extract_text_from_content(content):
    """Safely extract text from MCP result content - handles all types"""
    if content is None:
        return ""
    
    # If it's a string, return it
    if isinstance(content, str):
        return content
    
    # If it's a list
    if isinstance(content, list):
        if len(content) == 0:
            return ""
        
        # Get first item
        first_item = content[0]
        
        # If first item is a dict, try to get 'text' key
        if isinstance(first_item, dict):
            return first_item.get('text', str(first_item))
        
        # If first item has 'text' attribute
        if hasattr(first_item, 'text'):
            return first_item.text
        
        # Otherwise convert to string
        return str(first_item)
    
    # If it's a dict, try to get 'text' key
    if isinstance(content, dict):
        return content.get('text', str(content))
    
    # If it has 'text' attribute
    if hasattr(content, 'text'):
        return content.text
    
    # Last resort: convert to string
    return str(content)


# =================== AGENT EXECUTOR ===================
async def execute_agent(agent, mcp_server_path: str, user_query: str, session_id: str = None):
    """Execute an agent with its MCP server"""
    try:
        # Get conversation history
        conversation_history = get_or_create_session(session_id) if session_id else None
        
        async with Client(mcp_server_path) as mcp_client:
            # Plan the tool call with history
            tool_call = await agent.plan_tool_call(user_query, conversation_history)
            if not tool_call:
                return {
                    "success": False,
                    "error": "Could not understand your request. Try being more specific."
                }

            tool_name = tool_call.get("tool")
            args = tool_call.get("args", {})

            # Execute the tool
            result = await mcp_client.call_tool(tool_name, arguments=args)

            # Extract raw tool result using safe extraction
            raw_result = ""
            
            # Try to get content from result
            if hasattr(result, 'content'):
                raw_result = extract_text_from_content(result.content)
            elif isinstance(result, dict) and "content" in result:
                raw_result = extract_text_from_content(result["content"])
            else:
                # If no content field, convert entire result to JSON
                raw_result = json.dumps(result, indent=2, default=str)
            
            # If we still don't have a result, use the whole object
            if not raw_result:
                raw_result = str(result)
            
            # Humanize the response
            humanized = await agent.humanize_response(user_query, tool_name, args, raw_result)

            # Store in conversation history
            if session_id:
                add_to_session(session_id, "user", user_query)
                add_to_session(session_id, "assistant", humanized)
            
            # Create a NEW dictionary for each insert (don't reuse)
            chat_record = {
                'session_id': session_id or 'default',
                'user_query': user_query,
                'tool_used': tool_name,
                'tool_args': args,
                'mcp_result': raw_result,
                'humanized_result': humanized,
                'timestamp': datetime.utcnow()
            }
            
            # Insert into MongoDB
            collection.insert_one(chat_record)

            return {
                "success": True,
                "tool_name": tool_name,
                "args": args,
                "raw_result": raw_result,
                "response": humanized
            }

    except Exception as e:
        # Log the error for debugging
        import traceback
        print(f"❌ Error in execute_agent: {str(e)}")
        print(f"🔍 Traceback: {traceback.format_exc()}")
        return {
            "success": False,
            "error": str(e)
        }


# =================== ASYNC ROUTE WRAPPER ===================
def async_route(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        return asyncio.run(f(*args, **kwargs))
    return wrapped


# =================== API ROUTES ===================

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "agents": ["email", "mongo", "file"]
    })


@app.route('/api/email', methods=['POST'])
@async_route
async def email_endpoint():
    """Email agent endpoint"""
    data = request.json
    user_query = data.get('query', '')
    session_id = data.get('session_id', 'default')
    
    if not user_query:
        return jsonify({"success": False, "error": "Query is required"}), 400
    
    agent = EmailAgent(model)
    result = await execute_agent(agent, "MCP_Servers/email_mcp_server/fastmcp_email_server.py", user_query, session_id)
    
    return jsonify(result), 200 if result["success"] else 400


@app.route('/api/mongo', methods=['POST'])
@async_route
async def mongo_endpoint():
    """MongoDB agent endpoint"""
    data = request.json
    user_query = data.get('query', '')
    session_id = data.get('session_id', 'default')
    
    if not user_query:
        return jsonify({"success": False, "error": "Query is required"}), 400
    
    agent = MongoAgent(model)
    result = await execute_agent(agent, "MCP_Servers/mongo_mcp_server/fastmcp_mongo_server.py", user_query, session_id)
    
    return jsonify(result), 200 if result["success"] else 400


@app.route('/api/file', methods=['POST'])
@async_route
async def file_endpoint():
    """File system agent endpoint"""
    data = request.json
    user_query = data.get('query', '')
    session_id = data.get('session_id', 'default')
    
    if not user_query:
        return jsonify({"success": False, "error": "Query is required"}), 400
    
    agent = FileAgent(model)
    result = await execute_agent(agent, "./MCP_Servers/file_mcp_server/fastmcp_file_server.py", user_query, session_id)
    
    return jsonify(result), 200 if result["success"] else 400




@app.route('/api/agents', methods=['GET'])
def list_agents():
    """List all available agents"""
    return jsonify({
        "agents": [
            {
                "name": "email",
                "endpoint": "/api/email",
                "description": "Complete email management (send, fetch, search, organize, delete)",
                "capabilities": [
                    "Send emails (text/HTML)",
                    "Reply and forward",
                    "Search and filter",
                    "Organize (flag, move, mark)",
                    "Count and get statistics"
                ],
                "example_queries": [
                    "Send email to john@example.com about meeting",
                    "Show my last 10 unread emails",
                    "Search for emails from Sarah",
                    "Count unread emails in my inbox",
                    "Mark email 123 as read",
                    "Delete all emails from spam@example.com"
                ]
            },
            {
                "name": "mongo",
                "endpoint": "/api/mongo",
                "description": "Complete student database management (CRUD + Analytics)",
                "capabilities": [
                    "Add and update students",
                    "Query and search",
                    "Delete records",
                    "Statistical analysis",
                    "Sorting and filtering"
                ],
                "example_queries": [
                    "Add a student named Alice, age 20, course CS",
                    "Show all students in AI course",
                    "Count students older than 25",
                    "Get average age by course",
                    "Search for students with 'computer' in name or course",
                    "Delete student named Bob"
                ]
            },
            {
                "name": "file",
                "endpoint": "/api/file",
                "description": "Complete file system management (read, write, organize)",
                "capabilities": [
                    "List and search files",
                    "Read and write files",
                    "Create and delete folders",
                    "Move and copy files",
                    "Get file information"
                ],
                "example_queries": [
                    "List files in my desktop",
                    "Create a file called notes.txt with 'Hello World'",
                    "Read the contents of config.json",
                    "Create a folder called 'Projects'",
                    "Search for all Python files in current directory",
                    "Move test.txt to Documents folder"
                ]
            }
        ]
    })


@app.route('/api/session/clear', methods=['POST'])
def clear_session():
    """Clear conversation history for a session"""
    data = request.json
    session_id = data.get('session_id', 'default')
    
    if session_id in conversation_sessions:
        del conversation_sessions[session_id]
        return jsonify({"success": True, "message": f"Session {session_id} cleared"})
    
    return jsonify({"success": False, "message": "Session not found"}), 404


@app.route('/api/session/history', methods=['POST'])
def get_session_history():
    """Get conversation history for a session"""
    data = request.json
    session_id = data.get('session_id', 'default')
    
    history = get_or_create_session(session_id)
    return jsonify({"session_id": session_id, "history": history})


@app.route('/api/session/chats', methods=['POST'])
def get_session_chats():
    """Get all MongoDB chat logs for a session"""
    data = request.json
    session_id = data.get('session_id', 'default')
    
    chats = list(collection.find(
        {'session_id': session_id},
        {'_id': 0}
    ).sort('timestamp', -1))
    
    return jsonify({
        "session_id": session_id,
        "total_chats": len(chats),
        "chats": chats
    })


# =================== ERROR HANDLERS ===================
@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Endpoint not found"}), 404

@app.errorhandler(500)
def internal_error(e):
    return jsonify({"error": "Internal server error", "details": str(e)}), 500


# =================== MAIN ===================
if __name__ == '__main__':
    print("🚀 Starting Unified Flask Agent Gateway")
    print("=" * 60)
    print("📧 Email Agent:    POST /api/email")
    print("🗄️  MongoDB Agent:  POST /api/mongo")
    print("📁 File Agent:     POST /api/file")
    print("📋 List Agents:    GET  /api/agents")
    print("❤️  Health Check:  GET  /health")
    print("🔄 Session History: POST /api/session/history")
    print("🗑️  Clear Session:  POST /api/session/clear")
    print("💾 Session Chats:  POST /api/session/chats")
    print("=" * 60)
    app.run(port=5000, host='0.0.0.0')