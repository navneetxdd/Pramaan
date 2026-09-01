from pydantic import BaseModel


class CustodyEventRecord(BaseModel):
    id: int
    case_id: str
    image_id: str | None
    actor: str
    action: str
    detail: str | None
    created_at: str
    prev_hash: str | None = None
    event_hash: str | None = None
