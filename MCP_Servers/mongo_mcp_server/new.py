import asyncio
from fastmcp import Client

async def main():
    async with Client("fastmcp_mongo_server") as mcp_client:
        
        