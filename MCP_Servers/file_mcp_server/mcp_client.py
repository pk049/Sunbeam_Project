import asyncio
import google.generativeai as genai
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import json
from typing import Optional

# =================== CONFIGURATION ===================
GEMINI_API_KEY = "AIzaSyAwlSVufxkTFCnu9e54zTs5QAdmIlg-_-8"  # Replace with your API key
MCP_SERVER_PATH = "file_server.py"  # Path to your MCP server file

# =================== SETUP GEMINI ===================
genai.configure(api_key=GEMINI_API_KEY)

# Configure Gemini model
generation_config = {
    "temperature": 0.7,
    "top_p": 0.95,
    "top_k": 40,
    "max_output_tokens": 8192,
}


# =================== MCP CLIENT ===================
class FileMCPClient:
    def __init__(self):
        self.session: Optional[ClientSession] = None
        self.tools = []
        self.chat = None  # Store chat instance
        self.model_with_tools = None  # Store model instance
        
    async def initialize(self):
        """Initialize and list available tools"""
        await self.session.initialize()
        response = await self.session.list_tools()
        self.tools = response.tools
        
        print("✅ Connected to File MCP Server")
        print(f"📋 Available tools: {len(self.tools)}")
        for tool in self.tools:
            print(f"   • {tool.name}: {tool.description}")
        print()
        
        # Convert tools once and create model once
        gemini_tools = self.get_tools_for_gemini()
        
        system_instruction = """You are a helpful AI assistant with access to file system tools.

For general questions (explanations, facts, advice), answer directly without using tools.
Only use tools when the user explicitly asks you to interact with files or the file system.

Examples:
- "What is Python?" → Answer directly
- "Tell me about async" → Answer directly  
- "List my files" → Use list_files tool
- "Create test.txt" → Use create_file tool
"""
        
        self.model_with_tools = genai.GenerativeModel(
            model_name="gemini-2.5-flash",
            generation_config=generation_config,
            tools=[{"function_declarations": gemini_tools}],
            system_instruction=system_instruction
        )
        # Start chat once
        self.chat = self.model_with_tools.start_chat()
        print("🤖 Gemini agent initialized with tools\n")
    
    def get_tools_for_gemini(self):
        """Convert MCP tools to Gemini function declarations"""
        function_declarations = []
        
        for tool in self.tools:
            properties = {}
            required = []
            
            if hasattr(tool, 'inputSchema') and tool.inputSchema:
                schema = tool.inputSchema
                if 'properties' in schema:
                    for prop_name, prop_info in schema['properties'].items():
                        param_type = prop_info.get('type', 'string').upper()
                        
                        type_mapping = {
                            'STRING': 'STRING',
                            'INTEGER': 'INTEGER',
                            'NUMBER': 'NUMBER',
                            'BOOLEAN': 'BOOLEAN',
                            'ARRAY': 'ARRAY',
                            'OBJECT': 'OBJECT'
                        }
                        
                        gemini_type = type_mapping.get(param_type, 'STRING')
                        
                        prop_def = {
                            "type": gemini_type,
                            "description": prop_info.get('description', '')
                        }
                        
                        if gemini_type == 'ARRAY':
                            items_info = prop_info.get('items', {})
                            items_type = items_info.get('type', 'string').upper()
                            prop_def["items"] = {
                                "type": type_mapping.get(items_type, 'STRING')
                            }
                        
                        properties[prop_name] = prop_def
                
                if 'required' in schema:
                    required = schema['required']
            
            function_declarations.append({
                "name": tool.name,
                "description": tool.description or f"Execute {tool.name}",
                "parameters": {
                    "type": "OBJECT",
                    "properties": properties,
                    "required": required
                }
            })
        
        return function_declarations
    
    async def call_tool(self, tool_name: str, arguments: dict):
        """Call an MCP tool and return the result"""
        try:
            result = await self.session.call_tool(tool_name, arguments)
            
            if hasattr(result, 'content'):
                for content in result.content:
                    if hasattr(content, 'text'):
                        return content.text
            
            return str(result)
            
        except Exception as e:
            return f"❌ Error calling tool {tool_name}: {str(e)}"
    
    async def process_user_message(self, user_message: str):
        """Process user message with Gemini and execute tools if needed"""
        print(f"\n💭 You: {user_message}")
        print("-" * 80)
        
        # Just send message to existing chat (no recreation!)
        response = self.chat.send_message(user_message)
        
        # Process function calls
        while (response.candidates 
               and response.candidates[0].content.parts 
               and response.candidates[0].content.parts[0].function_call):
            
            function_call = response.candidates[0].content.parts[0].function_call
            
            tool_name = function_call.name
            tool_args = dict(function_call.args)
            
            print(f"🔧 Gemini wants to use tool: {tool_name}")
            print(f"   Arguments: {json.dumps(tool_args, indent=2)}")
            
            tool_result = await self.call_tool(tool_name, tool_args)
            
            print(f"📤 Tool result:\n{tool_result}\n")
            
            response = self.chat.send_message(
                genai.protos.Content(
                    parts=[genai.protos.Part(
                        function_response=genai.protos.FunctionResponse(
                            name=tool_name,
                            response={"result": tool_result}
                        )
                    )]
                )
            )
        
        final_response = response.text
        
        print(f"🤖 Gemini: {final_response}")
        print("=" * 80)
        
        return final_response


# =================== MAIN CLI ===================
async def main():
    print("=" * 80)
    print("🚀 File MCP Client with Gemini 2.5 Flash")
    print("=" * 80)
    print()
    
    if GEMINI_API_KEY == "YOUR_GEMINI_API_KEY_HERE":
        print("⚠️  Please set your Gemini API key in the script!")
        print("   Get your API key from: https://aistudio.google.com/app/apikey")
        return
    
    server_params = StdioServerParameters(
        command="python",
        args=[MCP_SERVER_PATH],
        env=None
    )
    
    try:
        async with stdio_client(server_params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                client = FileMCPClient()
                client.session = session
                
                await client.initialize()
                
                print("\n💡 Examples:")
                print("   • Create a file called test.txt on desktop")
                print("   • Make 5 folders named folder1 to folder5 in desktop")
                print("   • List files in my desktop")
                print("   • Delete the file test.txt from desktop")
                print("   • What's my current directory?")
                print("   • What is Python? (general question)")
                print()
                print("Type 'exit' or 'quit' to stop\n")
                print("=" * 80)
                
                while True:
                    try:
                        user_input = input("\n💬 You: ").strip()
                        
                        if not user_input:
                            continue
                        
                        if user_input.lower() in ['exit', 'quit', 'q']:
                            print("\n👋 Goodbye!")
                            break
                        
                        await client.process_user_message(user_input)
                        
                    except KeyboardInterrupt:
                        print("\n\n👋 Goodbye!")
                        break
                    except Exception as e:
                        print(f"\n❌ Error: {e}")
                        import traceback
                        traceback.print_exc()
                        
    except Exception as e:
        print(f"❌ Failed to connect to MCP server: {e}")
        import traceback
        traceback.print_exc()


# =================== RUN ===================
if __name__ == "__main__":
    asyncio.run(main())