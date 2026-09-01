from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import HTMLResponse, Response

from engine.app.core.db import get_db
from engine.app.core.job_manager import job_manager
from engine.app.core.repository import persist_job
from engine.app.services.tool_verification_report import build_html_report, build_json_report, build_pdf_report
from engine.app.verification.run_suite import run_verification_suite

router = APIRouter(prefix="/tool-verification", tags=["verification"])


@router.post("/run")
async def run_suite(background_tasks: BackgroundTasks) -> dict:
    job = await job_manager.create("tool_verification")
    persist_job(job.id, "tool_verification", "pending")

    async def _run() -> None:
        await job_manager.update(job.id, status="running", progress=5, message="Running verification suite")
        try:
            result = await run_verification_suite(job.id)
            await job_manager.update(job.id, status="completed", progress=100, result=result)
            persist_job(job.id, "tool_verification", "completed", progress=100, result=result)
        except Exception as exc:
            await job_manager.update(job.id, status="failed", error=str(exc))
            persist_job(job.id, "tool_verification", "failed", error=str(exc))

    background_tasks.add_task(_run)
    return {"job_id": job.id}


@router.get("/results")
def list_results() -> list[dict]:
    import json

    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, run_at, app_version, passed, results_json FROM tool_verification_runs ORDER BY run_at DESC LIMIT 20"
        ).fetchall()
    out = []
    for row in rows:
        item = dict(row)
        try:
            item["results"] = json.loads(item.pop("results_json"))
        except json.JSONDecodeError:
            item["results"] = {}
        out.append(item)
    return out


def _get_run_or_404(run_id: str) -> dict:
    with get_db() as conn:
        row = conn.execute(
            "SELECT id, run_at, app_version, passed FROM tool_verification_runs WHERE id = ?",
            (run_id,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Verification run not found")
    return dict(row)


@router.get("/results/{run_id}")
def get_result(run_id: str) -> dict:
    try:
        return build_json_report(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/results/{run_id}/report.html", response_class=HTMLResponse)
def verification_html(run_id: str) -> HTMLResponse:
    _get_run_or_404(run_id)
    try:
        return HTMLResponse(build_html_report(run_id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/results/{run_id}/report.pdf")
def verification_pdf(run_id: str) -> Response:
    _get_run_or_404(run_id)
    try:
        signed, fingerprint = build_pdf_report(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(
        content=signed,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="tool_verification_{run_id[:12]}.pdf"',
            "X-Signing-Fingerprint": fingerprint,
        },
    )
