from pydantic import BaseModel, Field


class RecoveryRequest(BaseModel):
    actor: str = Field(min_length=2, max_length=120)
    max_scan_bytes: int | None = Field(default=None, ge=1024)


class RecoveryJobRecord(BaseModel):
    id: str
    case_id: str
    image_id: str
    status: str
    vendor: str | None
    adapter: str | None
    stats_json: str | None
    error: str | None
    started_at: str
    completed_at: str | None


class SegmentRecord(BaseModel):
    id: str
    job_id: str
    channel: int | None
    vendor: str
    offset_start: int
    offset_end: int
    frame_count: int
    confidence: float
    validation: str
    preview_path: str | None
    created_at: str
