"""Evaluation endpoints."""

from fastapi import APIRouter, HTTPException, status

from api.models import EvaluationCreateRequest, EvaluationUpdateRequest
from api.schemas import ApiResponse, EvaluationResponse, PaginatedData, ProgressInfo
from api.services import EvaluationService

router = APIRouter(prefix="/api/v1", tags=["evaluations"])
service = EvaluationService()


@router.post("/evaluations", status_code=status.HTTP_201_CREATED)
async def create_evaluation(request: EvaluationCreateRequest) -> ApiResponse[EvaluationResponse]:
    """Create a new evaluation task."""
    try:
        result = service.create_evaluation(request)
        return ApiResponse(
            success=True,
            data=result,
            message="Evaluation created successfully",
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/evaluations")
async def list_evaluations(
    status: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> ApiResponse[PaginatedData[EvaluationResponse]]:
    """List all evaluation tasks with optional filtering."""
    try:
        # Validate pagination
        if limit < 1 or limit > 100:
            limit = 20
        if offset < 0:
            offset = 0

        results, total = service.list_evaluations(status=status, limit=limit, offset=offset)
        has_more = (offset + limit) < total

        data = PaginatedData(
            items=results,
            total=total,
            limit=limit,
            offset=offset,
            has_more=has_more,
        )

        return ApiResponse(
            success=True,
            data=data,
            message="Evaluations retrieved successfully",
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/evaluations/{evaluation_id}")
async def get_evaluation(evaluation_id: str) -> ApiResponse[EvaluationResponse]:
    """Get evaluation task details."""
    try:
        result = service.get_evaluation(evaluation_id)
        return ApiResponse(
            success=True,
            data=result,
            message="Evaluation retrieved successfully",
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/evaluations/{evaluation_id}")
async def update_evaluation(
    evaluation_id: str, request: EvaluationUpdateRequest
) -> ApiResponse[EvaluationResponse]:
    """Update evaluation task configuration (pending tasks only)."""
    try:
        result = service.update_evaluation(evaluation_id, request)
        return ApiResponse(
            success=True,
            data=result,
            message="Evaluation updated successfully",
        )
    except ValueError as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=404, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/evaluations/{evaluation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_evaluation(evaluation_id: str):
    """Delete evaluation task (pending or completed only)."""
    try:
        service.delete_evaluation(evaluation_id)
        return None
    except ValueError as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=404, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/evaluations/{evaluation_id}/start", status_code=status.HTTP_202_ACCEPTED)
async def start_evaluation(evaluation_id: str) -> ApiResponse[EvaluationResponse]:
    """Start evaluation task execution in background."""
    try:
        result = service.start_evaluation(evaluation_id)
        return ApiResponse(
            success=True,
            data=result,
            message="Evaluation started successfully",
        )
    except ValueError as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=404, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/evaluations/{evaluation_id}/progress")
async def get_evaluation_progress(evaluation_id: str) -> ApiResponse[ProgressInfo]:
    """Get evaluation task execution progress."""
    try:
        progress = service.get_progress(evaluation_id)
        return ApiResponse(
            success=True,
            data=progress,
            message="Progress retrieved successfully",
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/evaluations/{evaluation_id}/cancel")
async def cancel_evaluation(evaluation_id: str) -> ApiResponse[EvaluationResponse]:
    """Cancel running evaluation task."""
    try:
        result = service.cancel_evaluation(evaluation_id)
        return ApiResponse(
            success=True,
            data=result,
            message="Evaluation cancelled successfully",
        )
    except ValueError as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=404, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
