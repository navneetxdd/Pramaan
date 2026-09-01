from __future__ import annotations

from pydantic import BaseModel, Field


class CaseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    examiner_name: str = Field(min_length=1, max_length=120)
    notes: str | None = Field(default=None, max_length=4000)


class Device(BaseModel):
    id: str
    case_id: str
    declared_brand: str | None = None
    detected_engine: str | None = None
    detection_confidence: float | None = None
    detection_trace_json: str | None = None
    model_hint: str | None = None
    serial_hint: str | None = None
    image_path: str
    image_md5: str | None = None
    image_sha256: str | None = None
    acquisition_status: str
    bad_sector_map_json: str | None = None
    acquired_at: str | None = None
    drift_offset_seconds: float = 0
    source_type: str | None = None
    source_identifier: str | None = None
    source_size_bytes: int | None = None
    acquisition_started_at: str | None = None
    acquisition_completed_at: str | None = None
    acquisition_tool_version: str | None = None
    acquisition_method: str | None = None
    acquisition_operator: str | None = None
    write_blocker: str | None = None
    acquisition_error: str | None = None
    verification_status: str = "pending"
    verification_checked_at: str | None = None


class Case(BaseModel):
    id: str
    name: str
    examiner_name: str
    created_at: str
    notes: str | None = None


class CaseDetail(Case):
    devices: list[Device] = Field(default_factory=list)


class CustodyLogEntry(BaseModel):
    id: int
    timestamp_utc: str
    actor: str
    action: str
    target_type: str
    target_id: str
    prev_row_hash: str
    this_row_hash: str


class CustodyLogStatus(BaseModel):
    intact: bool
    first_broken_row_id: int | None = None
    tip_hash: str | None = None


class JobStatus(BaseModel):
    status: str
    result: dict | None = None
    error: str | None = None
    progress: float = 0
    message: str | None = None
