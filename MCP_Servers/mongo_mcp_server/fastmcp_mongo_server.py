from mcp.server.fastmcp import FastMCP
from pymongo import MongoClient
from bson import ObjectId
import sys
from typing import Optional

# =================== DATABASE CONNECTION ===================
try:
    client = MongoClient("mongodb://localhost:27017/", serverSelectionTimeoutMS=5000)
    client.server_info()
    db = client["newdb"]
    students_col = db["students"]
    print("✅ Connected to MongoDB", file=sys.stderr)
except Exception as e:
    print(f"❌ MongoDB connection failed: {e}", file=sys.stderr)
    sys.exit(1)

# =================== HELPER ===================
def convert_objectid(doc):
    if doc and "_id" in doc:
        doc["_id"] = str(doc["_id"])
    return doc

# =================== FASTMCP SERVER ===================
mcp = FastMCP("student-database-server")







# =================== CREATE ===================
@mcp.tool()
async def add_student(name: str, age: int, course: str) -> str:
    """Add a new student"""
    try:
        doc = {"name": name, "age": age, "course": course}
        result = students_col.insert_one(doc)
        return f"✅ Added: {name}, Age: {age}, Course: {course}"
    except Exception as e:
        return f"❌ Error: {str(e)}"



# =================== READ ===================
@mcp.tool()
async def find_students(name: Optional[str] = None, age: Optional[int] = None, course: Optional[str] = None) -> str:
    """Find students by name, age, course, or get all if no params given"""
    try:
        query = {}
        
        if name:
            query["name"] = {"$regex": name, "$options": "i"}
        if age:
            query["age"] = age
        if course:
            query["course"] = {"$regex": course, "$options": "i"}
        
        docs = list(students_col.find(query))
        for d in docs:
            convert_objectid(d)
        
        if not docs:
            return "No students found."
        
        result = f"Found {len(docs)} student(s):\n"
        for i, s in enumerate(docs, 1):
            result += f"{i}. {s.get('name')} (ID: {s.get('_id')}, Age: {s.get('age')}, Course: {s.get('course')})\n"
        return result
    except Exception as e:
        return f"❌ Error: {str(e)}"

# =================== UPDATE ===================
@mcp.tool()
async def update_student(student_id: str, name: Optional[str] = None, age: Optional[int] = None, course: Optional[str] = None) -> str:
    """Update student by ID"""
    try:
        update_data = {}
        if name:
            update_data["name"] = name
        if age:
            update_data["age"] = age
        if course:
            update_data["course"] = course
        
        if not update_data:
            return "❌ No fields to update"
        
        result = students_col.update_one({"_id": ObjectId(student_id)}, {"$set": update_data})
        
        if result.matched_count == 0:
            return f"❌ No student found with ID: {student_id}"
        
        return f"✅ Updated student"
    except Exception as e:
        return f"❌ Error: {str(e)}"

# =================== DELETE ===================
@mcp.tool()
async def delete_student(student_id: str) -> str:
    """Delete student by ID"""
    try:
        result = students_col.delete_one({"_id": ObjectId(student_id)})
        
        if result.deleted_count == 0:
            return f"❌ No student found with ID: {student_id}"
        
        return f"🗑️ Deleted student"
    except Exception as e:
        return f"❌ Error: {str(e)}"
    
    
    

# =================== RUN SERVER ===================
if __name__ == "__main__":
    print("🚀 MongoDB MCP Server starting...", file=sys.stderr)
    print("📋 Tools: add_student, find_students, update_student, delete_student", file=sys.stderr)
    mcp.run()