"""从执行器使用的共享题库和本人导入读取评估选项。"""

import time
from collections import Counter

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from api.auth.service import PROVIDER_URLS, AuthService
from api.db.models import Problem
from api.evaluation_options import (
    EvaluationOptions,
    ModelOptions,
    ProblemOption,
    ProblemSource,
    ProblemSourceFilter,
    SourceOption,
    StrategyOption,
)
from api.files.store import FileStore
from api.schemas import PaginatedData
from src.harness import AlgorithmHarness
from src.llm_client import LLMClient


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

    def models(self, owner_id: str, api_key_id: str) -> ModelOptions:
        self.auth.limit("models:" + owner_id)
        key = self.auth.owned_key(api_key_id, owner_id)
        deadline = time.monotonic() + 10.0
        client = None
        ids: list[str] = []
        complete = False
        try:
            client = LLMClient(self.auth.llm_config(api_key_id, owner_id, "model-list"))
            client.client = client.client.with_options(
                timeout=5.0, max_retries=0, base_url=PROVIDER_URLS[key["provider"]]
            )
            remaining = deadline - time.monotonic()
            if remaining > 0:
                page = client.client.models.list(timeout=min(5.0, remaining))
                while True:
                    capacity = 500 - len(ids)
                    for model in page.data:
                        if len(ids) == 500:
                            break
                        ids.append(model.id)
                    has_next = getattr(page, "has_next_page", None)
                    if not callable(has_next):
                        break
                    more = has_next()
                    if len(ids) >= 500:
                        break
                    if len(page.data) <= capacity and not more:
                        # Anthropic also returns no next page when its cursor is
                        # missing; only has_more=False proves its terminal page.
                        complete = key["provider"] in ("openai", "siliconflow") or (
                            getattr(page, "has_more", None) is False
                        )
                        break
                    next_page = getattr(page, "get_next_page", None)
                    remaining = deadline - time.monotonic()
                    if remaining <= 0 or not callable(next_page):
                        break
                    # Both supported SDKs copy these request options for subsequent
                    # pages; changing client.timeout alone leaves the original 5s.
                    page._options.timeout = min(5.0, remaining)
                    page = next_page()
        except Exception:
            # Provider exceptions may embed keys or response bodies.
            raise HTTPException(503, "Provider model listing unavailable") from None
        finally:
            if client is not None:
                try:
                    client.client.close()
                except Exception:
                    pass
        current = self.auth.store.key(api_key_id, owner_id)
        if current is None or current["ciphertext"] != key["ciphertext"]:
            raise HTTPException(409, "API key changed during model listing")
        return ModelOptions(provider=key["provider"], models=ids, complete=complete)
