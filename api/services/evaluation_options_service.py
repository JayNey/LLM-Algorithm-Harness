"""从执行器使用的共享题库和本人导入读取评估选项。"""

from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from api.auth.service import AuthService
from api.db.models import Problem
from api.evaluation_options import (
    EvaluationOptions,
    ProblemOption,
    ProblemSource,
    ProblemSourceFilter,
    SourceOption,
    StrategyOption,
)
from api.files.store import FileStore
from api.schemas import PaginatedData
from src.harness import AlgorithmHarness


class EvaluationOptionsService:
    def __init__(
        self, session_factory: sessionmaker[Session], files: FileStore, auth: AuthService
    ) -> None:
        self.session_factory = session_factory
        self.files = files
        self.auth = auth

    def _effective_problems(self, owner_id: str) -> list[ProblemOption]:
        # 与 worker 一致：本人集合按 ID 去重，最后一项覆盖共享同 ID。
        personal = {item["problem_id"]: item for item in self.files.dataset(owner_id)}
        with self.session_factory() as session:
            shared = session.execute(select(Problem.problem_id, Problem.title, Problem.difficulty))
            problems = [
                ProblemOption(
                    problem_id=row.problem_id,
                    title=row.title,
                    difficulty=row.difficulty,
                    source="shared",
                )
                for row in shared
                if row.problem_id not in personal
            ]
        problems.extend(
            ProblemOption(
                problem_id=pid,
                title=item["title"],
                difficulty=item.get("difficulty"),
                source="personal",
            )
            for pid, item in personal.items()
        )
        return sorted(problems, key=lambda item: item.problem_id)

    def options(self, owner_id: str) -> EvaluationOptions:
        counts = Counter(item.source for item in self._effective_problems(owner_id))
        labels: tuple[tuple[ProblemSource, str], ...] = (
            ("shared", "共享题库"),
            ("personal", "本人导入"),
        )
        return EvaluationOptions(
            strategies=[StrategyOption(name=name) for name in AlgorithmHarness.STRATEGY_MAP],
            sources=[
                SourceOption(id=source, label=label, problem_count=counts[source])
                for source, label in labels
                if counts[source]
            ],
        )

    def problems(
        self,
        owner_id: str,
        source: ProblemSourceFilter = "all",
        limit: int = 20,
        offset: int = 0,
    ) -> PaginatedData[ProblemOption]:
        problems = [
            item
            for item in self._effective_problems(owner_id)
            if source == "all" or item.source == source
        ]
        total = len(problems)
        return PaginatedData(
            items=problems[offset : offset + limit],
            total=total,
            limit=limit,
            offset=offset,
            has_more=offset + limit < total,
        )
