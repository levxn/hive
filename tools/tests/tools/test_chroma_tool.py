"""Tests for chroma_tool - ChromaDB vector database operations."""

from unittest.mock import MagicMock, patch

import pytest
from fastmcp import FastMCP

from aden_tools.tools.chroma_tool.chroma_tool import (
    _ChromaNotConfigured,
    _get_client,
    register_tools,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def tool_fns(mcp: FastMCP):
    register_tools(mcp, credentials=None)
    tools = mcp._tool_manager._tools
    return {name: tools[name].fn for name in tools}


@pytest.fixture
def mock_client():
    """A MagicMock standing in for a chromadb client."""
    return MagicMock()


# ── _get_client connection mode tests ─────────────────────────────────────────

def _make_chromadb_mock():
    """Build a fake chromadb module so TestGetClient tests work without the package installed."""
    import sys
    import types

    mock_chromadb = types.ModuleType("chromadb")
    mock_chromadb.CloudClient = MagicMock()
    mock_chromadb.HttpClient = MagicMock()
    mock_chromadb.PersistentClient = MagicMock()

    mock_config = types.ModuleType("chromadb.config")
    mock_config.Settings = MagicMock()
    mock_chromadb.config = mock_config
    sys.modules.setdefault("chromadb.config", mock_config)

    return mock_chromadb


class TestGetClient:
    def test_cloud_mode(self):
        env = {
            "CHROMA_API_KEY": "ck-test",
            "CHROMA_TENANT": "my-tenant",
            "CHROMA_DATABASE": "my-db",
        }
        mock_chroma = _make_chromadb_mock()
        with (
            patch.dict("os.environ", env, clear=True),
            patch.dict("sys.modules", {"chromadb": mock_chroma}),
        ):
            _get_client(None)
            mock_chroma.CloudClient.assert_called_once_with(
                tenant="my-tenant", database="my-db", api_key="ck-test"
            )

    def test_http_mode_no_auth(self):
        env = {"CHROMA_HOST": "myhost", "CHROMA_PORT": "9000"}
        mock_chroma = _make_chromadb_mock()
        with (
            patch.dict("os.environ", env, clear=True),
            patch.dict("sys.modules", {"chromadb": mock_chroma}),
        ):
            _get_client(None)
            mock_chroma.HttpClient.assert_called_once_with(host="myhost", port=9000, ssl=False)

    def test_http_mode_with_token(self):
        env = {
            "CHROMA_HOST": "myhost",
            "CHROMA_SERVER_AUTHN_CREDENTIALS": "tok-abc",
        }
        mock_chroma = _make_chromadb_mock()
        with (
            patch.dict("os.environ", env, clear=True),
            patch.dict("sys.modules", {"chromadb": mock_chroma}),
        ):
            _get_client(None)
            mock_chroma.config.Settings.assert_called_once()
            mock_chroma.HttpClient.assert_called_once()

    def test_persistent_mode(self):
        env = {"CHROMA_PERSIST_PATH": "/tmp/chroma"}
        mock_chroma = _make_chromadb_mock()
        with (
            patch.dict("os.environ", env, clear=True),
            patch.dict("sys.modules", {"chromadb": mock_chroma}),
        ):
            _get_client(None)
            mock_chroma.PersistentClient.assert_called_once_with(path="/tmp/chroma")

    def test_not_configured_raises(self):
        mock_chroma = _make_chromadb_mock()
        with (
            patch.dict("os.environ", {}, clear=True),
            patch.dict("sys.modules", {"chromadb": mock_chroma}),
        ):
            with pytest.raises(_ChromaNotConfigured):
                _get_client(None)

    def test_import_error(self):
        with patch.dict("os.environ", {}, clear=True):
            with patch.dict("sys.modules", {"chromadb": None}):
                with pytest.raises(ImportError, match="chromadb package is not installed"):
                    _get_client(None)


# ── chroma_list_collections ───────────────────────────────────────────────────

class TestChromaListCollections:
    def test_successful_list(self, tool_fns):
        col1 = MagicMock(name="col1", metadata={"hnsw:space": "cosine"})
        col1.name = "col1"
        col2 = MagicMock(name="col2", metadata=None)
        col2.name = "col2"
        mock_client = MagicMock()
        mock_client.list_collections.return_value = [col1, col2]
        with patch(
            "aden_tools.tools.chroma_tool.chroma_tool._get_client",
            return_value=mock_client,
        ):
            result = tool_fns["chroma_list_collections"]()
        assert result["count"] == 2
        assert result["collections"][0]["name"] == "col1"
        assert result["collections"][1]["metadata"] == {}

    def test_client_error(self, tool_fns):
        mock_client = MagicMock()
        mock_client.list_collections.side_effect = Exception("connection refused")
        with patch(
            "aden_tools.tools.chroma_tool.chroma_tool._get_client",
            return_value=mock_client,
        ):
            result = tool_fns["chroma_list_collections"]()
        assert "error" in result
        assert "connection refused" in result["error"]

    def test_import_error(self, tool_fns):
        with patch(
            "aden_tools.tools.chroma_tool.chroma_tool._get_client",
            side_effect=ImportError("chromadb package is not installed"),
        ):
            result = tool_fns["chroma_list_collections"]()
        assert "error" in result

    def test_not_configured_returns_error_and_help(self, tool_fns):
        with patch(
            "aden_tools.tools.chroma_tool.chroma_tool._get_client",
            side_effect=_ChromaNotConfigured("not configured"),
        ):
            result = tool_fns["chroma_list_collections"]()
        assert "error" in result
        assert "help" in result


# ── chroma_create_collection ──────────────────────────────────────────────────

class TestChromaCreateCollection:
    def test_missing_name(self, tool_fns):
        result = tool_fns["chroma_create_collection"](name="")
        assert "error" in result

    def test_invalid_distance(self, tool_fns):
        result = tool_fns["chroma_create_collection"](name="test", distance="bad")
        assert "error" in result

    def test_successful_create(self, tool_fns):
        col = MagicMock()
        col.name = "my-col"
        col.metadata = {"hnsw:space": "cosine"}
        mock_client = MagicMock()
        mock_client.create_collection.return_value = col
        with patch(
            "aden_tools.tools.chroma_tool.chroma_tool._get_client",
            return_value=mock_client,
        ):
            result = tool_fns["chroma_create_collection"](name="my-col", distance="cosine")
        assert result["status"] == "created"
        assert result["name"] == "my-col"
        mock_client.create_collection.assert_called_once_with(
            name="my-col", metadata={"hnsw:space": "cosine"}
        )

    def test_client_error(self, tool_fns):
        mock_client = MagicMock()
        mock_client.create_collection.side_effect = Exception("already exists")
        with patch(
            "aden_tools.tools.chroma_tool.chroma_tool._get_client",
            return_value=mock_client,
        ):
            result = tool_fns["chroma_create_collection"](name="dupe")
        assert "error" in result


# ── chroma_get_or_create_collection ──────────────────────────────────────────

class TestChromaGetOrCreateCollection:
    def test_missing_name(self, tool_fns):
        result = tool_fns["chroma_get_or_create_collection"](name="")
        assert "error" in result

    def test_successful(self, tool_fns):
        col = MagicMock()
        col.name = "my-col"
        col.metadata = {"hnsw:space": "l2"}
        mock_client = MagicMock()
        mock_client.get_or_create_collection.return_value = col
        with patch(
            "aden_tools.tools.chroma_tool.chroma_tool._get_client",
            return_value=mock_client,
        ):
            result = tool_fns["chroma_get_or_create_collection"](name="my-col", distance="l2")
        assert result["name"] == "my-col"


# ── chroma_delete_collection ──────────────────────────────────────────────────

class TestChromaDeleteCollection:
    def test_missing_name(self, tool_fns):
        result = tool_fns["chroma_delete_collection"](collection_name="")
        assert "error" in result

    def test_successful_delete(self, tool_fns):
        mock_client = MagicMock()
        with patch(
            "aden_tools.tools.chroma_tool.chroma_tool._get_client",
            return_value=mock_client,
        ):
            result = tool_fns["chroma_delete_collection"](collection_name="old-col")
        assert result["status"] == "deleted"
        assert result["collection_name"] == "old-col"

    def test_client_error(self, tool_fns):
        mock_client = MagicMock()
        mock_client.delete_collection.side_effect = Exception("not found")
        with patch(
            "aden_tools.tools.chroma_tool.chroma_tool._get_client",
            return_value=mock_client,
        ):
            result = tool_fns["chroma_delete_collection"](collection_name="ghost")
        assert "error" in result


# ── chroma_collection_count ───────────────────────────────────────────────────

class TestChromaCollectionCount:
    def test_missing_name(self, tool_fns):
        result = tool_fns["chroma_collection_count"](collection_name="")
        assert "error" in result

    def test_successful_count(self, tool_fns):
        col = MagicMock()
        col.count.return_value = 42
        mock_client = MagicMock()
        mock_client.get_collection.return_value = col
        with patch(
            "aden_tools.tools.chroma_tool.chroma_tool._get_client",
            return_value=mock_client,
        ):
            result = tool_fns["chroma_collection_count"](collection_name="my-col")
        assert result["count"] == 42
        assert result["collection_name"] == "my-col"


# ── chroma_add_documents ──────────────────────────────────────────────────────

class TestChromaAddDocuments:
    def test_missing_collection(self, tool_fns):
        result = tool_fns["chroma_add_documents"](
            collection_name="", ids=["1"], documents=["doc"]
        )
        assert "error" in result

    def test_missing_ids(self, tool_fns):
        result = tool_fns["chroma_add_documents"](
            collection_name="col", ids=[], documents=["doc"]
        )
        assert "error" in result

    def test_missing_documents_and_embeddings(self, tool_fns):
        result = tool_fns["chroma_add_documents"](
            collection_name="col", ids=["1"]
        )
        assert "error" in result

    def test_length_mismatch_documents(self, tool_fns):
        result = tool_fns["chroma_add_documents"](
            collection_name="col", ids=["1", "2"], documents=["only one"]
        )
        assert "error" in result

    def test_length_mismatch_embeddings(self, tool_fns):
        result = tool_fns["chroma_add_documents"](
            collection_name="col",
            ids=["1"],
            embeddings=[[0.1, 0.2], [0.3, 0.4]],
        )
        assert "error" in result

    def test_successful_add_with_documents(self, tool_fns):
        col = MagicMock()
        mock_client = MagicMock()
        mock_client.get_collection.return_value = col
        with patch(
            "aden_tools.tools.chroma_tool.chroma_tool._get_client",
            return_value=mock_client,
        ):
            result = tool_fns["chroma_add_documents"](
                collection_name="my-col",
                ids=["doc1", "doc2"],
                documents=["Hello world", "Foo bar"],
                metadatas=[{"topic": "test"}, {"topic": "test2"}],
            )
        assert result["status"] == "added"
        assert result["added_count"] == 2
        col.add.assert_called_once()

    def test_successful_add_with_embeddings(self, tool_fns):
        col = MagicMock()
        mock_client = MagicMock()
        mock_client.get_collection.return_value = col
        with patch(
            "aden_tools.tools.chroma_tool.chroma_tool._get_client",
            return_value=mock_client,
        ):
            result = tool_fns["chroma_add_documents"](
                collection_name="my-col",
                ids=["v1"],
                embeddings=[[0.1, 0.2, 0.3]],
            )
        assert result["added_count"] == 1


# ── chroma_query ──────────────────────────────────────────────────────────────

class TestChromaQuery:
    def test_missing_collection(self, tool_fns):
        result = tool_fns["chroma_query"](
            collection_name="", query_embeddings=[[0.1, 0.2]]
        )
        assert "error" in result

    def test_missing_embeddings(self, tool_fns):
        result = tool_fns["chroma_query"](
            collection_name="col", query_embeddings=[]
        )
        assert "error" in result

    def test_invalid_n_results(self, tool_fns):
        result = tool_fns["chroma_query"](
            collection_name="col", query_embeddings=[[0.1]], n_results=0
        )
        assert "error" in result

    def test_successful_query(self, tool_fns):
        col = MagicMock()
        col.query.return_value = {
            "ids": [["doc1", "doc2"]],
            "distances": [[0.1, 0.3]],
            "documents": [["Hello", "World"]],
            "metadatas": [[{"topic": "AI"}, {"topic": "ML"}]],
        }
        mock_client = MagicMock()
        mock_client.get_collection.return_value = col
        with patch(
            "aden_tools.tools.chroma_tool.chroma_tool._get_client",
            return_value=mock_client,
        ):
            result = tool_fns["chroma_query"](
                collection_name="my-col",
                query_embeddings=[[0.1, 0.2, 0.3]],
                n_results=5,
            )
        assert result["n_queries"] == 1
        assert result["ids"] == [["doc1", "doc2"]]
        assert result["distances"][0][0] == 0.1

    def test_query_with_where_filter(self, tool_fns):
        col = MagicMock()
        col.query.return_value = {"ids": [[]], "distances": [[]], "documents": [[]], "metadatas": [[]]}
        mock_client = MagicMock()
        mock_client.get_collection.return_value = col
        with patch(
            "aden_tools.tools.chroma_tool.chroma_tool._get_client",
            return_value=mock_client,
        ):
            result = tool_fns["chroma_query"](
                collection_name="my-col",
                query_embeddings=[[0.1, 0.2]],
                where={"topic": {"$eq": "AI"}},
            )
        call_kwargs = col.query.call_args[1]
        assert call_kwargs["where"] == {"topic": {"$eq": "AI"}}

    def test_not_configured_returns_error_and_help(self, tool_fns):
        with patch(
            "aden_tools.tools.chroma_tool.chroma_tool._get_client",
            side_effect=_ChromaNotConfigured("not configured"),
        ):
            result = tool_fns["chroma_query"](
                collection_name="my-col",
                query_embeddings=[[0.1, 0.2]],
            )
        assert "error" in result
        assert "help" in result


# ── chroma_get_documents ──────────────────────────────────────────────────────

class TestChromaGetDocuments:
    def test_missing_collection(self, tool_fns):
        result = tool_fns["chroma_get_documents"](collection_name="", ids=["1"])
        assert "error" in result

    def test_missing_all_filters(self, tool_fns):
        result = tool_fns["chroma_get_documents"](collection_name="col")
        assert "error" in result

    def test_successful_get_by_ids(self, tool_fns):
        col = MagicMock()
        col.get.return_value = {
            "ids": ["doc1"],
            "documents": ["Hello"],
            "metadatas": [{"topic": "AI"}],
        }
        mock_client = MagicMock()
        mock_client.get_collection.return_value = col
        with patch(
            "aden_tools.tools.chroma_tool.chroma_tool._get_client",
            return_value=mock_client,
        ):
            result = tool_fns["chroma_get_documents"](
                collection_name="my-col", ids=["doc1"]
            )
        assert result["count"] == 1
        assert result["ids"] == ["doc1"]

    def test_successful_get_by_where(self, tool_fns):
        col = MagicMock()
        col.get.return_value = {"ids": ["a", "b"], "documents": ["x", "y"], "metadatas": [{}, {}]}
        mock_client = MagicMock()
        mock_client.get_collection.return_value = col
        with patch(
            "aden_tools.tools.chroma_tool.chroma_tool._get_client",
            return_value=mock_client,
        ):
            result = tool_fns["chroma_get_documents"](
                collection_name="my-col",
                where={"topic": {"$eq": "AI"}},
            )
        assert result["count"] == 2


# ── chroma_update_documents ───────────────────────────────────────────────────

class TestChromaUpdateDocuments:
    def test_missing_collection(self, tool_fns):
        result = tool_fns["chroma_update_documents"](
            collection_name="", ids=["1"], documents=["new"]
        )
        assert "error" in result

    def test_missing_ids(self, tool_fns):
        result = tool_fns["chroma_update_documents"](
            collection_name="col", ids=[], documents=["new"]
        )
        assert "error" in result

    def test_missing_update_fields(self, tool_fns):
        result = tool_fns["chroma_update_documents"](
            collection_name="col", ids=["1"]
        )
        assert "error" in result

    def test_length_mismatch(self, tool_fns):
        result = tool_fns["chroma_update_documents"](
            collection_name="col",
            ids=["1", "2"],
            documents=["only one"],
        )
        assert "error" in result

    def test_successful_update(self, tool_fns):
        col = MagicMock()
        mock_client = MagicMock()
        mock_client.get_collection.return_value = col
        with patch(
            "aden_tools.tools.chroma_tool.chroma_tool._get_client",
            return_value=mock_client,
        ):
            result = tool_fns["chroma_update_documents"](
                collection_name="my-col",
                ids=["doc1"],
                metadatas=[{"topic": "updated"}],
            )
        assert result["status"] == "updated"
        assert result["updated_count"] == 1
        col.update.assert_called_once()


# ── chroma_delete_documents ───────────────────────────────────────────────────

class TestChromaDeleteDocuments:
    def test_missing_collection(self, tool_fns):
        result = tool_fns["chroma_delete_documents"](
            collection_name="", ids=["1"]
        )
        assert "error" in result

    def test_missing_all_criteria(self, tool_fns):
        result = tool_fns["chroma_delete_documents"](collection_name="col")
        assert "error" in result

    def test_successful_delete_by_ids(self, tool_fns):
        col = MagicMock()
        mock_client = MagicMock()
        mock_client.get_collection.return_value = col
        with patch(
            "aden_tools.tools.chroma_tool.chroma_tool._get_client",
            return_value=mock_client,
        ):
            result = tool_fns["chroma_delete_documents"](
                collection_name="my-col", ids=["doc1", "doc2"]
            )
        assert result["status"] == "deleted"
        col.delete.assert_called_once_with(ids=["doc1", "doc2"])

    def test_successful_delete_by_where(self, tool_fns):
        col = MagicMock()
        mock_client = MagicMock()
        mock_client.get_collection.return_value = col
        with patch(
            "aden_tools.tools.chroma_tool.chroma_tool._get_client",
            return_value=mock_client,
        ):
            result = tool_fns["chroma_delete_documents"](
                collection_name="my-col",
                where={"topic": {"$eq": "stale"}},
            )
        assert result["status"] == "deleted"
        col.delete.assert_called_once_with(where={"topic": {"$eq": "stale"}})

    def test_client_error(self, tool_fns):
        mock_client = MagicMock()
        mock_client.get_collection.side_effect = Exception("collection not found")
        with patch(
            "aden_tools.tools.chroma_tool.chroma_tool._get_client",
            return_value=mock_client,
        ):
            result = tool_fns["chroma_delete_documents"](
                collection_name="ghost", ids=["1"]
            )
        assert "error" in result
