from __future__ import annotations

import asyncio

from interview_agent_runtime.checkpoint import JsonFileCheckpointStore
from conftest import make_mock_runtime
from interview_agent_runtime.runtime import InterviewStage


def test_json_checkpoint_restore_continues_interview(tmp_path):
    asyncio.run(_case(tmp_path))


async def _case(tmp_path):
    store = JsonFileCheckpointStore(tmp_path)
    runtime = make_mock_runtime(checkpoint_store=store)
    board = await runtime.start_session("restore")
    board = await runtime.run_until_waiting_or_done(board.session_id)
    assert board.current_stage == InterviewStage.LISTENING

    restored_runtime = make_mock_runtime(checkpoint_store=JsonFileCheckpointStore(tmp_path))
    restored = await restored_runtime.load_context(board.session_id)
    assert restored.current_stage == InterviewStage.LISTENING
    assert restored.current_question is not None

    await restored_runtime.receive_answer(restored.session_id, "我会用缓存，但是细节还需要补充。")
    restored = await restored_runtime.run_until_waiting_or_done(restored.session_id)
    assert restored.current_stage in {InterviewStage.LISTENING, InterviewStage.FINISHED}
