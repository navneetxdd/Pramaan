from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from engine.app.services.reporting import (
    build_html_report,
    build_integrity_html_report,
    build_integrity_pdf_report,
    build_integrity_report,
    build_json_report,
    build_pdf_report,
)

router = APIRouter(prefix="/cases", tags=["reports"])


def _report_error(exc: ValueError) -> HTTPException:
    status = 409 if "Custody chain broken" in str(exc) else 404
    return HTTPException(status_code=status, detail=str(exc))


@router.get("/{case_id}/report")
def report_json(case_id: str) -> dict:
    try:
        return build_json_report(case_id)
    except ValueError as exc:
        raise _report_error(exc) from exc


@router.get("/{case_id}/report.html")
def report_html(case_id: str) -> Response:
    try:
        html = build_html_report(case_id)
    except ValueError as exc:
        raise _report_error(exc) from exc
    return Response(content=html, media_type="text/html")


@router.get("/{case_id}/report.pdf")
def report_pdf(case_id: str) -> Response:
    try:
        pdf, _ = build_pdf_report(case_id)
    except ValueError as exc:
        raise _report_error(exc) from exc
    return Response(content=pdf, media_type="application/pdf")


@router.get("/{case_id}/report/integrity")
def integrity_report_json(case_id: str) -> dict:
    try:
        return build_integrity_report(case_id)
    except ValueError as exc:
        raise _report_error(exc) from exc


@router.get("/{case_id}/report/integrity.html")
def integrity_report_html(case_id: str) -> Response:
    try:
        html = build_integrity_html_report(case_id)
    except ValueError as exc:
        raise _report_error(exc) from exc
    return Response(content=html, media_type="text/html")


@router.get("/{case_id}/report/integrity.pdf")
def integrity_report_pdf(case_id: str) -> Response:
    try:
        pdf, _ = build_integrity_pdf_report(case_id)
    except ValueError as exc:
        raise _report_error(exc) from exc
    return Response(content=pdf, media_type="application/pdf")
