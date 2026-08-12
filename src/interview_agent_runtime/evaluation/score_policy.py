from __future__ import annotations


class ScorePolicy:
    def score(
        self,
        *,
        matched_points: list[str],
        missing_points: list[str],
        answer_length: int,
        is_follow_up: bool,
    ) -> float:
        score = 55.0 + min(25.0, len(matched_points) * 6.0) + min(10.0, answer_length / 20.0)
        score -= len(missing_points) * (8.0 if not is_follow_up else 5.0)
        return max(20.0, min(95.0, round(score, 1)))
