"""Owner-scoped evaluation result query endpoints."""

from collections.abc import Callable
from typing import TypeVar, cast
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

from api.auth.dependencies import current_user
from api.auth.service import Principal
from api.evaluation_options import (
    RecommendationPreview,
    RecommendationPreviewRequest,
    RecommendationSetCreate,
    RecommendationSetDetail,
    RecommendationSetSummary,
    RecommendationWeakness,
    RecommendedProblem,
)
from api.files.dependencies import file_service
from api.files.governance import (
    DatasetVersion,
    DatasetVersionDetail,
    GovernancePreview,
    GovernanceRequest,
    GovernanceSaveRequest,
    VersionProblem,
    preview_governance,
    save_governance,
)
from api.files.service import FileService
from api.routes.evaluation_options import evaluation_options_service
from api.schemas import ApiResponse, PaginatedData
from api.services import EvaluationResultsService
from api.services.evaluation_options_service import EvaluationOptionsService
from src.recommender import analyze_recommendations

router = APIRouter(prefix="/api/v1", tags=["evaluation-results"])
T = TypeVar("T")


def evaluation_results_service(request: Request) -> EvaluationResultsService:
    return cast(EvaluationResultsService, request.app.state.evaluation_results)


def call(operation: Callable[[], T]) -> T:
    try:
        return operation()
    except ValueError as exc:
        raise HTTPException(404 if "not found" in str(exc).lower() else 400, str(exc)) from None


def _analytics(
    service: EvaluationResultsService,
    principal: Principal,
    method: Callable[..., dict],
    run_id: str | None,
    strategy: str | None,
    difficulty: str | None,
    tag: str | None,
) -> dict:
    return call(
        lambda: method(
            principal.user_id,
            run_id=run_id,
            strategy=strategy,
            difficulty=difficulty,
            tag=tag,
        )
    )


def _page(limit: int, offset: int) -> tuple[int, int]:
    return (limit if 1 <= limit <= 100 else 20, max(0, offset))


@router.post("/problems/governance/preview")
def preview_problem_governance(
    request: GovernanceRequest,
    principal: Principal = Depends(current_user),
    history: EvaluationResultsService = Depends(evaluation_results_service),
    files: FileService = Depends(file_service),
) -> ApiResponse[GovernancePreview]:
    preview, _ = call(lambda: preview_governance(files.store, history, principal.user_id, request))
    return ApiResponse(success=True, data=preview, message="Governance preview")


@router.post("/problems/governance/versions", status_code=201)
def save_problem_version(
    request: GovernanceSaveRequest,
    principal: Principal = Depends(current_user),
    history: EvaluationResultsService = Depends(evaluation_results_service),
    files: FileService = Depends(file_service),
) -> ApiResponse[DatasetVersion]:
    version = call(lambda: save_governance(files.store, history, principal.user_id, request))
    return ApiResponse(success=True, data=version, message="Dataset version saved")


@router.get("/problems/governance/versions")
def list_problem_versions(
    principal: Principal = Depends(current_user),
    files: FileService = Depends(file_service),
) -> ApiResponse[list[DatasetVersion]]:
    versions = files.store.dataset_versions(principal.user_id)
    return ApiResponse(
        success=True,
        data=[DatasetVersion.model_validate(version) for version in versions],
        message="Personal dataset versions",
    )


@router.get("/problems/governance/versions/{version_id}")
def get_problem_version(
    version_id: str,
    principal: Principal = Depends(current_user),
    files: FileService = Depends(file_service),
) -> ApiResponse[DatasetVersionDetail]:
    name, dataset = files.store.dataset_version(principal.user_id, version_id)
    return ApiResponse(
        success=True,
        data=DatasetVersionDetail(
            id=version_id,
            name=name,
            problem_count=len(dataset),
            problems=[VersionProblem.model_validate(problem) for problem in dataset],
        ),
        message="Personal dataset version",
    )


@router.post("/results/recommendations/preview")
def preview_recommendations(
    request: RecommendationPreviewRequest,
    principal: Principal = Depends(current_user),
    service: EvaluationResultsService = Depends(evaluation_results_service),
    options: EvaluationOptionsService = Depends(evaluation_options_service),
) -> ApiResponse[RecommendationPreview]:
    owner = principal.user_id
    catalog = options.problem_metadata(owner)
    history = call(
        lambda: service.recommendation_history(
            owner, request.run_ids, {pid: problem for pid, (problem, _) in catalog.items()}
        )
    )
    analysis, sufficient = analyze_recommendations(
        history,
        (problem for problem, source in catalog.values() if request.source in ("all", source)),
        min_samples=request.min_samples,
        failure_threshold=request.failure_threshold,
    )
    weaknesses = [
        RecommendationWeakness.model_validate(item) for item in analysis["weakness_report"]
    ]
    problems = [
        RecommendedProblem(
            problem_id=item["problem_id"],
            title=item["title"],
            difficulty=item["difficulty"],
            reason=item["recommendation_reason"],
            matching_groups=item["matching_groups"],
            failure_rate=item["recommendation_score"],
            total=item["sample_count"],
        )
        for item in analysis["recommended_problems"]
    ]
    if not sufficient:
        empty_reason = "insufficient_history"
    elif not weaknesses:
        empty_reason = "no_weaknesses"
    elif not problems:
        empty_reason = "no_candidates"
    else:
        empty_reason = None
    return ApiResponse(
        success=True,
        data=RecommendationPreview(
            weaknesses=weaknesses, problems=problems, empty_reason=empty_reason
        ),
        message="Recommendation preview",
    )


@router.get("/recommendation-sets")
def list_recommendation_sets(
    principal: Principal = Depends(current_user),
    options: EvaluationOptionsService = Depends(evaluation_options_service),
) -> ApiResponse[list[RecommendationSetSummary]]:
    return ApiResponse(
        success=True,
        data=[
            RecommendationSetSummary.model_validate(row)
            for row in options.files.recommendation_sets(principal.user_id)
        ],
        message="Personal recommendation sets",
    )


@router.post("/recommendation-sets", status_code=201)
def save_recommendation_set(
    request: RecommendationSetCreate,
    principal: Principal = Depends(current_user),
    options: EvaluationOptionsService = Depends(evaluation_options_service),
) -> ApiResponse[RecommendationSetSummary]:
    owner = principal.user_id
    options.selected_problems(owner, request.problem_ids, require_all=True)
    set_id = options.files.save_recommendation_set(owner, request.name, request.problem_ids)
    return ApiResponse(
        success=True,
        data=RecommendationSetSummary(id=set_id, name=request.name),
        message="Recommendation set saved",
    )


@router.get("/recommendation-sets/{set_id}")
def get_recommendation_set(
    set_id: str,
    principal: Principal = Depends(current_user),
    options: EvaluationOptionsService = Depends(evaluation_options_service),
) -> ApiResponse[RecommendationSetDetail]:
    owner = principal.user_id
    name, ids = options.files.recommendation_set(owner, set_id)
    problems = options.selected_problems(owner, ids)
    return ApiResponse(
        success=True,
        data=RecommendationSetDetail(
            id=set_id, name=name, problems=problems, unavailable_count=len(ids) - len(problems)
        ),
        message="Personal recommendation set",
    )


@router.get("/results/problems/{problem_id}")
def problem_history(
    problem_id: str,
    status: str | None = None,
    limit: int = 20,
    offset: int = 0,
    principal: Principal = Depends(current_user),
    service: EvaluationResultsService = Depends(evaluation_results_service),
) -> ApiResponse[PaginatedData[dict]]:
    limit, offset = _page(limit, offset)
    items, total = call(
        lambda: service.problem_history(
            principal.user_id, problem_id, status=status, limit=limit, offset=offset
        )
    )
    data = PaginatedData(
        items=items, total=total, limit=limit, offset=offset, has_more=offset + limit < total
    )
    return ApiResponse(success=True, data=data, message="Problem results retrieved")


@router.get("/results")
def list_results(
    strategy: str | None = None,
    difficulty: str | None = None,
    tag: str | None = None,
    status: str | None = None,
    limit: int = 20,
    offset: int = 0,
    sort: str = "completed_at",
    order: str = "desc",
    principal: Principal = Depends(current_user),
    service: EvaluationResultsService = Depends(evaluation_results_service),
) -> ApiResponse[PaginatedData[dict]]:
    limit, offset = _page(limit, offset)
    if sort not in {"completed_at", "created_at"}:
        sort = "completed_at"
    items, total = call(
        lambda: service.list_runs(
            principal.user_id,
            strategy=strategy,
            difficulty=difficulty,
            tag=tag,
            status=status,
            limit=limit,
            offset=offset,
            sort=sort,
            order=order,
        )
    )
    data = PaginatedData(
        items=items, total=total, limit=limit, offset=offset, has_more=offset + limit < total
    )
    return ApiResponse(success=True, data=data, message="Evaluation results retrieved")


@router.get("/analytics/success-rate")
def analytics_success_rate(
    run_id: str | None = None,
    strategy: str | None = None,
    difficulty: str | None = None,
    tag: str | None = None,
    principal: Principal = Depends(current_user),
    service: EvaluationResultsService = Depends(evaluation_results_service),
) -> ApiResponse[dict]:
    data = _analytics(service, principal, service.success_rate, run_id, strategy, difficulty, tag)
    return ApiResponse(success=True, data=data, message="Success rate retrieved")


@router.get("/analytics/tokens")
def analytics_tokens(
    run_id: str | None = None,
    strategy: str | None = None,
    difficulty: str | None = None,
    tag: str | None = None,
    principal: Principal = Depends(current_user),
    service: EvaluationResultsService = Depends(evaluation_results_service),
) -> ApiResponse[dict]:
    data = _analytics(service, principal, service.tokens, run_id, strategy, difficulty, tag)
    return ApiResponse(success=True, data=data, message="Token analytics retrieved")


@router.get("/analytics/iterations")
def analytics_iterations(
    run_id: str | None = None,
    strategy: str | None = None,
    difficulty: str | None = None,
    tag: str | None = None,
    principal: Principal = Depends(current_user),
    service: EvaluationResultsService = Depends(evaluation_results_service),
) -> ApiResponse[dict]:
    data = _analytics(service, principal, service.iterations, run_id, strategy, difficulty, tag)
    return ApiResponse(success=True, data=data, message="Iteration analytics retrieved")


@router.get("/analytics/failure-modes")
def analytics_failure_modes(
    run_id: str | None = None,
    strategy: str | None = None,
    difficulty: str | None = None,
    tag: str | None = None,
    principal: Principal = Depends(current_user),
    service: EvaluationResultsService = Depends(evaluation_results_service),
) -> ApiResponse[dict]:
    data = _analytics(service, principal, service.failure_modes, run_id, strategy, difficulty, tag)
    return ApiResponse(success=True, data=data, message="Failure modes retrieved")


@router.get("/visualizations/success-rate-chart")
def visualization_success_rate_chart(
    run_id: str | None = None,
    strategy: str | None = None,
    difficulty: str | None = None,
    tag: str | None = None,
    principal: Principal = Depends(current_user),
    service: EvaluationResultsService = Depends(evaluation_results_service),
) -> ApiResponse[dict]:
    data = _analytics(
        service, principal, service.success_rate_chart, run_id, strategy, difficulty, tag
    )
    return ApiResponse(success=True, data=data, message="Success rate chart retrieved")


@router.get("/visualizations/token-chart")
def visualization_token_chart(
    run_id: str | None = None,
    strategy: str | None = None,
    difficulty: str | None = None,
    tag: str | None = None,
    principal: Principal = Depends(current_user),
    service: EvaluationResultsService = Depends(evaluation_results_service),
) -> ApiResponse[dict]:
    data = _analytics(service, principal, service.token_chart, run_id, strategy, difficulty, tag)
    return ApiResponse(success=True, data=data, message="Token chart retrieved")


@router.get("/visualizations/cost-accuracy")
def visualization_cost_accuracy(
    run_id: str | None = None,
    strategy: str | None = None,
    difficulty: str | None = None,
    tag: str | None = None,
    principal: Principal = Depends(current_user),
    service: EvaluationResultsService = Depends(evaluation_results_service),
) -> ApiResponse[dict]:
    data = _analytics(service, principal, service.cost_accuracy, run_id, strategy, difficulty, tag)
    return ApiResponse(success=True, data=data, message="Cost accuracy chart retrieved")


@router.get("/visualizations/capability-radar")
def visualization_capability_radar(
    run_id: str | None = None,
    strategy: str | None = None,
    difficulty: str | None = None,
    tag: str | None = None,
    principal: Principal = Depends(current_user),
    service: EvaluationResultsService = Depends(evaluation_results_service),
) -> ApiResponse[dict]:
    data = _analytics(
        service, principal, service.capability_radar, run_id, strategy, difficulty, tag
    )
    return ApiResponse(success=True, data=data, message="Capability radar retrieved")


@router.get("/visualizations/learning-curve")
def visualization_learning_curve(
    suite_id: str | None = None,
    principal: Principal = Depends(current_user),
    service: EvaluationResultsService = Depends(evaluation_results_service),
) -> ApiResponse[dict]:
    data = call(lambda: service.learning_curve(principal.user_id, suite_id=suite_id))
    return ApiResponse(success=True, data=data, message="Learning curve retrieved")


@router.get("/failures/by-tag")
def failures_by_tag(
    run_id: str | None = None,
    strategy: str | None = None,
    difficulty: str | None = None,
    tag: str | None = None,
    principal: Principal = Depends(current_user),
    service: EvaluationResultsService = Depends(evaluation_results_service),
) -> ApiResponse[dict]:
    data = _analytics(
        service, principal, service.failures_by_tag, run_id, strategy, difficulty, tag
    )
    return ApiResponse(success=True, data=data, message="Failures by tag retrieved")


@router.get("/failures/summary/{run_id}")
def failure_summary(
    run_id: str,
    principal: Principal = Depends(current_user),
    service: EvaluationResultsService = Depends(evaluation_results_service),
) -> ApiResponse[dict]:
    data = call(lambda: service.failure_summary(principal.user_id, run_id))
    return ApiResponse(success=True, data=data, message="Failure summary retrieved")


@router.get("/failures/cases/{run_id}")
def failure_cases(
    run_id: str,
    principal: Principal = Depends(current_user),
    service: EvaluationResultsService = Depends(evaluation_results_service),
) -> ApiResponse[dict]:
    data = call(lambda: service.failure_cases(principal.user_id, run_id))
    return ApiResponse(success=True, data=data, message="Failure cases retrieved")


@router.get("/results/{run_id}")
def get_result(
    run_id: str,
    limit: int = 20,
    offset: int = 0,
    principal: Principal = Depends(current_user),
    service: EvaluationResultsService = Depends(evaluation_results_service),
) -> ApiResponse[dict]:
    limit, offset = _page(limit, offset)
    data = call(lambda: service.detail(principal.user_id, run_id, limit=limit, offset=offset))
    return ApiResponse(success=True, data=data, message="Evaluation result retrieved")


def _require_run_id(run_id: str | None) -> str:
    if not run_id:
        raise HTTPException(400, "run_id is required")
    return run_id


@router.get("/compare/strategies")
def compare_strategies(
    run_id: str | None = None,
    principal: Principal = Depends(current_user),
    service: EvaluationResultsService = Depends(evaluation_results_service),
) -> ApiResponse[dict]:
    run_id = _require_run_id(run_id)
    data = call(lambda: service.compare_strategies(principal.user_id, run_id))
    return ApiResponse(success=True, data=data, message="Strategy comparison retrieved")


@router.get("/compare/models")
def compare_models(
    principal: Principal = Depends(current_user),
    service: EvaluationResultsService = Depends(evaluation_results_service),
) -> ApiResponse[dict]:
    data = call(lambda: service.compare_models(principal.user_id))
    return ApiResponse(success=True, data=data, message="Model comparison retrieved")


@router.get("/compare/history")
def compare_history(
    run_id: str | None = None,
    principal: Principal = Depends(current_user),
    service: EvaluationResultsService = Depends(evaluation_results_service),
) -> ApiResponse[dict]:
    run_id = _require_run_id(run_id)
    data = call(lambda: service.compare_history(principal.user_id, run_id))
    return ApiResponse(success=True, data=data, message="History comparison retrieved")


@router.get("/compare/ab-test/{test_id}")
def compare_ab_test(
    test_id: str,
    request: Request,
    principal: Principal = Depends(current_user),
) -> ApiResponse[dict]:
    """Same ABTestService.results call as GET /ab-tests/{test_id}/results."""
    ab_tests = request.app.state.ab_tests
    data = call(lambda: ab_tests.results(test_id, principal.user_id))
    return ApiResponse(success=True, data=data, message="A/B comparison retrieved")


def _download(body: str, media_type: str, filename: str) -> Response:
    disposition = "attachment; filename*=UTF-8''" + quote(filename, safe="")
    return Response(body, media_type=media_type, headers={"Content-Disposition": disposition})


@router.get("/reports/markdown/{run_id}")
def report_markdown(
    run_id: str,
    principal: Principal = Depends(current_user),
    service: EvaluationResultsService = Depends(evaluation_results_service),
) -> Response:
    body = call(lambda: service.report_markdown(principal.user_id, run_id))
    return _download(body, "text/markdown", f"{run_id}.md")


@router.get("/reports/html/{run_id}")
def report_html(
    run_id: str,
    principal: Principal = Depends(current_user),
    service: EvaluationResultsService = Depends(evaluation_results_service),
) -> Response:
    body = call(lambda: service.report_html(principal.user_id, run_id))
    return _download(body, "text/html", f"{run_id}.html")


@router.get("/reports/csv/{run_id}")
def report_csv(
    run_id: str,
    principal: Principal = Depends(current_user),
    service: EvaluationResultsService = Depends(evaluation_results_service),
) -> Response:
    body = call(lambda: service.report_csv(principal.user_id, run_id))
    return _download(body, "text/csv", f"{run_id}.csv")
