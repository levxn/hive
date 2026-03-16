"""
ChromaDB credentials.

Contains credentials for ChromaDB vector database operations.
Both are optional — the tool falls back to local mode when neither is set.
"""

from .base import CredentialSpec

CHROMA_CREDENTIALS = {
    "chroma_api_key": CredentialSpec(
        env_var="CHROMA_API_KEY",
        tools=[
            "chroma_list_collections",
            "chroma_create_collection",
            "chroma_get_or_create_collection",
            "chroma_delete_collection",
            "chroma_collection_count",
            "chroma_add_documents",
            "chroma_query",
            "chroma_get_documents",
            "chroma_update_documents",
            "chroma_delete_documents",
        ],
        required=False,
        startup_required=False,
        help_url="https://docs.trychroma.com/deployment/chroma-server/cloud-client",
        description="API key for Chroma Cloud (set together with CHROMA_TENANT and CHROMA_DATABASE)",
        direct_api_key_supported=True,
        api_key_instructions="""To use Chroma Cloud:
1. Go to https://docs.trychroma.com/deployment/chroma-server/cloud-client
2. Create an account and obtain an API key
3. Set the following environment variables:
   export CHROMA_API_KEY=your-api-key
   export CHROMA_TENANT=your-tenant-id
   export CHROMA_DATABASE=your-database-name

For a self-hosted Chroma server, set instead:
   export CHROMA_HOST=localhost
   export CHROMA_PORT=8000  (optional, default 8000)

For local-only usage, no credentials are needed.""",
        credential_id="chroma_api_key",
        credential_key="api_key",
    ),
    "chroma_token": CredentialSpec(
        env_var="CHROMA_SERVER_AUTHN_CREDENTIALS",
        tools=[
            "chroma_list_collections",
            "chroma_create_collection",
            "chroma_get_or_create_collection",
            "chroma_delete_collection",
            "chroma_collection_count",
            "chroma_add_documents",
            "chroma_query",
            "chroma_get_documents",
            "chroma_update_documents",
            "chroma_delete_documents",
        ],
        required=False,
        startup_required=False,
        help_url="https://docs.trychroma.com/deployment/chroma-server/auth",
        description="Auth token for a self-hosted Chroma server with token authentication enabled",
        direct_api_key_supported=True,
        api_key_instructions="""To configure token auth on a self-hosted Chroma server:
1. Start Chroma with token auth enabled (see https://docs.trychroma.com/deployment/chroma-server/auth)
2. Set the token:
   export CHROMA_SERVER_AUTHN_CREDENTIALS=your-token
   export CHROMA_HOST=your-server-host
   export CHROMA_PORT=8000""",
        credential_id="chroma_token",
        credential_key="api_key",
    ),
}
