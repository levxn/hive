# ChromaDB Tool

Vector database tool for semantic search and RAG (Retrieval-Augmented Generation) workflows using ChromaDB.

## Description

Provides collection management and document operations against a ChromaDB instance.
Supports four connection modes auto-detected from environment variables — no credentials
are required for local use.

## Connection Modes

| Priority | Mode | Required env vars |
|---|---|---|
| 1 | **Chroma Cloud** | `CHROMA_API_KEY` + `CHROMA_TENANT` + `CHROMA_DATABASE` |
| 2 | **Self-hosted server** | `CHROMA_HOST` (+ optional `CHROMA_SERVER_AUTHN_CREDENTIALS`) |
| 3 | **Local persistent** | `CHROMA_PERSIST_PATH` |
| 4 | **In-memory (default)** | *(none — ephemeral fallback)* |

## Environment Variables

| Variable | Description | Default |
|---|---|---|
| `CHROMA_API_KEY` | Chroma Cloud API key | — |
| `CHROMA_TENANT` | Chroma Cloud tenant ID | — |
| `CHROMA_DATABASE` | Chroma Cloud database name | — |
| `CHROMA_HOST` | Self-hosted server hostname | — |
| `CHROMA_PORT` | Self-hosted server port | `8000` |
| `CHROMA_SSL` | Use HTTPS for server connection (`1` or `true`) | `false` |
| `CHROMA_SERVER_AUTHN_CREDENTIALS` | Token for server auth | — |
| `CHROMA_PERSIST_PATH` | Directory path for local persistent storage | — |

## Available Tools

### Collection Management

| Tool | Description |
|---|---|
| `chroma_list_collections` | List all collections |
| `chroma_create_collection` | Create a new collection |
| `chroma_get_or_create_collection` | Get existing or create new collection |
| `chroma_delete_collection` | Delete a collection and all its documents |
| `chroma_collection_count` | Count documents in a collection |

### Document Operations

| Tool | Description |
|---|---|
| `chroma_add_documents` | Add documents (text and/or embeddings) to a collection |
| `chroma_query` | Query by embedding vectors, returns nearest neighbours |
| `chroma_get_documents` | Retrieve documents by IDs or metadata/content filters |
| `chroma_update_documents` | Update existing documents |
| `chroma_delete_documents` | Delete documents by IDs or filters |

## Argument Reference

### `chroma_create_collection`

| Argument | Type | Required | Default | Description |
|---|---|---|---|---|
| `name` | str | Yes | — | Collection name |
| `distance` | str | No | `cosine` | Distance metric: `cosine`, `l2`, or `ip` |

### `chroma_add_documents`

| Argument | Type | Required | Default | Description |
|---|---|---|---|---|
| `collection_name` | str | Yes | — | Target collection |
| `ids` | list[str] | Yes | — | Unique IDs, one per document |
| `documents` | list[str] | No | — | Text content (required if embeddings not provided) |
| `embeddings` | list[list[float]] | No | — | Pre-computed vectors (required if documents not provided) |
| `metadatas` | list[dict] | No | — | Metadata dicts, one per document |

### `chroma_query`

| Argument | Type | Required | Default | Description |
|---|---|---|---|---|
| `collection_name` | str | Yes | — | Collection to query |
| `query_embeddings` | list[list[float]] | Yes | — | Query vectors |
| `n_results` | int | No | `10` | Number of nearest neighbours per query |
| `where` | dict | No | — | Metadata filter, e.g. `{"topic": {"$eq": "AI"}}` |
| `where_document` | dict | No | — | Document content filter, e.g. `{"$contains": "term"}` |
| `include` | list[str] | No | `["documents","metadatas","distances"]` | Fields to include |

### `chroma_get_documents`

| Argument | Type | Required | Default | Description |
|---|---|---|---|---|
| `collection_name` | str | Yes | — | Collection to read from |
| `ids` | list[str] | No | — | Specific IDs to fetch |
| `where` | dict | No | — | Metadata filter |
| `where_document` | dict | No | — | Document content filter |
| `include` | list[str] | No | `["documents","metadatas"]` | Fields to include |
| `limit` | int | No | — | Max results |
| `offset` | int | No | — | Skip N results (pagination) |

### `chroma_delete_documents`

| Argument | Type | Required | Default | Description |
|---|---|---|---|---|
| `collection_name` | str | Yes | — | Collection to delete from |
| `ids` | list[str] | No | — | IDs to delete |
| `where` | dict | No | — | Metadata filter for bulk delete |
| `where_document` | dict | No | — | Document content filter |

At least one of `ids`, `where`, or `where_document` is required.

## Installation

ChromaDB is an optional dependency:

```bash
uv pip install 'tools[chroma]'
```

## Error Handling

All tools return `{"error": "<message>"}` for:
- Missing required parameters
- Invalid parameter values (e.g. unknown distance metric)
- `chromadb` package not installed
- Client connection failures
- Collection not found
