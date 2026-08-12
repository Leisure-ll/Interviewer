from __future__ import annotations

import asyncio

from interview_agent_runtime.checkpoint import JsonFileCheckpointStore
from interview_agent_runtime.harness import HarnessConfig, InterviewHarness


def test_harness_selects_checkpoint_store_runtime_uses_it(tmp_path):
    asyncio.run(_case(tmp_path))


async def _case(tmp_path):
    harness = InterviewHarness.from_config(HarnessConfig.development(checkpoint_dir=tmp_path))
    runtime = harness.create_runtime()
    board = await runtime.start_session("checkpoint-boundary")
    await runtime.run_until_waiting_or_done(board.session_id)

    assert isinstance(harness.checkpoint_store, JsonFileCheckpointStore)
    assert (tmp_path / "checkpoint-boundary.json").exists()
