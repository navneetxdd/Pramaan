from pydantic import BaseModel


class EvidenceRecord(BaseModel):
    id: str
    case_id: str
    filename: str
    storage_path: str
    sha256: str
    size_bytes: int
    media_type: str
    acquired_at: str


class VendorHint(BaseModel):
    vendor: str
    adapter: str
    confidence: float
    markers: list[str]
