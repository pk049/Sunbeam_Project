from mcp.server.fastmcp import FastMCP
import asyncio
import sys
import os
from pathlib import Path
from typing import Optional, List
import platform

# =============== FASTMCP SERVER ===============
mcp = FastMCP("file-mcp-server")

# =============== CONSTANTS & HELPERS ===============
MAX_BATCH_OPERATIONS = 10  # Safety limit for batch operations

def get_desktop_path() -> str:
    """Get the desktop path for the current OS"""
    if platform.system() == "Windows":
        return os.path.join(os.path.expanduser("~"),"OneDrive", "Desktop")
    elif platform.system() == "Darwin":  # macOS
        return os.path.join(os.path.expanduser("~"), "Desktop")
    else:  # Linux
        return os.path.join(os.path.expanduser("~"), "Desktop")


def normalize_path(path: str) -> str:
    """Convert path to OS-specific format and expand special keywords"""
    path = path.strip()
    path_lower = path.lower()
    
    # Handle "desktop" keyword specially
    if path_lower == "desktop":
        return get_desktop_path()
    elif path_lower.startswith("desktop/") or path_lower.startswith("desktop\\"):
        # Extract subpath after "desktop/"
        subpath = path.split(os.sep, 1)[1] if os.sep in path else path.split("/", 1)[1]
        return os.path.join(get_desktop_path(), subpath)
    
    # For regular paths, expand and normalize
    path = os.path.expanduser(path)
    
    if not os.path.isabs(path):
        path = os.path.abspath(path)
    
    path = os.path.normpath(path)
    
    return path


def safe_operation_check(count: int, operation: str) -> Optional[str]:
    """Check if operation count exceeds safety limit"""
    if count > MAX_BATCH_OPERATIONS:
        return f"❌ Safety limit exceeded: Cannot {operation} more than {MAX_BATCH_OPERATIONS} items at once"
    return None


# =============== TOOLS ===============

@mcp.tool()
async def create_file(filename: str = "new_file.txt", path: str = ".", content: str = "") -> str:
    """
    Create a new file with optional content.
    
    Args:
        filename: Name of the file (default: new_file.txt)
        path: Directory path where file should be created (default: current directory)
              Can use 'desktop' keyword for desktop location
        content: Optional content to write to the file
    
    Returns:
        Success message with full file path or error message
    """
    try:
        # Normalize path
        target_path = normalize_path(path)
        
        # Create directory if it doesn't exist
        if not os.path.exists(target_path):
            os.makedirs(target_path, exist_ok=True)
        
        # Create full file path
        file_path = os.path.join(target_path, filename)
        
        # Check if file already exists
        if os.path.exists(file_path):
            return f"⚠️ File already exists: {file_path}"
        
        # Create file
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        return f"✅ File created successfully: {file_path}"
    
    except PermissionError:
        return f"❌ Permission denied: Cannot create file at {path}"
    except Exception as e:
        return f"❌ Error creating file: {str(e)}"


@mcp.tool()
async def create_folder(folder_name: str, path: str = ".") -> str:
    """
    Create a new folder at the specified location.
    
    Args:
        folder_name: Name of the folder to create
        path: Parent directory path (default: current directory)
              Can use 'desktop' keyword for desktop location
    
    Returns:
        Success message with full folder path or error message
    """
    try:
        # Normalize path
        target_path = normalize_path(path)
        
        # Create full folder path
        folder_path = os.path.join(target_path, folder_name)
        
        # Check if folder already exists
        if os.path.exists(folder_path):
            return f"⚠️ Folder already exists: {folder_path}"
        
        # Create folder (including parent directories if needed)
        os.makedirs(folder_path, exist_ok=True)
        
        return f"✅ Folder created successfully: {folder_path}"
    
    except PermissionError:
        return f"❌ Permission denied: Cannot create folder at {path}"
    except Exception as e:
        return f"❌ Error creating folder: {str(e)}"


@mcp.tool()
async def create_folders_batch(folder_names: List[str], path: str = ".") -> str:
    """
    Create multiple folders at once (max 10 for safety).
    
    Args:
        folder_names: List of folder names to create
        path: Parent directory path (default: current directory)
              Can use 'desktop' keyword for desktop location
    
    Returns:
        Summary of created folders or error message
    """
    try:
        # Safety check
        error = safe_operation_check(len(folder_names), "create")
        if error:
            return error
        
        # Normalize path
        target_path = normalize_path(path)
        
        created = []
        skipped = []
        errors = []
        
        for folder_name in folder_names:
            try:
                folder_path = os.path.join(target_path, folder_name)
                
                if os.path.exists(folder_path):
                    skipped.append(folder_name)
                else:
                    os.makedirs(folder_path, exist_ok=True)
                    created.append(folder_name)
            except Exception as e:
                errors.append(f"{folder_name}: {str(e)}")
        
        result = f"✅ Batch folder creation completed:\n"
        result += f"  • Created: {len(created)} folder(s)\n"
        result += f"  • Skipped (already exist): {len(skipped)}\n"
        result += f"  • Errors: {len(errors)}\n"
        result += f"  • Location: {target_path}\n"
        
        if errors:
            result += f"\n❌ Errors encountered:\n"
            for error in errors[:5]:  # Show first 5 errors
                result += f"  - {error}\n"
        
        return result
    
    except Exception as e:
        return f"❌ Error in batch creation: {str(e)}"


@mcp.tool()
async def list_directory(path: str = ".") -> str:
    """
    List all files and folders in a directory.
    
    Args:
        path: Directory path to list (default: current directory)
              Can use 'desktop' keyword for desktop location
    
    Returns:
        Formatted list of directory contents or error message
    """
    try:
        # Normalize path
        target_path = normalize_path(path)
        
        if not os.path.exists(target_path):
            return f"❌ Path does not exist: {target_path}"
        
        if not os.path.isdir(target_path):
            return f"❌ Not a directory: {target_path}"
        
        items = os.listdir(target_path)
        
        if not items:
            return f"📂 Directory is empty: {target_path}"
        
        folders = [item for item in items if os.path.isdir(os.path.join(target_path, item))]
        files = [item for item in items if os.path.isfile(os.path.join(target_path, item))]
        
        result = f"📂 Contents of: {target_path}\n\n"
        
        if folders:
            result += f"Folders ({len(folders)}):\n"
            for folder in sorted(folders):
                result += f"  📁 {folder}\n"
            result += "\n"
        
        if files:
            result += f"Files ({len(files)}):\n"
            for file in sorted(files):
                result += f"  📄 {file}\n"
        
        return result
    
    except PermissionError:
        return f"❌ Permission denied: Cannot access {path}"
    except Exception as e:
        return f"❌ Error listing directory: {str(e)}"


@mcp.tool()
async def delete_file(file_path: str) -> str:
    """
    Delete a single file.
    
    Args:
        file_path: Full path to the file to delete
    
    Returns:
        Success message or error message
    """
    try:
        # Normalize path
        target_path = normalize_path(file_path)
        
        if not os.path.exists(target_path):
            return f"❌ File does not exist: {target_path}"
        
        if not os.path.isfile(target_path):
            return f"❌ Not a file: {target_path}"
        
        os.remove(target_path)
        return f"🗑️ File deleted successfully: {target_path}"
    
    except PermissionError:
        return f"❌ Permission denied: Cannot delete {file_path}"
    except Exception as e:
        return f"❌ Error deleting file: {str(e)}"


@mcp.tool()
async def delete_folder(folder_path: str, recursive: bool = False) -> str:
    """
    Delete a folder (empty by default, or with contents if recursive=True).
    
    Args:
        folder_path: Full path to the folder to delete
        recursive: If True, delete folder and all contents (USE WITH CAUTION)
    
    Returns:
        Success message or error message
    """
    try:
        # Normalize path
        target_path = normalize_path(folder_path)
        
        if not os.path.exists(target_path):
            return f"❌ Folder does not exist: {target_path}"
        
        if not os.path.isdir(target_path):
            return f"❌ Not a folder: {target_path}"
        
        if recursive:
            import shutil
            shutil.rmtree(target_path)
            return f"🗑️ Folder and all contents deleted: {target_path}"
        else:
            os.rmdir(target_path)
            return f"🗑️ Folder deleted: {target_path}"
    
    except OSError as e:
        if "not empty" in str(e).lower():
            return f"❌ Folder is not empty. Use recursive=True to delete contents: {folder_path}"
        return f"❌ Error deleting folder: {str(e)}"
    except PermissionError:
        return f"❌ Permission denied: Cannot delete {folder_path}"
    except Exception as e:
        return f"❌ Error deleting folder: {str(e)}"


@mcp.tool()
async def rename_item(old_path: str, new_name: str) -> str:
    """
    Rename a file or folder.
    
    Args:
        old_path: Current path of the file/folder
        new_name: New name (not full path, just the name)
    
    Returns:
        Success message with new path or error message
    """
    try:
        # Normalize path
        old_path_normalized = normalize_path(old_path)
        
        if not os.path.exists(old_path_normalized):
            return f"❌ Path does not exist: {old_path_normalized}"
        
        # Create new path
        parent_dir = os.path.dirname(old_path_normalized)
        new_path = os.path.join(parent_dir, new_name)
        
        if os.path.exists(new_path):
            return f"❌ Target already exists: {new_path}"
        
        os.rename(old_path_normalized, new_path)
        return f"✅ Renamed successfully: {old_path_normalized} → {new_path}"
    
    except PermissionError:
        return f"❌ Permission denied: Cannot rename {old_path}"
    except Exception as e:
        return f"❌ Error renaming: {str(e)}"


@mcp.tool()
async def check_path_exists(path: str) -> str:
    """
    Check if a file or folder exists at the given path.
    
    Args:
        path: Path to check
    
    Returns:
        Information about the path
    """
    try:
        # Normalize path
        target_path = normalize_path(path)
        
        if not os.path.exists(target_path):
            return f"❌ Path does not exist: {target_path}"
        
        if os.path.isfile(target_path):
            size = os.path.getsize(target_path)
            return f"✅ File exists: {target_path}\n  Size: {size} bytes"
        elif os.path.isdir(target_path):
            items = len(os.listdir(target_path))
            return f"✅ Folder exists: {target_path}\n  Contains: {items} item(s)"
        else:
            return f"✅ Path exists: {target_path}\n  Type: Unknown"
    
    except Exception as e:
        return f"❌ Error checking path: {str(e)}"


@mcp.tool()
async def get_current_directory() -> str:
    """
    Get the current working directory.
    
    Returns:
        Current working directory path
    """
    try:
        cwd = os.getcwd()
        return f"📍 Current working directory: {cwd}"
    except Exception as e:
        return f"❌ Error getting current directory: {str(e)}"


# =============== RUN SERVER ===============
if __name__ == "__main__":
    print(f"🚀 File MCP Server starting...", file=sys.stderr)
    print(f"💻 Platform: {platform.system()}", file=sys.stderr)
    print(f"🖥️ Desktop path: {get_desktop_path()}", file=sys.stderr)
    print(f"📁 Current directory: {os.getcwd()}", file=sys.stderr)
    print(f"\n📋 Available tools (9):", file=sys.stderr)
    print(f"  CREATE: create_file, create_folder, create_folders_batch", file=sys.stderr)
    print(f"  READ: list_directory, check_path_exists, get_current_directory", file=sys.stderr)
    print(f"  UPDATE: rename_item", file=sys.stderr)
    print(f"  DELETE: delete_file, delete_folder", file=sys.stderr)
    asyncio.run(mcp.run())