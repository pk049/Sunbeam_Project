from flask import Flask, request, jsonify
from flask_cors import CORS
from pymongo import MongoClient
from bson import json_util
import uuid
import json
from datetime import datetime, timezone

app = Flask(__name__)
CORS(app)

client = MongoClient("mongodb://localhost:27017/")
db = client.chat_app

# Helper function to serialize MongoDB documents
def serialize_doc(doc):
    """Convert MongoDB document to JSON-serializable format"""
    return json.loads(json_util.dumps(doc))

# Create a new session
@app.route("/create_session", methods=["POST"])
def create_session():
    try:
        data = request.json
        session_id = str(uuid.uuid4())
        session = {
            "session_id": session_id,
            "title": data.get("title", "New Chat"),
            "agent": data.get("agent", "email"),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        db.chat_sessions.insert_one(session.copy())
        # Remove _id before returning
        session.pop('_id', None)
        return jsonify(session), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Save message
@app.route("/save_message", methods=["POST"])
def save_message():
    try:
        data = request.json
        
        if not data.get("session_id") or not data.get("sender") or not data.get("message"):
            return jsonify({"error": "Missing required fields"}), 400
        
        msg = {
            "session_id": data["session_id"],
            "sender": data["sender"],  # 'user' or 'agent'
            "message": data["message"],
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        db.chat_messages.insert_one(msg.copy())
        
        # Update session's updated_at timestamp
        db.chat_sessions.update_one(
            {"session_id": data["session_id"]},
            {"$set": {"updated_at": datetime.now(timezone.utc).isoformat()}}
        )
        
        return jsonify({"status": "ok", "message": "Message saved"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Get session list (for sidebar)
@app.route("/get_sessions", methods=["GET"])
def get_sessions():
    try:
        sessions = list(db.chat_sessions.find({}, {"_id": 0}).sort("updated_at", -1))
        return jsonify(sessions), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Get full chat history of a session
@app.route("/get_history/<session_id>", methods=["GET"])
def get_history(session_id):
    try:
        messages = list(db.chat_messages.find(
            {"session_id": session_id}, 
            {"_id": 0}
        ).sort("timestamp", 1))
        return jsonify(messages), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Delete a session and its messages
@app.route("/delete_session/<session_id>", methods=["DELETE"])
def delete_session(session_id):
    try:
        # Delete all messages in the session
        db.chat_messages.delete_many({"session_id": session_id})
        # Delete the session
        result = db.chat_sessions.delete_one({"session_id": session_id})
        
        if result.deleted_count > 0:
            return jsonify({"status": "ok", "message": "Session deleted"}), 200
        else:
            return jsonify({"error": "Session not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Update session title
@app.route("/update_session/<session_id>", methods=["PATCH"])
def update_session(session_id):
    try:
        data = request.json
        title = data.get("title")
        
        if not title:
            return jsonify({"error": "Title is required"}), 400
        
        result = db.chat_sessions.update_one(
            {"session_id": session_id},
            {"$set": {
                "title": title,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }}
        )
        
        if result.modified_count > 0:
            return jsonify({"status": "ok", "message": "Session updated"}), 200
        else:
            return jsonify({"error": "Session not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Health check endpoint
@app.route("/health", methods=["GET"])
def health():
    try:
        # Test MongoDB connection
        client.admin.command('ping')
        return jsonify({
            "status": "healthy",
            "mongodb": "connected",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }), 200
    except Exception as e:
        return jsonify({
            "status": "unhealthy",
            "error": str(e)
        }), 500

if __name__ == "__main__":
    print("🚀 Chat History API starting on http://127.0.0.1:5001")
    print("📊 MongoDB connection: mongodb://localhost:27017/")
    print("💾 Database: chat_app")
    app.run(host="127.0.0.1", port=5001, debug=True)