"""HTTP Endpoint for GitFlexi Agent (FastMCP)."""

import os
import json
import logging
from typing import Annotated

from fastmcp import FastMCP, Context
from starlette.requests import Request
from starlette.responses import JSONResponse

from .agent import default_agent, GitFlexiAgent

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("git-flexi-server")

# Initialize FastMCP
mcp = FastMCP("git-flexi-agent")


def get_agent() -> GitFlexiAgent:
    """Get or create agent instance."""
    return default_agent


@mcp.tool()
async def run_git_flexi_agent(
    force_run: Annotated[bool, "Force run even if recently ran"] = True
) -> str:
    """
    Trigger the GitFlexi Agent to check for new issues and create a digest.
    Returns the execution summary.
    """
    agent = get_agent()
    logger.info(f"Running agent via MCP tool (force_run={force_run})")
    try:
        result = await agent.run({"force_run": force_run})
        if result.success:
            # Check what the output keys were
            # The agent doesn't return a single string, result.output is a dict
            output = result.output
            if output.get("digest_sent"):
                return "Run successful. Digest email sent."
            else:
                return "Run successful. No new important issues found."
        else:
            return f"Agent failed: {result.error}"
    except Exception as e:
        logger.error(f"Error running agent: {e}", exc_info=True)
        return f"Internal error: {str(e)}"


@mcp.custom_route("/run", methods=["POST"])
async def run_endpoint(request: Request) -> JSONResponse:
    """
    HTTP Endpoint to trigger the agent.
    POST /run
    """
    agent = get_agent()
    try:
        body = await request.json()
    except:
        body = {}
        
    logger.info(f"Received HTTP trigger with body: {body}")
    
    try:
        result = await agent.run(body)
        response_data = {
            "success": result.success,
            "output": result.output,
            "error": result.error,
            "steps_executed": result.steps_executed
        }
        status_code = 200 if result.success else 500
        return JSONResponse(response_data, status_code=status_code)
        
    except Exception as e:
        logger.error(f"Error in HTTP endpoint: {e}", exc_info=True)
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Run GitFlexi Agent Server")
    parser.add_argument("--port", type=int, default=8000, help="Port to run on")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host to run on")
    parser.add_argument("--transport", type=str, choices=["stdio", "http"], default="http", help="Transport mode")
    
    args = parser.parse_args()
    
    if args.transport == "stdio":
        mcp.run(transport="stdio")
    else:
        logger.info(f"Starting HTTP server on {args.host}:{args.port}")
        mcp.run(transport="http", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
