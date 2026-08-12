from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from interview_agent_runtime.artifacts import InterviewReportArtifact, QuestionArtifact
from interview_agent_runtime.blackboard import InterviewBlackboard
from interview_agent_runtime.runtime import InterviewRuntime, InterviewStage


@dataclass
class InterviewStatus:
    session_id: str
    stage: InterviewStage
    current_question: Optional[QuestionArtifact]
    current_dimension: str
    progress: float
    report_ready: bool


class InterviewApplicationService:
    def __init__(self, runtime: Optional[InterviewRuntime] = None) -> None:
        self.runtime = runtime or InterviewRuntime()

    async def start_interview(
        self,
        candidate_id: str,
        resume: dict[str, Any],
        jd: dict[str, Any],
        session_id: Optional[str] = None,
    ) -> InterviewStatus:
        board = await self.runtime.start_session(
            session_id=session_id,
            candidate_id=candidate_id,
            resume=resume,
            jd=jd,
        )
        board = await self.runtime.run_until_waiting_or_done(board.session_id)
        return self._status(board)

    async def submit_answer(
        self,
        session_id: str,
        answer: str,
        *,
        source: str = "text",
        duration_seconds: Optional[float] = None,
    ) -> InterviewStatus:
        await self.runtime.receive_answer(
            session_id,
            answer,
            source=source,
            duration_seconds=duration_seconds,
        )
        board = await self.runtime.run_until_waiting_or_done(session_id)
        return self._status(board)

    async def resume_interview(self, session_id: str) -> InterviewStatus:
        board = await self.runtime.run_until_waiting_or_done(session_id)
        return self._status(board)

    async def get_status(self, session_id: str) -> InterviewStatus:
        board = await self.runtime.load_context(session_id)
        return self._status(board)

    async def get_report(self, session_id: str) -> Optional[InterviewReportArtifact]:
        board = await self.runtime.load_context(session_id)
        return board.report

    def _status(self, board: InterviewBlackboard) -> InterviewStatus:
        return InterviewStatus(
            session_id=board.session_id,
            stage=board.current_stage,
            current_question=board.current_question,
            current_dimension=board.current_dimension,
            progress=self._progress(board),
            report_ready=board.report is not None,
        )

    def _progress(self, board: InterviewBlackboard) -> float:
        if board.plan is None:
            return 0.0
        total = sum(item.question_budget + item.asked_questions for item in board.plan.dimensions)
        asked = len([item for item in board.question_history if not item.is_follow_up])
        return min(1.0, asked / max(1, total))
