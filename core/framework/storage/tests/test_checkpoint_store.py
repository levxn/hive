import asyncio

from framework.schemas.checkpoint import Checkpoint
from framework.storage.checkpoint_store import CheckpointStore


def test_checkpoint_store_save_and_filter(tmp_path):
    store = CheckpointStore(tmp_path)

    cp1 = Checkpoint.create(
        checkpoint_type="node_start",
        session_id="session_a",
        current_node="node_1",
        execution_path=["node_1"],
        shared_memory={},
        is_clean=True,
    )
    cp2 = Checkpoint.create(
        checkpoint_type="node_complete",
        session_id="session_a",
        current_node="node_2",
        execution_path=["node_1", "node_2"],
        shared_memory={},
        is_clean=False,
    )

    asyncio.run(store.save_checkpoint(cp1))
    asyncio.run(store.save_checkpoint(cp2))

    all_checkpoints = asyncio.run(store.list_checkpoints())
    assert len(all_checkpoints) == 2

    start_checkpoints = asyncio.run(store.list_checkpoints(checkpoint_type="node_start"))
    assert len(start_checkpoints) == 1
    assert start_checkpoints[0].checkpoint_type == "node_start"

    clean_checkpoints = asyncio.run(store.list_checkpoints(is_clean=True))
    assert len(clean_checkpoints) == 1
    assert clean_checkpoints[0].checkpoint_id == cp1.checkpoint_id
