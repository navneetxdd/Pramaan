from __future__ import annotations

import logging
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from urllib.parse import quote

import requests

from engine.app.core.config import APP_VERSION
from engine.app.core.hashing import hash_file
from engine.app.core.repository import (
    case_storage_dir,
    get_case,
    register_device_from_path,
)
from engine.app.parsers.manufacturer_detect import identify_image

logger = logging.getLogger("forensic.engine")

Vendor = Literal["hikvision", "dahua", "onvif"]


@dataclass(frozen=True)
class LogicalClip:
    remote_path: str
    filename: str
    start_time: str | None = None
    end_time: str | None = None


def _session(user: str, password: str) -> requests.Session:
    session = requests.Session()
    session.auth = (user, password)
    session.headers.update({"User-Agent": f"Pramaan-Logical-Acquire/{APP_VERSION}"})
    session.timeout = 120  # type: ignore[attr-defined]
    return session


def _hikvision_search_clips(session: requests.Session, host: str, port: int) -> list[LogicalClip]:
    search_xml = """<?xml version="1.0" encoding="UTF-8"?>
<CMSearchDescription>
  <searchID>1</searchID>
  <maxResults>8</maxResults>
  <timeSpanList><timeSpan><startTime>2020-01-01T00:00:00Z</startTime><endTime>2030-01-01T00:00:00Z</endTime></timeSpan></timeSpanList>
</CMSearchDescription>"""
    url = f"http://{host}:{port}/ISAPI/ContentMgmt/search"
    response = session.post(url, data=search_xml.encode("utf-8"), timeout=120)
    response.raise_for_status()
    root = ET.fromstring(response.text)
    clips: list[LogicalClip] = []
    for match in root.iter():
        if not match.tag.endswith("matchItem"):
            continue
        playback_uri = None
        start_time = None
        end_time = None
        for child in match:
            tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            if tag == "playbackURI" and child.text:
                playback_uri = child.text.strip()
            elif tag == "startTime" and child.text:
                start_time = child.text.strip()
            elif tag == "endTime" and child.text:
                end_time = child.text.strip()
        if playback_uri:
            name = Path(playback_uri.split("?")[0]).name or f"clip_{len(clips)}.mp4"
            clips.append(LogicalClip(remote_path=playback_uri, filename=name, start_time=start_time, end_time=end_time))
    return clips


def _hikvision_download(session: requests.Session, host: str, port: int, clip: LogicalClip) -> bytes:
    if clip.remote_path.startswith("http"):
        url = clip.remote_path
    else:
        url = f"http://{host}:{port}/ISAPI/ContentMgmt/download?playbackURI={quote(clip.remote_path, safe='')}"
    response = session.get(url, timeout=300)
    response.raise_for_status()
    return response.content


def _dahua_search_clips(session: requests.Session, host: str, port: int) -> list[LogicalClip]:
    base = f"http://{host}:{port}/cgi-bin/mediaFileFind.cgi"
    create = session.get(f"{base}?action=factory.create", timeout=60)
    create.raise_for_status()
    object_id = None
    for line in create.text.splitlines():
        if line.startswith("result="):
            object_id = line.split("=", 1)[1].strip()
            break
    if not object_id:
        raise RuntimeError("Dahua mediaFileFind did not return an object id")

    find = session.get(
        f"{base}?action=findFile&object={object_id}&condition.Channel=1&condition.StartTime=2020-01-01%2000:00:00&condition.EndTime=2030-01-01%2000:00:00",
        timeout=60,
    )
    find.raise_for_status()

    clips: list[LogicalClip] = []
    while True:
        nxt = session.get(f"{base}?action=findNextFile&object={object_id}&count=1", timeout=60)
        nxt.raise_for_status()
        if "found=0" in nxt.text:
            break
        path = None
        for line in nxt.text.splitlines():
            if line.startswith("items[0].Path="):
                path = line.split("=", 1)[1].strip()
        if not path:
            break
        clips.append(LogicalClip(remote_path=path, filename=Path(path).name or f"dahua_{len(clips)}.dav"))
    return clips


def _dahua_download(session: requests.Session, host: str, port: int, clip: LogicalClip) -> bytes:
    url = f"http://{host}:{port}/cgi-bin/RPC_Loadfile/{quote(clip.remote_path.lstrip('/'), safe='/')}"
    response = session.get(url, timeout=300)
    response.raise_for_status()
    return response.content


def _onvif_search_clips(host: str, port: int, user: str, password: str) -> list[LogicalClip]:
    try:
        from onvif import ONVIFCamera  # type: ignore
    except ImportError as exc:
        raise RuntimeError("onvif-zeep is not installed on this host") from exc

    camera = ONVIFCamera(host, port, user, password)
    recordings = camera.create_recording_service().GetRecordings()
    clips: list[LogicalClip] = []
    for index, recording in enumerate(recordings or []):
        token = getattr(recording, "RecordingToken", None) or getattr(recording, "token", None)
        if not token:
            continue
        clips.append(LogicalClip(remote_path=str(token), filename=f"onvif_recording_{index}.mp4"))
    return clips


def discover_logical_clips(
    *,
    host: str,
    port: int,
    user: str,
    password: str,
    vendor: Vendor,
) -> list[LogicalClip]:
    if vendor == "onvif":
        return _onvif_search_clips(host, port, user, password)
    session = _session(user, password)
    if vendor == "hikvision":
        return _hikvision_search_clips(session, host, port)
    return _dahua_search_clips(session, host, port)


def download_logical_clip(
    *,
    host: str,
    port: int,
    user: str,
    password: str,
    vendor: Vendor,
    clip: LogicalClip,
) -> bytes:
    if vendor == "onvif":
        raise RuntimeError("ONVIF export URI download is operator-driven in this release")
    session = _session(user, password)
    if vendor == "hikvision":
        return _hikvision_download(session, host, port, clip)
    return _dahua_download(session, host, port, clip)


async def acquire_logical_network(
    case_id: str,
    actor: str,
    *,
    host: str,
    port: int,
    user: str,
    password: str,
    vendor: Vendor,
    max_clips: int = 4,
) -> dict:
    if not get_case(case_id):
        raise ValueError("Case not found")

    clips = discover_logical_clips(host=host, port=port, user=user, password=password, vendor=vendor)
    if not clips:
        raise RuntimeError("No recordings returned by the device index")

    acquired: list[dict] = []
    storage = case_storage_dir(case_id)
    storage.mkdir(parents=True, exist_ok=True)

    for clip in clips[:max_clips]:
        blob = download_logical_clip(
            host=host,
            port=port,
            user=user,
            password=password,
            vendor=vendor,
            clip=clip,
        )
        if not blob:
            continue
        safe_name = Path(clip.filename).name or f"{uuid.uuid4().hex}.bin"
        dest = storage / f"logical_{safe_name}"
        dest.write_bytes(blob)
        md5, sha256 = hash_file(dest)
        identification = identify_image(dest)
        device = register_device_from_path(
            case_id,
            actor.strip(),
            dest,
            identification=identification,
            acquisition_method="logical_network",
            write_blocker="n/a_read_only_api",
            source_type="network_logical",
            source_identifier=f"{vendor}://{host}:{port}/{clip.remote_path}",
        )
        acquired.append(
            {
                "evidence": {
                    "id": device["id"],
                    "filename": dest.name,
                    "sha256": sha256,
                    "md5": md5,
                    "size_bytes": dest.stat().st_size,
                },
                "remote_path": clip.remote_path,
                "logical_only": True,
            }
        )

    if not acquired:
        raise RuntimeError("Device index returned clips but none could be downloaded")

    return {
        "case_id": case_id,
        "host": host,
        "vendor": vendor,
        "clips_acquired": len(acquired),
        "devices": acquired,
        "note": "Logical network acquisition — no unallocated space or deleted recovery possible.",
    }
