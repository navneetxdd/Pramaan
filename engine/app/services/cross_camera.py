"""Cross-camera trace: correlate the same person across multiple recovered channels.

Delivers the SIH26150 requirement "correlate events across cameras" on already-recovered
footage. One batch job per case: sample each source video at a low frame rate, detect
people (YOLOX-nano ONNX, already bundled), embed each crop with a compact re-identification
model (person_reid_youtu ONNX (Tencent Youtu, via OpenCV Zoo), CPU, runs on CPU via cv2.dnn), then greedily cluster
the embeddings across every source. The result is a list of tracked identities, each with
its appearances (which camera, when) and a cross-camera movement timeline.

"Find a person" then searches those appearances against an uploaded reference photo. Two
match modes: appearance (clothing / body, person_reid_youtu, works at surveillance distance)
and face (YuNet + SFace, only usable when a face is large enough in frame).

No live streaming, no per-frame realtime inference, no PyTorch.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import tempfile
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from engine.app.core.config import FFMPEG_BIN, REID_MODEL_PATH, SFACE_MODEL_PATH, YUNET_MODEL_PATH
from engine.app.core.db import append_custody, get_db
from engine.app.core.hashing import hash_file
from engine.app.core.job_manager import job_manager
from engine.app.core.repository import case_storage_dir, get_case, list_devices, list_sequences, persist_job
from engine.app.services.ai_analytics import _detect_objects, _load_cv

logger = logging.getLogger("forensic.engine")

# --- tuning -----------------------------------------------------------------
DEFAULT_FPS = 1.0                 # frames sampled per second of source
DEFAULT_MAX_FRAMES = 400          # hard cap per source so a long recording can't run away
MIN_PERSON_CONF = 0.45           # YOLOX person score floor
MIN_BOX_PX = 28                  # ignore boxes shorter than this (far-field noise)
REID_INPUT = (128, 256)          # (w, h) fixed by the model
REID_MEAN = (0.485, 0.456, 0.406)
REID_STD = (0.229, 0.224, 0.225)
# match_sensitivity in [0,1] -> average-linkage cosine floor; see cos_threshold in run_correlation
# (0.40 + 0.35*s, so 0.40 loose .. 0.75 strict)
MIN_APPEARANCES = 3             # drop clusters with fewer detections (transient noise)
MIN_FACE_PX = 20               # SFace is unreliable below this face height on CCTV footage
FACE_MATCH_COS = 0.28         # SFace same-person cosine floor (OpenCV Zoo reference)

VIDEO_SUFFIXES = {".mp4", ".avi", ".mkv", ".mov", ".mpg", ".mpeg", ".m4v", ".dav", ".ts", ".webm"}

_reid_net = None
_reid_checked = False
_face = None                    # (detector, recognizer) once loaded
_face_checked = False


# --- models ---------------------------------------------------------------
def _load_reid():
    global _reid_net, _reid_checked
    if _reid_checked:
        return _reid_net
    _reid_checked = True
    if not REID_MODEL_PATH.exists() or not _load_cv():
        logger.warning("Re-identification model not available at %s", REID_MODEL_PATH)
        return None
    import cv2  # type: ignore

    try:
        _reid_net = cv2.dnn.readNet(str(REID_MODEL_PATH))
    except Exception:
        logger.exception("Could not load re-id model at %s", REID_MODEL_PATH)
        _reid_net = None
    return _reid_net


def _load_face():
    """Return (YuNet detector, SFace recognizer) for face matching, or None if unavailable."""
    global _face, _face_checked
    if _face_checked:
        return _face
    _face_checked = True
    if not (YUNET_MODEL_PATH.exists() and SFACE_MODEL_PATH.exists() and _load_cv()):
        return None
    import cv2  # type: ignore

    if not (hasattr(cv2, "FaceDetectorYN") and hasattr(cv2, "FaceRecognizerSF")):
        return None
    try:
        detector = cv2.FaceDetectorYN.create(str(YUNET_MODEL_PATH), "", (320, 320), 0.7, 0.3, 5000)
        recognizer = cv2.FaceRecognizerSF.create(str(SFACE_MODEL_PATH), "")
        _face = (detector, recognizer)
    except Exception:
        logger.exception("Could not load face models")
        _face = None
    return _face


def _face_embed(frame, region: dict | None = None):
    """L2-normalised 128-d SFace vector for the largest face inside `region` (or whole frame), or None."""
    import numpy as np  # type: ignore

    pair = _load_face()
    if pair is None:
        return None
    detector, recognizer = pair
    if region is not None:
        x, y = max(0, int(region["x"])), max(0, int(region["y"]))
        sub = frame[y : y + int(region["h"]), x : x + int(region["w"])]
    else:
        sub = frame
    if sub is None or sub.size == 0 or sub.shape[0] < MIN_FACE_PX or sub.shape[1] < MIN_FACE_PX:
        return None
    h, w = sub.shape[:2]
    detector.setInputSize((w, h))
    _, faces = detector.detect(sub)
    if faces is None or len(faces) == 0:
        return None
    face = max(faces, key=lambda f: float(f[2]) * float(f[3]))
    if float(face[3]) < MIN_FACE_PX:
        return None
    aligned = recognizer.alignCrop(sub, face)
    feat = recognizer.feature(aligned).reshape(-1).astype(np.float32)
    n = float(np.linalg.norm(feat))
    return feat / n if n > 1e-6 else None


def models_ready() -> dict:
    from engine.app.core.config import YOLOX_MODEL_PATH

    return {
        "detector": YOLOX_MODEL_PATH.exists(),
        "reid": REID_MODEL_PATH.exists() and _load_reid() is not None,
        "face": _load_face() is not None,
    }


def _embed(frame, box: dict):
    """Return an L2-normalised 768-d appearance vector for one person crop, or None."""
    import cv2  # type: ignore
    import numpy as np  # type: ignore

    net = _load_reid()
    if net is None:
        return None
    x, y, w, h = int(box["x"]), int(box["y"]), int(box["w"]), int(box["h"])
    x, y = max(0, x), max(0, y)
    crop = frame[y : y + h, x : x + w]
    if crop.size == 0 or crop.shape[0] < 8 or crop.shape[1] < 4:
        return None
    resized = cv2.resize(crop, REID_INPUT)
    rgb = resized[:, :, ::-1].astype(np.float32) / 255.0
    rgb = (rgb - np.array(REID_MEAN, np.float32)) / np.array(REID_STD, np.float32)
    blob = cv2.dnn.blobFromImage(rgb.astype(np.float32))
    net.setInput(blob)
    feat = net.forward().reshape(-1).astype(np.float32)
    norm = float(np.linalg.norm(feat))
    if norm < 1e-6:
        return None
    return feat / norm


# --- frame sampling -----------------------------------------------------------
def _sample(video_path: Path, fps: float, max_frames: int) -> Iterator[tuple[int, object]]:
    """Yield (offset_ms, BGR frame). Transcode to mp4 first if OpenCV can't open it."""
    if not _load_cv():
        return
    import cv2  # type: ignore

    tmp: Path | None = None
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        cap.release()
        ffmpeg = shutil.which(FFMPEG_BIN)
        if not ffmpeg:
            return
        tmp = Path(tempfile.gettempdir()) / f"ccam_{uuid.uuid4().hex}.mp4"
        cmd = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(video_path),
               "-an", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(tmp)]
        # raw h264 carves need an explicit demuxer
        if video_path.suffix.lower() in {".h264", ".264", ".bin"}:
            cmd = cmd[:6] + ["-f", "h264"] + cmd[6:]
        if subprocess.run(cmd, capture_output=True).returncode != 0 or not tmp.exists():
            tmp.unlink(missing_ok=True)
            return
        cap = cv2.VideoCapture(str(tmp))
        if not cap.isOpened():
            cap.release()
            tmp.unlink(missing_ok=True)
            return

    src_fps = float(cap.get(cv2.CAP_PROP_FPS) or 0)
    if src_fps <= 0 or src_fps > 240:
        src_fps = 25.0
    stride = max(1, round(src_fps / max(fps, 0.1)))
    idx = 0
    emitted = 0
    try:
        while emitted < max_frames:
            ok, frame = cap.read()
            if not ok:
                break
            if idx % stride == 0:
                pos = float(cap.get(cv2.CAP_PROP_POS_MSEC) or 0)
                offset_ms = int(pos if pos > 0 else (idx / src_fps) * 1000)
                yield offset_ms, frame
                emitted += 1
            idx += 1
    finally:
        cap.release()
        if tmp is not None:
            tmp.unlink(missing_ok=True)


# --- clustering ---------------------------------------------------------------
@dataclass
class _Det:
    source_key: str
    source_label: str
    source_video: str
    offset_ms: int
    box: dict
    conf: float
    emb: object  # np.ndarray (768,)
    crop: object  # np.ndarray BGR
    face_emb: object = None  # np.ndarray (128,) or None when no usable face in the crop


@dataclass
class _Tracklet:
    source_key: str
    source_label: str
    source_video: str
    dets: list = field(default_factory=list)      # list[_Det], time-ordered within one source
    mean_emb: object = None                       # np.ndarray (768,) L2-normalised
    last_ms: int = 0

    @property
    def span(self) -> tuple[int, int]:
        return self.dets[0].offset_ms, self.dets[-1].offset_ms


TRACK_LINK_COS = 0.50      # link a detection into a same-source tracklet
TRACK_GAP_MS = 4000        # ... only if within this time gap
IOU_HELP = 0.15            # spatial overlap that also allows a link even on a weaker embedding


def _iou(a: dict, b: dict) -> float:
    ax2, ay2 = a["x"] + a["w"], a["y"] + a["h"]
    bx2, by2 = b["x"] + b["w"], b["y"] + b["h"]
    ix1, iy1 = max(a["x"], b["x"]), max(a["y"], b["y"])
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
    inter = iw * ih
    union = a["w"] * a["h"] + b["w"] * b["h"] - inter
    return inter / union if union > 0 else 0.0


def _build_tracklets(dets: list) -> list:
    """Group one source's detections into short tracklets (embedding + time + space)."""
    import numpy as np  # type: ignore

    open_tr: list[_Tracklet] = []
    done: list[_Tracklet] = []
    for det in sorted(dets, key=lambda d: d.offset_ms):
        still_open = []
        for t in open_tr:
            (still_open if det.offset_ms - t.last_ms <= TRACK_GAP_MS else done).append(t)
        open_tr = still_open
        best, best_score = None, -1.0
        for t in open_tr:
            cos = float(np.dot(t.mean_emb, det.emb))
            iou = _iou(t.dets[-1].box, det.box)
            score = cos + (0.4 if iou >= IOU_HELP else 0.0)
            if score > best_score:
                best, best_score = t, score
        link_cos = float(np.dot(best.mean_emb, det.emb)) if best is not None else -1.0
        link_iou = _iou(best.dets[-1].box, det.box) if best is not None else 0.0
        if best is not None and (link_cos >= TRACK_LINK_COS or link_iou >= IOU_HELP):
            best.dets.append(det)
            best.last_ms = det.offset_ms
            m = np.mean([d.emb for d in best.dets], axis=0)
            n = float(np.linalg.norm(m))
            best.mean_emb = m / n if n > 1e-6 else best.mean_emb
        else:
            open_tr.append(_Tracklet(det.source_key, det.source_label, det.source_video,
                                     dets=[det], mean_emb=det.emb.copy(), last_ms=det.offset_ms))
    done.extend(open_tr)
    return [t for t in done if len(t.dets) >= 2]


def _agglomerate(tracklets: list, min_cos: float) -> list:
    """Average-linkage agglomerative clustering of tracklet mean embeddings (numpy only)."""
    import numpy as np  # type: ignore

    n = len(tracklets)
    if n == 0:
        return []
    embs = np.stack([t.mean_emb for t in tracklets])          # (n, 768)
    sim = embs @ embs.T                                       # cosine (unit vectors)
    groups = [[i] for i in range(n)]
    while len(groups) > 1:
        best = (-1.0, -1, -1)
        for gi in range(len(groups)):
            for gj in range(gi + 1, len(groups)):
                pair = sim[np.ix_(groups[gi], groups[gj])]
                avg = float(pair.mean())
                if avg > best[0]:
                    best = (avg, gi, gj)
        if best[0] < min_cos:
            break
        _, gi, gj = best
        groups[gi].extend(groups[gj])
        groups.pop(gj)
    return [[tracklets[k] for k in g] for g in groups]


# --- sources ----------------------------------------------------------------
def list_sources(case_id: str) -> list[dict]:
    """Resolvable correlation inputs for this case: recovered channels + registered video evidence."""
    out: list[dict] = []
    # recovered footage, grouped by channel across every device in the case
    by_channel: dict[int, list[dict]] = {}
    for dev in list_devices(case_id):
        for seq in list_sequences(dev["id"]):
            path = seq.get("output_path")
            if not path or not Path(path).exists():
                continue
            ch = int(seq.get("channel") or 0)
            by_channel.setdefault(ch, []).append(seq)
    for ch, seqs in sorted(by_channel.items()):
        seqs.sort(key=lambda s: (s.get("recorder_start_ts") or "", s.get("offset_order") or 0))
        out.append({
            "key": f"recovered:ch{ch}",
            "label": f"Recovered channel {ch}",
            "kind": "recovered_channel",
            "segments": [s["output_path"] for s in seqs],
            "clip_count": len(seqs),
        })
    # registered video evidence (live captures, network-pulled clips, directly imported video)
    for dev in list_devices(case_id):
        p = Path(dev.get("image_path") or "")
        if p.suffix.lower() in VIDEO_SUFFIXES and p.exists():
            out.append({
                "key": f"evidence:{dev['id']}",
                "label": p.name,
                "kind": "video_evidence",
                "segments": [str(p)],
                "clip_count": 1,
            })
    return out


def _resolve_sources(case_id: str, source_keys: list[str]) -> list[dict]:
    catalog = {s["key"]: s for s in list_sources(case_id)}
    picked = [catalog[k] for k in source_keys if k in catalog]
    if not picked:
        raise ValueError("None of the selected sources could be resolved for this case")
    return picked


# --- run ------------------------------------------------------------------
async def run_correlation(
    run_id: str,
    job_id: str,
    case_id: str,
    *,
    actor: str,
    source_keys: list[str],
    fps: float = DEFAULT_FPS,
    match_sensitivity: float = 0.5,
    max_frames_per_source: int = DEFAULT_MAX_FRAMES,
) -> None:
    import cv2  # type: ignore
    import numpy as np  # type: ignore

    now = datetime.now(timezone.utc).isoformat()
    params = {
        "fps": fps,
        "match_sensitivity": match_sensitivity,
        "max_frames_per_source": max_frames_per_source,
        "source_keys": source_keys,
    }
    with get_db() as conn:
        conn.execute(
            "INSERT INTO cross_camera_runs (id, case_id, status, params_json, actor, created_at) VALUES (?,?,?,?,?,?)",
            (run_id, case_id, "running", json.dumps(params), actor, now),
        )
    await job_manager.update(job_id, status="running", progress=2, message="Loading models")
    persist_job(job_id, "cross_camera", "running", case_id=case_id, progress=2, message="Loading models")

    try:
        if _load_reid() is None:
            raise RuntimeError(
                "Re-identification model unavailable. Fetch it with "
                "`python scripts/validation/fetch_validation_assets.py`."
            )
        sources = _resolve_sources(case_id, source_keys)
        # match_sensitivity in [0,1] -> average-linkage cosine floor for cross-source grouping
        s = min(max(match_sensitivity, 0.0), 1.0)
        cos_threshold = round(0.40 + 0.35 * s, 3)   # 0.40 (loose) .. 0.75 (strict)

        all_tracklets: list = []
        det_total = 0
        total = len(sources)
        for si, src in enumerate(sources):
            await job_manager.update(
                job_id, progress=5 + int(65 * si / max(total, 1)),
                message=f"Scanning {src['label']} ({si + 1}/{total})",
            )
            src_dets: list[_Det] = []
            budget = max_frames_per_source
            for video in src["segments"]:
                if budget <= 0:
                    break
                for offset_ms, frame in _sample(Path(video), fps, budget):
                    budget -= 1
                    persons = [
                        (c, b) for (lbl, c, b) in _detect_objects(frame)
                        if lbl == "person" and c >= MIN_PERSON_CONF and int(b["h"]) >= MIN_BOX_PX
                    ]
                    for conf, box in persons:
                        emb = _embed(frame, box)
                        if emb is None:
                            continue
                        x, y, w, h = int(box["x"]), int(box["y"]), int(box["w"]), int(box["h"])
                        crop = frame[max(0, y): y + h, max(0, x): x + w].copy()
                        face_emb = _face_embed(frame, box)
                        src_dets.append(_Det(src["key"], src["label"], video, offset_ms, box,
                                             float(conf), emb, crop, face_emb))
            det_total += len(src_dets)
            all_tracklets.extend(_build_tracklets(src_dets))

        await job_manager.update(
            job_id, progress=78,
            message=f"Correlating {len(all_tracklets)} tracks from {det_total} detections",
        )
        if not all_tracklets:
            raise RuntimeError("No trackable people found in the selected sources at this sample rate.")

        groups = _agglomerate(all_tracklets, cos_threshold)

        class _Ident:
            def __init__(self, tracklets):
                self.dets = [d for t in tracklets for d in t.dets]
                self.sources = {t.source_key for t in tracklets}
                m = np.mean([d.emb for d in self.dets], axis=0)
                n = float(np.linalg.norm(m))
                self.centroid = (m / n if n > 1e-6 else m).astype(np.float32)
                faces = [d.face_emb for d in self.dets if d.face_emb is not None]
                if faces:
                    fm = np.mean(faces, axis=0)
                    fn = float(np.linalg.norm(fm))
                    self.face_centroid = (fm / fn if fn > 1e-6 else fm).astype(np.float32)
                else:
                    self.face_centroid = None

        kept = [_Ident(g) for g in groups]
        kept = [c for c in kept if len(c.dets) >= MIN_APPEARANCES]
        kept.sort(key=lambda c: (len(c.sources), len(c.dets)), reverse=True)
        dets = kept and [d for c in kept for d in c.dets] or []

        thumb_dir = case_storage_dir(case_id) / "cross_camera" / run_id
        thumb_dir.mkdir(parents=True, exist_ok=True)
        identities_summary: list[dict] = []
        with get_db() as conn:
            for i, cl in enumerate(kept, start=1):
                iid = uuid.uuid4().hex
                cl.dets.sort(key=lambda d: (d.source_key, d.offset_ms))
                rep = max(cl.dets, key=lambda d: d.conf)
                rep_path = thumb_dir / f"{iid}.jpg"
                cv2.imwrite(str(rep_path), rep.crop)
                first_ms = min(d.offset_ms for d in cl.dets)
                last_ms = max(d.offset_ms for d in cl.dets)
                cams = {}
                for d in cl.dets:
                    cams.setdefault(d.source_label, {"key": d.source_key, "count": 0, "first_ms": d.offset_ms, "last_ms": d.offset_ms})
                    e = cams[d.source_label]
                    e["count"] += 1
                    e["first_ms"] = min(e["first_ms"], d.offset_ms)
                    e["last_ms"] = max(e["last_ms"], d.offset_ms)
                conn.execute(
                    """INSERT INTO cross_camera_identities
                       (id, run_id, label, camera_count, appearance_count, first_seen_ms, last_seen_ms,
                        rep_thumb_path, cameras_json, embedding, face_embedding)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (iid, run_id, f"Person {i}", len(cl.sources), len(cl.dets), first_ms, last_ms,
                     str(rep_path), json.dumps(cams), cl.centroid.astype(np.float32).tobytes(),
                     cl.face_centroid.tobytes() if cl.face_centroid is not None else None),
                )
                for d in cl.dets:
                    conn.execute(
                        """INSERT INTO cross_camera_appearances
                           (id, identity_id, run_id, source_key, source_label, source_video, offset_ms,
                            bbox_json, confidence, embedding, face_embedding)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                        (uuid.uuid4().hex, iid, run_id, d.source_key, d.source_label, d.source_video,
                         d.offset_ms, json.dumps(d.box), d.conf, d.emb.astype(np.float32).tobytes(),
                         d.face_emb.astype(np.float32).tobytes() if d.face_emb is not None else None),
                    )
                identities_summary.append({
                    "id": iid, "label": f"Person {i}", "camera_count": len(cl.sources),
                    "appearance_count": len(cl.dets),
                })

            faces_kept = sum(1 for c in kept for d in c.dets if d.face_emb is not None)
            summary = {
                "identities": len(kept),
                "cross_camera_identities": sum(1 for c in kept if len(c.sources) >= 2),
                "detections": det_total,
                "appearances_with_face": faces_kept,
                "sources": [{"key": s["key"], "label": s["label"]} for s in sources],
                "cosine_threshold": round(cos_threshold, 3),
            }
            conn.execute(
                "UPDATE cross_camera_runs SET status=?, summary_json=?, completed_at=? WHERE id=?",
                ("completed", json.dumps(summary), datetime.now(timezone.utc).isoformat(), run_id),
            )
            append_custody(
                conn, actor=actor, action="cross_camera_correlation_run",
                target_type="case", target_id=case_id,
            )

        result = {"run_id": run_id, **summary}
        await job_manager.update(job_id, status="completed", progress=100,
                                 message=f"{len(kept)} identities, {summary['cross_camera_identities']} seen on 2+ cameras",
                                 result=result)
        persist_job(job_id, "cross_camera", "completed", case_id=case_id, progress=100, result=result)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Cross-camera correlation %s failed", run_id)
        with get_db() as conn:
            conn.execute("UPDATE cross_camera_runs SET status=?, error=?, completed_at=? WHERE id=?",
                         ("failed", str(exc), datetime.now(timezone.utc).isoformat(), run_id))
        await job_manager.update(job_id, status="failed", error=str(exc))
        persist_job(job_id, "cross_camera", "failed", case_id=case_id, error=str(exc))


# --- read side ----------------------------------------------------------------
def list_runs(case_id: str) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, status, params_json, summary_json, actor, created_at, completed_at, error "
            "FROM cross_camera_runs WHERE case_id=? ORDER BY created_at DESC",
            (case_id,),
        ).fetchall()
    return [
        {
            "id": r["id"], "status": r["status"], "actor": r["actor"],
            "created_at": r["created_at"], "completed_at": r["completed_at"], "error": r["error"],
            "params": json.loads(r["params_json"] or "{}"),
            "summary": json.loads(r["summary_json"] or "{}"),
        }
        for r in rows
    ]


def get_run(run_id: str) -> dict | None:
    with get_db() as conn:
        r = conn.execute(
            "SELECT id, case_id, status, params_json, summary_json, actor, created_at, completed_at, error "
            "FROM cross_camera_runs WHERE id=?",
            (run_id,),
        ).fetchone()
        if not r:
            return None
        idents = conn.execute(
            "SELECT id, label, camera_count, appearance_count, first_seen_ms, last_seen_ms, cameras_json "
            "FROM cross_camera_identities WHERE run_id=? ORDER BY camera_count DESC, appearance_count DESC",
            (run_id,),
        ).fetchall()
    return {
        "id": r["id"], "case_id": r["case_id"], "status": r["status"], "actor": r["actor"],
        "created_at": r["created_at"], "completed_at": r["completed_at"], "error": r["error"],
        "params": json.loads(r["params_json"] or "{}"),
        "summary": json.loads(r["summary_json"] or "{}"),
        "identities": [
            {
                "id": i["id"], "label": i["label"], "camera_count": i["camera_count"],
                "appearance_count": i["appearance_count"],
                "first_seen_ms": i["first_seen_ms"], "last_seen_ms": i["last_seen_ms"],
                "cameras": json.loads(i["cameras_json"] or "{}"),
            }
            for i in idents
        ],
    }


def get_identity(identity_id: str) -> dict | None:
    with get_db() as conn:
        i = conn.execute(
            "SELECT id, run_id, label, camera_count, appearance_count, first_seen_ms, last_seen_ms, cameras_json "
            "FROM cross_camera_identities WHERE id=?",
            (identity_id,),
        ).fetchone()
        if not i:
            return None
        aps = conn.execute(
            "SELECT id, source_key, source_label, offset_ms, bbox_json, confidence "
            "FROM cross_camera_appearances WHERE identity_id=? ORDER BY source_label, offset_ms",
            (identity_id,),
        ).fetchall()
    return {
        "id": i["id"], "run_id": i["run_id"], "label": i["label"],
        "camera_count": i["camera_count"], "appearance_count": i["appearance_count"],
        "first_seen_ms": i["first_seen_ms"], "last_seen_ms": i["last_seen_ms"],
        "cameras": json.loads(i["cameras_json"] or "{}"),
        "appearances": [
            {
                "id": a["id"], "source_key": a["source_key"], "source_label": a["source_label"],
                "offset_ms": a["offset_ms"], "bbox": json.loads(a["bbox_json"]),
                "confidence": round(a["confidence"], 3),
            }
            for a in aps
        ],
    }


def _appearance_row(appearance_id: str) -> dict | None:
    with get_db() as conn:
        a = conn.execute(
            "SELECT id, identity_id, run_id, source_key, source_label, source_video, offset_ms, bbox_json, confidence "
            "FROM cross_camera_appearances WHERE id=?",
            (appearance_id,),
        ).fetchone()
    return dict(a) if a else None


def identity_thumb_path(identity_id: str) -> Path | None:
    with get_db() as conn:
        r = conn.execute("SELECT rep_thumb_path FROM cross_camera_identities WHERE id=?", (identity_id,)).fetchone()
    if r and r["rep_thumb_path"] and Path(r["rep_thumb_path"]).exists():
        return Path(r["rep_thumb_path"])
    return None


def crop_appearance(appearance_id: str, *, full_frame: bool = False) -> bytes | None:
    """Extract the person crop (or the whole frame) for one appearance, on demand."""
    import cv2  # type: ignore

    row = _appearance_row(appearance_id)
    if not row:
        return None
    for offset_ms, frame in _sample_at(Path(row["source_video"]), row["offset_ms"]):
        if full_frame:
            box = json.loads(row["bbox_json"])
            x, y, w, h = int(box["x"]), int(box["y"]), int(box["w"]), int(box["h"])
            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 200, 255), 2)
            ok, buf = cv2.imencode(".jpg", frame)
            return buf.tobytes() if ok else None
        box = json.loads(row["bbox_json"])
        x, y, w, h = int(box["x"]), int(box["y"]), int(box["w"]), int(box["h"])
        crop = frame[max(0, y): y + h, max(0, x): x + w]
        if crop.size == 0:
            return None
        ok, buf = cv2.imencode(".jpg", crop)
        return buf.tobytes() if ok else None
    return None


def _sample_at(video_path: Path, target_ms: int):
    """Yield one (offset_ms, frame) at/after target_ms, seeking directly."""
    import cv2  # type: ignore

    tmp = None
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        cap.release()
        ffmpeg = shutil.which(FFMPEG_BIN)
        if not ffmpeg:
            return
        tmp = Path(tempfile.gettempdir()) / f"ccam_seek_{uuid.uuid4().hex}.mp4"
        cmd = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(video_path),
               "-an", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(tmp)]
        if video_path.suffix.lower() in {".h264", ".264", ".bin"}:
            cmd = cmd[:6] + ["-f", "h264"] + cmd[6:]
        if subprocess.run(cmd, capture_output=True).returncode != 0 or not tmp.exists():
            (tmp.unlink(missing_ok=True) if tmp else None)
            return
        cap = cv2.VideoCapture(str(tmp))
    try:
        cap.set(cv2.CAP_PROP_POS_MSEC, max(0, target_ms))
        ok, frame = cap.read()
        if not ok:
            cap.set(cv2.CAP_PROP_POS_MSEC, 0)
            ok, frame = cap.read()
        if ok:
            yield int(cap.get(cv2.CAP_PROP_POS_MSEC) or target_ms), frame
    finally:
        cap.release()
        if tmp is not None:
            tmp.unlink(missing_ok=True)


def search_person(run_id: str, query_image: bytes, *, mode: str = "appearance", top_k: int = 40) -> dict:
    """Rank every appearance in a run against a reference photo.

    mode="appearance": clothing / body (person_reid_youtu) — reliable at surveillance distance.
    mode="face": YuNet + SFace — only matches appearances that had a large-enough face in frame.
    """
    import cv2  # type: ignore
    import numpy as np  # type: ignore

    mode = "face" if mode == "face" else "appearance"
    arr = np.frombuffer(query_image, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Could not decode the query image")

    col = "face_embedding" if mode == "face" else "embedding"
    if mode == "face":
        if _load_face() is None:
            raise RuntimeError("Face models unavailable on the engine host")
        q = _face_embed(img, None)
        if q is None:
            raise ValueError("No face found in the reference photo — try a closer, front-facing image")
        floor = FACE_MATCH_COS
    else:
        if _load_reid() is None:
            raise RuntimeError("Re-identification model unavailable")
        q = _embed(img, {"x": 0, "y": 0, "w": img.shape[1], "h": img.shape[0]})
        if q is None:
            raise RuntimeError("Could not embed the query image")
        floor = None

    with get_db() as conn:
        rows = conn.execute(
            f"SELECT a.id, a.identity_id, a.source_label, a.offset_ms, a.confidence, a.{col} AS vec, i.label "
            "FROM cross_camera_appearances a JOIN cross_camera_identities i ON i.id=a.identity_id "
            "WHERE a.run_id=?",
            (run_id,),
        ).fetchall()
    total = len(rows)
    comparable = 0
    scored = []
    for r in rows:
        if r["vec"] is None:
            continue
        emb = np.frombuffer(r["vec"], np.float32)
        if emb.size != q.size:
            continue
        comparable += 1
        sim = float(np.dot(q, emb))
        if floor is not None and sim < floor:
            continue
        scored.append((sim, r))
    scored.sort(key=lambda t: -t[0])
    matches = [
        {
            "appearance_id": r["id"], "identity_id": r["identity_id"], "identity_label": r["label"],
            "source_label": r["source_label"], "offset_ms": r["offset_ms"],
            "similarity": round(sim, 3),
        }
        for sim, r in scored[:top_k]
    ]
    return {
        "mode": mode,
        "matches": matches,
        "appearances_total": total,
        "appearances_comparable": comparable,
    }


def save_still_to_custody(case_id: str, appearance_id: str, *, actor: str) -> dict:
    jpg = crop_appearance(appearance_id, full_frame=True)
    if jpg is None:
        raise RuntimeError("Could not render the frame for this appearance")
    row = _appearance_row(appearance_id)
    out_dir = case_storage_dir(case_id) / "cross_camera" / "stills"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = out_dir / f"{ts}_{appearance_id[:8]}.jpg"
    dest.write_bytes(jpg)
    _, sha256 = hash_file(dest)
    with get_db() as conn:
        append_custody(
            conn, actor=actor, action="cross_camera_still_saved",
            target_type="case", target_id=case_id, evidence_digest=f"sha256:{sha256}",
        )
    return {"filename": dest.name, "sha256": sha256, "source_label": row["source_label"], "offset_ms": row["offset_ms"]}
