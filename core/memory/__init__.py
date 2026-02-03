"""
Memory Manager Module

Provides persistent memory for agents with dual-mode storage:
- ChromaDB: Robust vector search (if configured)
- JSON + Cosine: Lightweight portable fallback (default)
"""

from .memory_manager import MemoryManager

__all__ = ["MemoryManager"]
