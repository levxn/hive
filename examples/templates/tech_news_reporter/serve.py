"""
Serve Tech News Reporter as an MCP Server.

Arguments:
    --port: Port to run the server on (default: 8000)
    --host: Host to run the server on (default: 0.0.0.0)

Usage:
    uv run python -m examples.templates.tech_news_reporter.serve
"""

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Annotated, Any, Dict

# 1. Setup paths to allow imports from project root
# We need to find the root 'hive' directory
file_path = Path(__file__).resolve()
# examples/templates/tech_news_reporter/serve.py -> 4 levels up to root
project_root = file_path.parent.parent.parent.parent

if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Also add tools/src to path for aden_tools
tools_path = project_root / "tools" / "src"
if str(tools_path) not in sys.path:
    sys.path.insert(0, str(tools_path))

try:
    from fastmcp import FastMCP
    from starlette.requests import Request
    from starlette.responses import JSONResponse
except ImportError:
    print("Error: Required packages not installed.")
    print("Please install: fastmcp starlette uvicorn")
    sys.exit(1)

# Import the agent using absolute path to avoid relative import issues
try:
    from examples.templates.tech_news_reporter.agent import TechNewsReporterAgent
except ImportError:
    # If running from within the directory, try to adjust properly
    # forcing absolute import by ensuring root is in path (done above)
    try:
        from examples.templates.tech_news_reporter.agent import TechNewsReporterAgent
    except Exception as e:
        print(f"Error importing TechNewsReporterAgent: {e}")
        print(f"PYTHONPATH: {sys.path}")
        sys.exit(1)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("tech_news_server")

# Initialize FastMCP
mcp = FastMCP("tech-news-reporter")

# Global agent instance
_agent = None

def get_or_create_agent():
    """Get the global agent instance or create one."""
    global _agent
    if _agent is None:
        logger.info("Initializing TechNewsReporterAgent...")
        _agent = TechNewsReporterAgent()
    return _agent

@mcp.tool()
async def run_tech_news_reporter(
    topic: Annotated[str, "Main topic to research (e.g., 'AI Agents', 'Quantum Computing')"] = "AI News",
    max_articles: Annotated[int, "Maximum number of articles to efficiently process"] = 5,
) -> str:
    """
    Run the Tech News Reporter agent to research and generate a report on a specific topic.
    Returns the report content or error message.
    """
    agent = get_or_create_agent()
    
    # Prepare context
    context = {
        "topic": topic,
        "max_articles": max_articles
    }
    
    logger.info(f"Running agent via MCP tool with context: {context}")
    
    try:
        # Run agent
        result = await agent.run(context)
        
        if result.success:
            output = result.output
            # Return the report text if available, or full output
            return output.get("report_content", json.dumps(output, default=str))
        else:
            return f"Agent failed: {result.error}"
            
    except Exception as e:
        logger.error(f"Error running agent: {e}", exc_info=True)
        return f"Internal error running agent: {str(e)}"

@mcp.custom_route("/run", methods=["POST"])
async def run_endpoint(request: Request) -> JSONResponse:
    """
    HTTP Endpoint to trigger the agent.
    
    Body:
    {
        "topic": "string",
        "max_articles": 5
    }
    """
    try:
        body = await request.json()
    except Exception:
        body = {}
        
    topic = body.get("topic", "AI News")
    max_articles = body.get("max_articles", 5)
    
    agent = get_or_create_agent()
    context = {
        "topic": topic,
        "max_articles": max_articles
    }
    
    logger.info(f"Running agent via /run endpoint with context: {context}")
    
    try:
        result = await agent.run(context)
        
        response_data = {
            "success": result.success,
            "output": result.output,
            "error": result.error,
            "steps_executed": result.steps_executed
        }
        
        return JSONResponse(response_data, status_code=200 if result.success else 500)
        
    except Exception as e:
        logger.error(f"Error running agent endpoint: {e}", exc_info=True)
        return JSONResponse(
            {"success": False, "error": str(e)}, 
            status_code=500
        )

if __name__ == "__main__":
    import uvicorn
    import argparse
    
    parser = argparse.ArgumentParser(description="Serve Tech News Reporter via FastMCP")
    parser.add_argument("--port", type=int, default=8000, help="Port to listen on")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host to bind to")
    
    args = parser.parse_args()
    
    print(f"Starting Tech News Reporter MCP Server on http://{args.host}:{args.port}")
    print(f"MCP Tool available: run_tech_news_reporter")
    print(f"HTTP Endpoint available: POST /run")
    
    mcp.run(transport="http", host=args.host, port=args.port)
