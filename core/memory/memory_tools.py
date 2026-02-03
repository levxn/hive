"""
Memory Tools for MCP/FastMCP

Provides agent-callable tools for memory management:
- save_learning: Record important facts/fixes
- search_memory: Retrieve relevant learnings
- update_state: Save workflow progress
- get_state: Retrieve workflow state
"""

from typing import Any

from fastmcp import FastMCP

from .memory_manager import MemoryManager

# Global memory instance (initialized on first use)
_memory: MemoryManager | None = None


def _get_memory() -> MemoryManager:
    global _memory
    if _memory is None:
        _memory = MemoryManager()
    return _memory


def register_memory_tools(mcp: FastMCP) -> None:
    """Register memory tools with the MCP server."""
    
    @mcp.tool()
    def memory_save_learning(
        content: str,
        tags: str = "",
    ) -> dict:
        """
        Save an important learning or fix for future retrieval.
        
        Use this to record:
        - Error patterns and their fixes
        - Business rules or gotchas
        - User preferences and corrections
        
        Args:
            content: The learning text to save
            tags: Comma-separated tags (e.g., "hubspot,auth,error")
            
        Returns:
            Dict with entry ID
        """
        memory = _get_memory()
        tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
        entry_id = memory.save_learning(content, tags=tag_list)
        return {"success": True, "entry_id": entry_id}
    
    @mcp.tool()
    def memory_search(
        query: str,
        limit: int = 5,
    ) -> dict:
        """
        Search for relevant learnings and past experiences.
        
        Always search before attempting risky operations to check
        for known gotchas or proven solutions.
        
        Args:
            query: Search query (natural language)
            limit: Max results to return
            
        Returns:
            Dict with list of relevant memories
        """
        memory = _get_memory()
        results = memory.search_memory(query, n_results=limit)
        return {
            "count": len(results),
            "memories": [
                {"text": r["text"], "tags": r["metadata"].get("tags", []), "score": round(r["score"], 3)}
                for r in results
            ]
        }
    
    @mcp.tool()
    def memory_update_state(
        key: str,
        value: str,
    ) -> dict:
        """
        Save workflow state for crash recovery.
        
        Use this to checkpoint progress in multi-step workflows
        so you can resume if interrupted.
        
        Args:
            key: State key (e.g., "current_step", "contact_id")
            value: Value to save (will be stored as string)
            
        Returns:
            Dict with success status
        """
        memory = _get_memory()
        memory.update_state(key, value)
        return {"success": True, "key": key}
    
    @mcp.tool()
    def memory_get_state(
        key: str = "",
    ) -> dict:
        """
        Retrieve workflow state.
        
        Check this at startup to see if resuming a previous workflow.
        
        Args:
            key: State key to retrieve, or empty for all state
            
        Returns:
            Dict with state value(s)
        """
        memory = _get_memory()
        if key:
            value = memory.get_state(key)
            return {"key": key, "value": value}
        else:
            return {"state": memory.get_state()}
    
    @mcp.tool()
    def memory_clear_state() -> dict:
        """
        Clear all workflow state.
        
        Call this when a workflow completes successfully.
        
        Returns:
            Dict with success status
        """
        memory = _get_memory()
        memory.clear_state()
        return {"success": True, "message": "State cleared"}
