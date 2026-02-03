"""
Memory Manager - Dual-Mode Persistent Memory for Agents

Automatically selects backend:
- ChromaDB: If CHROMA_DB_PATH is set
- JSON + Cosine: Default fallback (zero infrastructure)

Usage:
    from memory import MemoryManager
    
    memory = MemoryManager()
    memory.save_learning("HubSpot 403 means scope missing", tags=["hubspot", "auth"])
    results = memory.search("permission error")
"""

import json
import os
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any

# Default data directory
DATA_DIR = Path(__file__).parent.parent.parent / "data"


class MemoryDriver(ABC):
    """Abstract base class for memory storage backends."""
    
    @abstractmethod
    def add(self, text: str, metadata: dict) -> str:
        """Add a memory entry. Returns the entry ID."""
        pass
    
    @abstractmethod
    def search(self, query: str, n_results: int = 5) -> list[dict]:
        """Search for relevant memories. Returns list of {text, metadata, score}."""
        pass
    
    @abstractmethod
    def delete(self, entry_id: str) -> bool:
        """Delete a memory entry by ID."""
        pass


class JSONMemoryDriver(MemoryDriver):
    """
    Portable JSON-based memory with cosine similarity search.
    Uses sentence-transformers for embeddings (lazy-loaded).
    """
    
    def __init__(self, file_path: Path | None = None):
        self.file_path = file_path or DATA_DIR / "memory.json"
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self._model = None
        self._data = self._load()
    
    def _load(self) -> dict:
        if self.file_path.exists():
            with open(self.file_path) as f:
                return json.load(f)
        return {"entries": [], "embeddings": []}
    
    def _save(self):
        with open(self.file_path, "w") as f:
            json.dump(self._data, f, indent=2, default=str)
    
    def _get_model(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer("all-MiniLM-L6-v2")
            except ImportError:
                raise ImportError(
                    "sentence-transformers required for JSON memory backend. "
                    "Install with: pip install sentence-transformers"
                )
        return self._model
    
    def _embed(self, text: str) -> list[float]:
        model = self._get_model()
        return model.encode(text).tolist()
    
    def _cosine_similarity(self, a: list[float], b: list[float]) -> float:
        import numpy as np
        a, b = np.array(a), np.array(b)
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-10))
    
    def add(self, text: str, metadata: dict) -> str:
        entry_id = f"mem_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{len(self._data['entries'])}"
        embedding = self._embed(text)
        
        self._data["entries"].append({
            "id": entry_id,
            "text": text,
            "metadata": metadata,
            "created_at": datetime.now().isoformat(),
        })
        self._data["embeddings"].append(embedding)
        self._save()
        return entry_id
    
    def search(self, query: str, n_results: int = 5) -> list[dict]:
        if not self._data["entries"]:
            return []
        
        query_embedding = self._embed(query)
        scores = [
            self._cosine_similarity(query_embedding, emb)
            for emb in self._data["embeddings"]
        ]
        
        # Sort by score descending
        indexed_scores = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
        
        results = []
        for idx, score in indexed_scores[:n_results]:
            entry = self._data["entries"][idx]
            results.append({
                "text": entry["text"],
                "metadata": entry["metadata"],
                "score": score,
                "id": entry["id"],
            })
        return results
    
    def delete(self, entry_id: str) -> bool:
        for i, entry in enumerate(self._data["entries"]):
            if entry["id"] == entry_id:
                self._data["entries"].pop(i)
                self._data["embeddings"].pop(i)
                self._save()
                return True
        return False


class ChromaMemoryDriver(MemoryDriver):
    """
    ChromaDB-based memory with vector search.
    Requires: pip install chromadb
    """
    
    def __init__(self, persist_directory: str | None = None):
        try:
            import chromadb
        except ImportError:
            raise ImportError(
                "chromadb required for Chroma memory backend. "
                "Install with: pip install chromadb"
            )
        
        persist_dir = persist_directory or str(DATA_DIR / "chroma_db")
        self._client = chromadb.PersistentClient(path=persist_dir)
        self._collection = self._client.get_or_create_collection(
            name="agent_memory",
            metadata={"hnsw:space": "cosine"}
        )
    
    def add(self, text: str, metadata: dict) -> str:
        entry_id = f"mem_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{self._collection.count()}"
        self._collection.add(
            documents=[text],
            metadatas=[metadata],
            ids=[entry_id]
        )
        return entry_id
    
    def search(self, query: str, n_results: int = 5) -> list[dict]:
        results = self._collection.query(
            query_texts=[query],
            n_results=n_results
        )
        
        output = []
        if results["documents"] and results["documents"][0]:
            for i, doc in enumerate(results["documents"][0]):
                output.append({
                    "text": doc,
                    "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                    "score": 1 - (results["distances"][0][i] if results["distances"] else 0),
                    "id": results["ids"][0][i] if results["ids"] else "",
                })
        return output
    
    def delete(self, entry_id: str) -> bool:
        try:
            self._collection.delete(ids=[entry_id])
            return True
        except Exception:
            return False


class MemoryManager:
    """
    High-level memory interface for agents.
    
    Automatically selects backend based on environment:
    - CHROMA_DB_PATH set -> ChromaDB
    - Otherwise -> JSON fallback
    """
    
    def __init__(self, force_backend: str | None = None):
        """
        Initialize memory manager.
        
        Args:
            force_backend: Force specific backend ("json" or "chroma")
        """
        self._state_file = DATA_DIR / "agent_state.json"
        self._state_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Select backend
        if force_backend == "json":
            self._driver = JSONMemoryDriver()
            self._backend = "json"
        elif force_backend == "chroma" or os.getenv("CHROMA_DB_PATH"):
            try:
                self._driver = ChromaMemoryDriver(os.getenv("CHROMA_DB_PATH"))
                self._backend = "chroma"
            except ImportError:
                print("⚠️  ChromaDB not installed, falling back to JSON")
                self._driver = JSONMemoryDriver()
                self._backend = "json"
        else:
            try:
                self._driver = JSONMemoryDriver()
                self._backend = "json"
            except ImportError:
                raise ImportError("No memory backend available. Install sentence-transformers.")
        
        print(f"🧠 Memory initialized ({self._backend} backend)")
    
    # =========================================================================
    # Learnings API (Long-Term Memory)
    # =========================================================================
    
    def save_learning(self, content: str, tags: list[str] | None = None) -> str:
        """
        Save a learning/fix for future retrieval.
        
        Args:
            content: The learning text
            tags: Optional list of tags for categorization
            
        Returns:
            Entry ID
        """
        metadata = {
            "type": "learning",
            "tags": tags or [],
        }
        entry_id = self._driver.add(content, metadata)
        print(f"🧠 Saved learning: {content[:50]}...")
        return entry_id
    
    def search_memory(self, query: str, n_results: int = 5) -> list[dict]:
        """
        Search for relevant memories.
        
        Args:
            query: Search query
            n_results: Max results to return
            
        Returns:
            List of {text, metadata, score}
        """
        results = self._driver.search(query, n_results)
        return results
    
    # =========================================================================
    # State API (Short-Term / Workflow State)
    # =========================================================================
    
    def update_state(self, key: str, value: Any) -> None:
        """Save a key-value to persistent state."""
        state = self._load_state()
        state[key] = value
        state["_updated_at"] = datetime.now().isoformat()
        self._save_state(state)
    
    def get_state(self, key: str | None = None) -> Any:
        """Get a value from state, or entire state if no key."""
        state = self._load_state()
        if key is None:
            return state
        return state.get(key)
    
    def clear_state(self) -> None:
        """Clear all state (for workflow completion)."""
        self._save_state({})
    
    def _load_state(self) -> dict:
        if self._state_file.exists():
            with open(self._state_file) as f:
                return json.load(f)
        return {}
    
    def _save_state(self, state: dict) -> None:
        with open(self._state_file, "w") as f:
            json.dump(state, f, indent=2, default=str)


# Quick test
if __name__ == "__main__":
    m = MemoryManager()
    
    # Test learning
    m.save_learning("HubSpot 403 error means OAuth token expired", tags=["hubspot", "auth"])
    m.save_learning("Slack channel names must be lowercase", tags=["slack"])
    
    # Test search
    results = m.search_memory("permission error hubspot")
    print("\n🔍 Search results:")
    for r in results:
        print(f"  - [{r['score']:.2f}] {r['text']}")
    
    # Test state
    m.update_state("current_workflow", "sync_contacts")
    m.update_state("step", 3)
    print(f"\n📊 State: {m.get_state()}")
