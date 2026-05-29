"""
ECHO Orchestrator — Pydantic Data Models
All request/response schemas, domain objects, and log structures live here.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator


# ── Enums ─────────────────────────────────────────────────────────────────────


class WorkerType(str, Enum):
    BACKEND = "backend_worker"
    FRONTEND = "frontend_worker"
    TEST = "test_worker"
    DOCS = "docs_worker"
    RETRIEVAL = "retrieval_worker"


class TaskStatus(str, Enum):
    PENDING = "pending"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    IN_PROGRESS = "in_progress"
    PENDING_DIFF = "pending_diff"   # Worker fertig, Diff wartet auf Gate-2-Freigabe
    COMPLETED = "completed"
    FAILED = "failed"


class ModelBackend(str, Enum):
    ANTHROPIC = "anthropic"
    OLLAMA = "ollama"


class TaskPriority(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


# ── Core Domain Models ────────────────────────────────────────────────────────


class TaskPayload(BaseModel):
    """Incoming task submitted by an API caller."""

    task_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique task identifier (auto-generated if omitted)",
    )
    title: str = Field(..., min_length=3, max_length=200, description="Short task title")
    description: str = Field(..., min_length=10, description="Full task description")
    worker_type: WorkerType = Field(..., description="Target worker category")
    priority: TaskPriority = Field(default=TaskPriority.NORMAL)
    context: dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary key/value context passed to the worker",
    )
    files: list[str] = Field(
        default_factory=list,
        description="Relative file paths relevant to this task",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class HumanApproval(BaseModel):
    """Approval or rejection signal from the human operator."""

    task_id: str
    approved: bool
    reviewer: str = Field(
        ...,
        min_length=1,
        description="Name or identifier of the human reviewer",
    )
    comment: str = Field(default="", description="Optional reviewer comment")
    reviewed_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class WorkerResult(BaseModel):
    """Output produced by a worker after executing a task."""

    task_id: str
    worker_type: WorkerType
    model_backend: ModelBackend
    model_name: str
    success: bool
    output: str = Field(description="Primary text output / generated content")
    artifacts: list[str] = Field(
        default_factory=list,
        description="Paths to files produced by the worker",
    )
    error: str | None = Field(
        default=None,
        description="Error message if success=False",
    )
    extra: dict[str, Any] = Field(
        default_factory=dict,
        description="Worker-specific metadata (e.g. created/modified/deleted file lists)",
    )
    completed_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class TaskState(BaseModel):
    """Full lifecycle state of a task — stored in-memory or persisted."""

    payload: TaskPayload
    status: TaskStatus = TaskStatus.PENDING
    model_backend: ModelBackend | None = None
    complexity_score: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Router-assigned complexity score",
    )
    result: WorkerResult | None = None
    approval: HumanApproval | None = None

    @model_validator(mode="after")
    def validate_approval_consistency(self) -> TaskState:
        if self.status == TaskStatus.APPROVED and self.approval is None:
            raise ValueError("Status APPROVED requires an approval record.")
        if self.status == TaskStatus.REJECTED and self.approval is None:
            raise ValueError("Status REJECTED requires an approval record.")
        return self


# ── API Schemas ───────────────────────────────────────────────────────────────


class SubmitTaskRequest(BaseModel):
    title: str = Field(..., min_length=3, max_length=200)
    description: str = Field(..., min_length=10)
    worker_type: WorkerType
    priority: TaskPriority = TaskPriority.NORMAL
    context: dict[str, Any] = Field(default_factory=dict)
    files: list[str] = Field(default_factory=list)


class SubmitTaskResponse(BaseModel):
    task_id: str
    status: TaskStatus
    message: str


class ApproveTaskRequest(BaseModel):
    approved: bool
    reviewer: str = Field(..., min_length=1)
    comment: str = ""


class TaskStatusResponse(BaseModel):
    task_id: str
    title: str
    status: TaskStatus
    worker_type: WorkerType
    model_backend: ModelBackend | None
    complexity_score: float | None
    result: WorkerResult | None
    created_at: datetime


# ── Logging / Observability ───────────────────────────────────────────────────


class TokenUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    @model_validator(mode="after")
    def compute_total(self) -> TokenUsage:
        self.total_tokens = self.prompt_tokens + self.completion_tokens
        return self


class MetricLogEntry(BaseModel):
    """
    One line in the JSONL metrics log.
    Written by BaseWorker on every task completion.
    """

    log_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    task_id: str
    worker_type: WorkerType
    model_backend: ModelBackend
    model_name: str
    success: bool
    duration_seconds: float = Field(ge=0.0)
    token_usage: TokenUsage
    files_touched: list[str] = Field(default_factory=list)
    error: str | None = None
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
