from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

from pramaan.core import cases as case_store
from pramaan.modules.reporting.service import build_html_report, build_json_report

router = APIRouter(prefix="/api", tags=["reporting"])


@router.get("/cases/{case_id}/report")
def case_report_json(case_id: str) -> dict:
    try:
        return build_json_report(case_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/cases/{case_id}/report.html", response_class=HTMLResponse)
def case_report_html(case_id: str) -> HTMLResponse:
    try:
        return HTMLResponse(build_html_report(case_id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
