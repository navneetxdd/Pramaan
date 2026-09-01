from pydantic import BaseModel, Field


class CaseCreate(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    examiner: str = Field(min_length=2, max_length=120)
    reference: str | None = Field(default=None, max_length=120)


class CaseRecord(BaseModel):
    id: str
    title: str
    examiner: str
    reference: str | None
    status: str
    created_at: str
    updated_at: str
