"""
ChromaDB Tool - Vector database for semantic search and RAG workflows.

Supports three connection modes (auto-detected from environment variables):
  1. Chroma Cloud   — CHROMA_API_KEY + CHROMA_TENANT + CHROMA_DATABASE
  2. HTTP server    — CHROMA_HOST (+ optional CHROMA_SERVER_AUTHN_CREDENTIALS)
  3. Local persist  — CHROMA_PERSIST_PATH

At least one mode must be configured. No in-memory fallback is provided so that
agents always operate against a durable store.

Docs: https://docs.trychroma.com/
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from aden_tools.credentials import CredentialStoreAdapter


class _ChromaNotConfigured(Exception):
    """Raised when no ChromaDB connection mode is configured."""


def _get_api_key(credentials: CredentialStoreAdapter | None) -> str | None:
    if credentials is not None:
        try:
            return credentials.get("chroma_api_key")
        except Exception:
            pass
    return os.getenv("CHROMA_API_KEY")


def _get_token(credentials: CredentialStoreAdapter | None) -> str | None:
    if credentials is not None:
        try:
            return credentials.get("chroma_token")
        except Exception:
            pass
    return os.getenv("CHROMA_SERVER_AUTHN_CREDENTIALS")


def _get_client(credentials: CredentialStoreAdapter | None) -> Any:
    """
    Build and return a ChromaDB client based on available environment variables.

    Priority:
      1. Cloud   — CHROMA_API_KEY + CHROMA_TENANT + CHROMA_DATABASE
      2. HTTP    — CHROMA_HOST (with optional token auth)
      3. Persist — CHROMA_PERSIST_PATH

    Raises:
        ImportError: if chromadb is not installed.
        _ChromaNotConfigured: if no connection mode is configured.
    """
    try:
        import chromadb
    except ImportError as exc:
        raise ImportError(
            "chromadb package is not installed. "
            "Run: uv pip install 'tools[chroma]'"
        ) from exc

    # 1. Chroma Cloud
    api_key = _get_api_key(credentials)
    tenant = os.getenv("CHROMA_TENANT")
    database = os.getenv("CHROMA_DATABASE")
    if api_key and tenant and database:
        return chromadb.CloudClient(tenant=tenant, database=database, api_key=api_key)

    # 2. Self-hosted HTTP server
    host = os.getenv("CHROMA_HOST")
    if host:
        port = int(os.getenv("CHROMA_PORT", "8000"))
        ssl = os.getenv("CHROMA_SSL", "").lower() in ("1", "true")
        token = _get_token(credentials)
        if token:
            settings = chromadb.config.Settings(
                chroma_client_auth_provider="chromadb.auth.token.TokenAuthClientProvider",
                chroma_client_auth_credentials=token,
            )
            return chromadb.HttpClient(host=host, port=port, ssl=ssl, settings=settings)
        return chromadb.HttpClient(host=host, port=port, ssl=ssl)

    # 3. Local persistent
    path = os.getenv("CHROMA_PERSIST_PATH")
    if path:
        return chromadb.PersistentClient(path=path)

    raise _ChromaNotConfigured(
        "No ChromaDB connection mode configured. "
        "Set CHROMA_API_KEY+CHROMA_TENANT+CHROMA_DATABASE (Cloud), "
        "CHROMA_HOST (HTTP server), or CHROMA_PERSIST_PATH (local)."
    )


def _import_error_response(exc: ImportError) -> dict[str, Any]:
    return {
        "error": str(exc),
        "help": "Install the optional dependency: uv pip install 'tools[chroma]'",
    }


def _not_configured_response() -> dict[str, Any]:
    return {
        "error": "ChromaDB is not configured.",
        "help": (
            "Choose a connection mode:\n"
            "  Cloud:  CHROMA_API_KEY + CHROMA_TENANT + CHROMA_DATABASE\n"
            "  Server: CHROMA_HOST (+ optional CHROMA_SERVER_AUTHN_CREDENTIALS)\n"
            "  Local:  CHROMA_PERSIST_PATH=/path/to/storage\n"
            "Docs: https://docs.trychroma.com/deployment"
        ),
    }


def register_tools(mcp: Any, credentials: CredentialStoreAdapter | None = None) -> None:
    """Register ChromaDB tools with the MCP server."""

    # ── Collection Management ──

    @mcp.tool()
    def chroma_list_collections() -> dict[str, Any]:
        """
        List all collections in the ChromaDB instance.

        Connection is auto-configured from environment variables:
          - Cloud:   CHROMA_API_KEY + CHROMA_TENANT + CHROMA_DATABASE
          - Server:  CHROMA_HOST (+ optional CHROMA_SERVER_AUTHN_CREDENTIALS)
          - Local:   CHROMA_PERSIST_PATH

        Returns:
            Dict with collections list (name, metadata) and count.
        """
        try:
            client = _get_client(credentials)
        except ImportError as exc:
            return _import_error_response(exc)
        except _ChromaNotConfigured:
            return _not_configured_response()
        try:
            cols = client.list_collections()
            return {
                "collections": [
                    {"name": c.name, "metadata": c.metadata or {}} for c in cols
                ],
                "count": len(cols),
            }
        except Exception as exc:
            return {"error": f"ChromaDB error: {exc!s}"}

    @mcp.tool()
    def chroma_create_collection(
        name: str,
        distance: str = "cosine",
    ) -> dict[str, Any]:
        """
        Create a new ChromaDB collection.

        Args:
            name: Collection name.
            distance: Distance metric — cosine, l2, or ip (inner product). Default cosine.

        Returns:
            Dict with collection name and metadata.
        """
        if not name:
            return {"error": "name is required"}
        if distance not in ("cosine", "l2", "ip"):
            return {"error": "distance must be one of: cosine, l2, ip"}
        try:
            client = _get_client(credentials)
        except ImportError as exc:
            return _import_error_response(exc)
        except _ChromaNotConfigured:
            return _not_configured_response()
        try:
            col = client.create_collection(
                name=name,
                metadata={"hnsw:space": distance},
            )
            return {"name": col.name, "metadata": col.metadata or {}, "status": "created"}
        except Exception as exc:
            return {"error": f"ChromaDB error: {exc!s}"}

    @mcp.tool()
    def chroma_get_or_create_collection(
        name: str,
        distance: str = "cosine",
    ) -> dict[str, Any]:
        """
        Get an existing collection or create it if it does not exist.

        Args:
            name: Collection name.
            distance: Distance metric used only when creating — cosine, l2, or ip. Default cosine.

        Returns:
            Dict with collection name, metadata, and whether it was just created.
        """
        if not name:
            return {"error": "name is required"}
        if distance not in ("cosine", "l2", "ip"):
            return {"error": "distance must be one of: cosine, l2, ip"}
        try:
            client = _get_client(credentials)
        except ImportError as exc:
            return _import_error_response(exc)
        except _ChromaNotConfigured:
            return _not_configured_response()
        try:
            col = client.get_or_create_collection(
                name=name,
                metadata={"hnsw:space": distance},
            )
            return {"name": col.name, "metadata": col.metadata or {}}
        except Exception as exc:
            return {"error": f"ChromaDB error: {exc!s}"}

    @mcp.tool()
    def chroma_delete_collection(collection_name: str) -> dict[str, Any]:
        """
        Delete a ChromaDB collection and all its documents. This is irreversible.

        Args:
            collection_name: Name of the collection to delete.

        Returns:
            Dict with deletion status.
        """
        if not collection_name:
            return {"error": "collection_name is required"}
        try:
            client = _get_client(credentials)
        except ImportError as exc:
            return _import_error_response(exc)
        except _ChromaNotConfigured:
            return _not_configured_response()
        try:
            client.delete_collection(name=collection_name)
            return {"collection_name": collection_name, "status": "deleted"}
        except Exception as exc:
            return {"error": f"ChromaDB error: {exc!s}"}

    @mcp.tool()
    def chroma_collection_count(collection_name: str) -> dict[str, Any]:
        """
        Return the number of documents in a collection.

        Args:
            collection_name: Name of the collection.

        Returns:
            Dict with collection name and document count.
        """
        if not collection_name:
            return {"error": "collection_name is required"}
        try:
            client = _get_client(credentials)
        except ImportError as exc:
            return _import_error_response(exc)
        except _ChromaNotConfigured:
            return _not_configured_response()
        try:
            col = client.get_collection(name=collection_name)
            return {"collection_name": collection_name, "count": col.count()}
        except Exception as exc:
            return {"error": f"ChromaDB error: {exc!s}"}

    # ── Document Operations ──

    @mcp.tool()
    def chroma_add_documents(
        collection_name: str,
        ids: list[str],
        documents: list[str] | None = None,
        embeddings: list[list[float]] | None = None,
        metadatas: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """
        Add documents (and optionally embeddings) to a collection.

        At least one of documents or embeddings must be provided.
        If only documents are provided, Chroma uses its default embedding function.
        If only embeddings are provided, documents are stored as empty strings.

        Args:
            collection_name: Target collection name.
            ids: Unique string IDs for each document. Must match length of documents/embeddings.
            documents: List of text strings to store (optional if embeddings provided).
            embeddings: Pre-computed embedding vectors (optional if documents provided).
            metadatas: List of metadata dicts, one per document (optional).

        Returns:
            Dict with added count and status.
        """
        if not collection_name:
            return {"error": "collection_name is required"}
        if not ids:
            return {"error": "ids is required and must be non-empty"}
        # Credentials check before content validation so credential errors are surfaced first.
        try:
            client = _get_client(credentials)
        except ImportError as exc:
            return _import_error_response(exc)
        except _ChromaNotConfigured:
            return _not_configured_response()
        if not documents and not embeddings:
            return {"error": "At least one of documents or embeddings must be provided"}
        if documents and len(documents) != len(ids):
            return {"error": "documents and ids must have the same length"}
        if embeddings and len(embeddings) != len(ids):
            return {"error": "embeddings and ids must have the same length"}
        if metadatas and len(metadatas) != len(ids):
            return {"error": "metadatas and ids must have the same length"}
        try:
            col = client.get_collection(name=collection_name)
            kwargs: dict[str, Any] = {"ids": ids}
            if documents:
                kwargs["documents"] = documents
            if embeddings:
                kwargs["embeddings"] = embeddings
            if metadatas:
                kwargs["metadatas"] = metadatas
            col.add(**kwargs)
            return {"collection_name": collection_name, "added_count": len(ids), "status": "added"}
        except Exception as exc:
            return {"error": f"ChromaDB error: {exc!s}"}

    @mcp.tool()
    def chroma_query(
        collection_name: str,
        query_embeddings: list[list[float]],
        n_results: int = 10,
        where: dict[str, Any] | None = None,
        where_document: dict[str, Any] | None = None,
        include: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Query a ChromaDB collection by embedding vectors.

        Args:
            collection_name: Collection to query.
            query_embeddings: List of query vectors (one result set returned per vector).
            n_results: Number of nearest neighbours to return per query. Default 10.
            where: Metadata filter using Chroma's operator syntax,
                   e.g. {"topic": {"$eq": "AI"}} or {"$and": [{"a": {"$eq": 1}}, {"b": {"$gt": 2}}]}.
            where_document: Document content filter, e.g. {"$contains": "search term"}.
            include: Fields to include in results. Any combination of:
                     ["documents", "embeddings", "metadatas", "distances"].
                     Default: ["documents", "metadatas", "distances"].

        Returns:
            Dict with ids, distances, documents, metadatas per query vector.
        """
        if not collection_name:
            return {"error": "collection_name is required"}
        if not query_embeddings:
            return {"error": "query_embeddings is required and must be non-empty"}
        if n_results < 1:
            return {"error": "n_results must be at least 1"}

        effective_include = include or ["documents", "metadatas", "distances"]
        try:
            client = _get_client(credentials)
        except ImportError as exc:
            return _import_error_response(exc)
        except _ChromaNotConfigured:
            return _not_configured_response()
        try:
            col = client.get_collection(name=collection_name)
            kwargs: dict[str, Any] = {
                "query_embeddings": query_embeddings,
                "n_results": n_results,
                "include": effective_include,
            }
            if where:
                kwargs["where"] = where
            if where_document:
                kwargs["where_document"] = where_document
            results = col.query(**kwargs)
            return {
                "ids": results.get("ids", []),
                "distances": results.get("distances", []),
                "documents": results.get("documents", []),
                "metadatas": results.get("metadatas", []),
                "n_queries": len(query_embeddings),
            }
        except Exception as exc:
            return {"error": f"ChromaDB error: {exc!s}"}

    @mcp.tool()
    def chroma_get_documents(
        collection_name: str,
        ids: list[str] | None = None,
        where: dict[str, Any] | None = None,
        where_document: dict[str, Any] | None = None,
        include: list[str] | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> dict[str, Any]:
        """
        Retrieve documents from a collection by IDs or metadata/content filters.

        At least one of ids, where, or where_document must be provided.

        Args:
            collection_name: Collection to read from.
            ids: Specific document IDs to fetch (optional).
            where: Metadata filter (optional), e.g. {"topic": {"$eq": "AI"}}.
            where_document: Document content filter (optional), e.g. {"$contains": "term"}.
            include: Fields to include — any of ["documents", "embeddings", "metadatas"].
                     Default: ["documents", "metadatas"].
            limit: Maximum number of results to return (optional).
            offset: Number of results to skip for pagination (optional).

        Returns:
            Dict with ids, documents, and metadatas for matching records.
        """
        if not collection_name:
            return {"error": "collection_name is required"}
        # Credentials check before content validation so credential errors are surfaced first.
        effective_include = include or ["documents", "metadatas"]
        try:
            client = _get_client(credentials)
        except ImportError as exc:
            return _import_error_response(exc)
        except _ChromaNotConfigured:
            return _not_configured_response()
        if not ids and not where and not where_document:
            return {"error": "At least one of ids, where, or where_document must be provided"}
        try:
            col = client.get_collection(name=collection_name)
            kwargs: dict[str, Any] = {"include": effective_include}
            if ids:
                kwargs["ids"] = ids
            if where:
                kwargs["where"] = where
            if where_document:
                kwargs["where_document"] = where_document
            if limit is not None:
                kwargs["limit"] = limit
            if offset is not None:
                kwargs["offset"] = offset
            results = col.get(**kwargs)
            return {
                "ids": results.get("ids", []),
                "documents": results.get("documents", []),
                "metadatas": results.get("metadatas", []),
                "count": len(results.get("ids", [])),
            }
        except Exception as exc:
            return {"error": f"ChromaDB error: {exc!s}"}

    @mcp.tool()
    def chroma_update_documents(
        collection_name: str,
        ids: list[str],
        documents: list[str] | None = None,
        embeddings: list[list[float]] | None = None,
        metadatas: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """
        Update existing documents in a collection. Only provided fields are updated.

        At least one of documents, embeddings, or metadatas must be provided.
        IDs that do not exist in the collection are ignored.

        Args:
            collection_name: Collection to update.
            ids: IDs of documents to update. Required.
            documents: New text content for each document (optional).
            embeddings: New embedding vectors (optional).
            metadatas: New metadata dicts (optional).

        Returns:
            Dict with updated count and status.
        """
        if not collection_name:
            return {"error": "collection_name is required"}
        if not ids:
            return {"error": "ids is required and must be non-empty"}
        # Credentials check before content validation so credential errors are surfaced first.
        try:
            client = _get_client(credentials)
        except ImportError as exc:
            return _import_error_response(exc)
        except _ChromaNotConfigured:
            return _not_configured_response()
        if not documents and not embeddings and not metadatas:
            return {"error": "At least one of documents, embeddings, or metadatas must be provided"}
        if documents and len(documents) != len(ids):
            return {"error": "documents and ids must have the same length"}
        if embeddings and len(embeddings) != len(ids):
            return {"error": "embeddings and ids must have the same length"}
        if metadatas and len(metadatas) != len(ids):
            return {"error": "metadatas and ids must have the same length"}
        try:
            col = client.get_collection(name=collection_name)
            kwargs: dict[str, Any] = {"ids": ids}
            if documents:
                kwargs["documents"] = documents
            if embeddings:
                kwargs["embeddings"] = embeddings
            if metadatas:
                kwargs["metadatas"] = metadatas
            col.update(**kwargs)
            return {"collection_name": collection_name, "updated_count": len(ids), "status": "updated"}
        except Exception as exc:
            return {"error": f"ChromaDB error: {exc!s}"}

    @mcp.tool()
    def chroma_delete_documents(
        collection_name: str,
        ids: list[str] | None = None,
        where: dict[str, Any] | None = None,
        where_document: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Delete documents from a collection by IDs or metadata/content filters.

        At least one of ids, where, or where_document must be provided.

        Args:
            collection_name: Collection to delete from.
            ids: Specific document IDs to delete (optional).
            where: Metadata filter to select documents for deletion (optional).
            where_document: Document content filter (optional).

        Returns:
            Dict with deletion status.
        """
        if not collection_name:
            return {"error": "collection_name is required"}
        # Credentials check before content validation so credential errors are surfaced first.
        try:
            client = _get_client(credentials)
        except ImportError as exc:
            return _import_error_response(exc)
        except _ChromaNotConfigured:
            return _not_configured_response()
        if not ids and not where and not where_document:
            return {"error": "At least one of ids, where, or where_document must be provided"}
        try:
            col = client.get_collection(name=collection_name)
            kwargs: dict[str, Any] = {}
            if ids:
                kwargs["ids"] = ids
            if where:
                kwargs["where"] = where
            if where_document:
                kwargs["where_document"] = where_document
            col.delete(**kwargs)
            return {"collection_name": collection_name, "status": "deleted"}
        except Exception as exc:
            return {"error": f"ChromaDB error: {exc!s}"}
