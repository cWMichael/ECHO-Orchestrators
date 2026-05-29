"""
ECHO Orchestrator — Planner API
Gate 0: Plan aus natürlicher Sprache, Freigabe, dann Task-Einreichung.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from config import Settings, get_settings
from core_router import submit_task
from models import (
    ApprovePlanRequest,
    PlanRequest,
    PlanResult,
    SubmitTaskRequest,
    SubmitTaskResponse,
)
from planner import Planner, PlannerError

logger = logging.getLogger("echo.planner_router")

router = APIRouter(tags=["Planner"])

_pending_plans: dict[str, PlanResult] = {}


@router.post(
    "/plan",
    response_model=PlanResult,
    status_code=status.HTTP_201_CREATED,
    summary="Plan aus natürlicher Sprache erstellen (Gate 0)",
)
async def create_plan(
    request: PlanRequest,
    settings: Settings = Depends(get_settings),
) -> PlanResult:
    planner = Planner(settings)
    try:
        result = await planner.create_plan(request)
    except PlannerError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    finally:
        await planner.close()

    _pending_plans[result.plan_id] = result
    logger.info("Plan %s gespeichert (%d Tasks).", result.plan_id, len(result.tasks))
    return result


@router.get(
    "/plan/{plan_id}",
    response_model=PlanResult,
    summary="Gespeicherten Plan abrufen",
)
async def get_plan(plan_id: str) -> PlanResult:
    plan = _pending_plans.get(plan_id)
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plan '{plan_id}' nicht gefunden oder bereits ausgeführt.",
        )
    return plan


@router.post(
    "/plan/{plan_id}/approve",
    response_model=list[SubmitTaskResponse],
    summary="Gate 0: Plan freigeben und Tasks einreichen",
)
async def approve_plan(
    plan_id: str,
    request: ApprovePlanRequest,
    settings: Settings = Depends(get_settings),
) -> list[SubmitTaskResponse]:
    plan = _pending_plans.get(plan_id)
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plan '{plan_id}' nicht gefunden oder bereits ausgeführt.",
        )

    if not request.approved:
        _pending_plans.pop(plan_id, None)
        logger.info("Plan %s abgelehnt von %s.", plan_id, request.reviewer)
        return []

    indices = request.selected_task_indices
    if indices is not None:
        tasks = []
        for i in indices:
            if 0 <= i < len(plan.tasks):
                tasks.append(plan.tasks[i])
        if not tasks:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="selected_task_indices enthält keine gültigen Indizes.",
            )
    else:
        tasks = plan.tasks

    submitted: list[SubmitTaskResponse] = []
    for planned in tasks:
        submit_req = SubmitTaskRequest(
            title=planned.title,
            description=planned.description,
            worker_type=planned.worker_type,
            priority=planned.priority,
            context=planned.context,
            files=planned.files,
        )
        resp = await submit_task(submit_req, settings)
        submitted.append(resp)

    _pending_plans.pop(plan_id, None)
    logger.info(
        "Plan %s freigegeben von %s — %d Task(s) eingereicht.",
        plan_id,
        request.reviewer,
        len(submitted),
    )
    return submitted


@router.get(
    "/plans/pending",
    response_model=list[dict[str, Any]],
    summary="Ausstehende Pläne (nur Metadaten)",
)
async def list_pending_plans() -> list[dict[str, Any]]:
    return [
        {
            "plan_id": p.plan_id,
            "plan_title": p.plan_title,
            "task_count": len(p.tasks),
            "estimated_total_tokens": p.estimated_total_tokens,
        }
        for p in _pending_plans.values()
    ]
