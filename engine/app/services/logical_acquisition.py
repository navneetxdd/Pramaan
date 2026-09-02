from __future__ import annotations

import logging
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from urllib.parse import quote

import requests
from requests.auth import HTTPBasicAuth, HTTPDigestAuth

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
Scheme = Literal["http", "https"]
DEFAULT_TIMEOUT = 120


@dataclass(frozen=True)
class LogicalClip:
    remote_path: str
    filename: str
    start_time: str | None = None
    end_time: str | None = None
    track: str | None = None


def _extension_from_magic(blob: bytes) -> str:
    if blob.startswith(b"DHAV"):
        return ".dav"
    if blob[:4] == b"\x00\x00\x00\x01" or b"\x00\x00\x01\xba" in blob[:4096]:
        return ".mpg"
    if b"ftyp" in blob[:64]:
        return ".mp4"
    return ".bin"


def _compact_time(value: str | None) -> str:
    if not value:
        return "unknown"
    return value.replace("-", "").replace(":", "").replace("T", "").replace("Z", "")[:14]


def _logical_dest_name(vendor: str, track: str, index: int, start: str | None, blob: bytes) -> str:
    ext = _extension_from_magic(blob)
    return f"logical_{vendor}_{track}_{index:03d}_{_compact_time(start)}{ext}"


def _track_from_playback_uri(uri: str) -> str:
    if "/tracks/" in uri:
        return uri.split("/tracks/", 1)[1].split("?")[0].rstrip("/") or "0"
    if "channel=" in uri.lower():
        for part in uri.split("&"):
            if part.lower().startswith("channel="):
                return part.split("=", 1)[1]
    stem = Path(uri.split("?")[0]).stem
    return stem if stem.isdigit() else "0"


def _session(user: str, password: str) -> requests.Session:
    session = requests.Session()
    session.auth = HTTPDigestAuth(user, password)
    session.headers.update({"User-Agent": f"Pramaan-Logical-Acquire/{APP_VERSION}"})
    return session


def _request_with_auth_fallback(
    session: requests.Session,
    method: str,
    url: str,
    user: str,
    password: str,
    **kwargs,
) -> requests.Response:
    timeout = kwargs.pop("timeout", DEFAULT_TIMEOUT)
    response = session.request(method, url, timeout=timeout, **kwargs)
    if response.status_code != 401:
        return response
    www_auth = response.headers.get("WWW-Authenticate", "")
    if "digest" in www_auth.lower():
        return response
    basic_session = requests.Session()
    basic_session.auth = HTTPBasicAuth(user, password)
    basic_session.headers.update(session.headers)
    return basic_session.request(method, url, timeout=timeout, **kwargs)


def _base_url(scheme: Scheme, host: str, port: int) -> str:
    default_port = 443 if scheme == "https" else 80
    if port == default_port:
        return f"{scheme}://{host}"
    return f"{scheme}://{host}:{port}"


def _iso_or_default(start: str | None, end: str | None) -> tuple[str, str]:
    return (
        start or "2020-01-01T00:00:00Z",
        end or "2030-01-01T00:00:00Z",
    )


def _dahua_time(value: str | None, fallback: str) -> str:
    if not value:
        return fallback
    return value.replace("T", " ").replace("Z", "")[:19]


def _hikvision_search_clips(
    session: requests.Session,
    *,
    scheme: Scheme,
    host: str,
    port: int,
    user: str,
    password: str,
    channel: int | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
) -> list[LogicalClip]:
    clips: list[LogicalClip] = []
    position = 0
    track_id = (channel or 1) * 100 + 1
    span_start, span_end = _iso_or_default(start_time, end_time)
    while True:
        search_id = uuid.uuid4().hex
        search_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<CMSearchDescription>
  <searchID>{search_id}</searchID>
  <trackList><trackID>{track_id}</trackID></trackList>
  <timeSpanList><timeSpan><startTime>{span_start}</startTime><endTime>{span_end}</endTime></timeSpan></timeSpanList>
  <maxResults>100</maxResults>
  <searchResultPostion>{position}</searchResultPostion>
</CMSearchDescription>"""
        url = f"{_base_url(scheme, host, port)}/ISAPI/ContentMgmt/search"
        response = _request_with_auth_fallback(
            session,
            "POST",
            url,
            user,
            password,
            data=search_xml.encode("utf-8"),
            headers={"Content-Type": "application/xml"},
        )
        response.raise_for_status()
        root = ET.fromstring(response.text)
        status = None
        page_count = 0
        for element in root.iter():
            tag = element.tag.split("}")[-1] if "}" in element.tag else element.tag
            if tag == "responseStatusStrg" and element.text:
                status = element.text.strip().upper()
            elif tag == "playbackURI" and element.text:
                uri = element.text.strip()
                start_time = None
                if "starttime=" in uri.lower():
                    for part in uri.split("?"):
                        if "starttime=" in part.lower():
                            start_time = part.split("=", 1)[1]
                clips.append(
                    LogicalClip(
                        remote_path=uri,
                        filename=Path(uri.split("?")[0]).name or f"clip_{len(clips)}.mp4",
                        start_time=start_time,
                        track=_track_from_playback_uri(uri),
                    )
                )
                page_count += 1
        if status == "NO MATCHES" or page_count == 0:
            break
        if status != "MORE":
            break
        position += page_count
        if position > 10_000:
            break
    return clips


def _hikvision_download(
    session: requests.Session,
    *,
    scheme: Scheme,
    host: str,
    port: int,
    user: str,
    password: str,
    clip: LogicalClip,
) -> bytes:
    if clip.remote_path.startswith("http"):
        url = clip.remote_path
    else:
        url = (
            f"{_base_url(scheme, host, port)}/ISAPI/ContentMgmt/download"
            f"?playbackURI={quote(clip.remote_path, safe='')}"
        )
    response = _request_with_auth_fallback(session, "GET", url, user, password, timeout=300)
    response.raise_for_status()
    if not response.content:
        raise RuntimeError("Hikvision download returned empty body — try RTSP export on this firmware")
    return response.content


def _dahua_search_clips(
    session: requests.Session,
    *,
    scheme: Scheme,
    host: str,
    port: int,
    user: str,
    password: str,
    channel: int | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
) -> list[LogicalClip]:
    base = f"{_base_url(scheme, host, port)}/cgi-bin/mediaFileFind.cgi"
    create = _request_with_auth_fallback(session, "GET", f"{base}?action=factory.create", user, password)
    create.raise_for_status()
    object_id = None
    for line in create.text.splitlines():
        if line.startswith("result="):
            object_id = line.split("=", 1)[1].strip()
            break
    if not object_id:
        raise RuntimeError("Dahua mediaFileFind did not return an object id")

    ch = channel or 1
    start = _dahua_time(start_time, "2020-01-01 00:00:00")
    end = _dahua_time(end_time, "2030-01-01 00:00:00")
    find = _request_with_auth_fallback(
        session,
        "GET",
        (
            f"{base}?action=findFile&object={object_id}"
            f"&condition.Channel={ch}&condition.StartTime={quote(start)}"
            f"&condition.EndTime={quote(end)}&condition.Types[0]=dav"
        ),
        user,
        password,
    )
    find.raise_for_status()

    clips: list[LogicalClip] = []
    while True:
        nxt = _request_with_auth_fallback(
            session,
            "GET",
            f"{base}?action=findNextFile&object={object_id}&count=100",
            user,
            password,
        )
        nxt.raise_for_status()
        if "found=0" in nxt.text:
            break
        path = None
        for line in nxt.text.splitlines():
            if ".FilePath=" in line or line.startswith("items[0].Path="):
                path = line.split("=", 1)[1].strip()
        if not path:
            break
        clips.append(LogicalClip(remote_path=path, filename=Path(path).name or f"dahua_{len(clips)}.dav", track=str(ch)))
        if "found=0" in nxt.text or len(clips) >= 100:
            break
    _request_with_auth_fallback(session, "GET", f"{base}?action=close&object={object_id}", user, password)
    _request_with_auth_fallback(session, "GET", f"{base}?action=destroy&object={object_id}", user, password)
    return clips


def _dahua_download(
    session: requests.Session,
    *,
    scheme: Scheme,
    host: str,
    port: int,
    user: str,
    password: str,
    clip: LogicalClip,
) -> bytes:
    remote = clip.remote_path if clip.remote_path.startswith("/") else f"/{clip.remote_path}"
    url = f"{_base_url(scheme, host, port)}/cgi-bin/RPC_Loadfile{remote}"
    response = _request_with_auth_fallback(session, "GET", url, user, password, timeout=300)
    response.raise_for_status()
    if not response.content:
        raise RuntimeError("Dahua RPC_Loadfile returned empty body — firmware may require SDK/RTSP export")
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
    scheme: Scheme = "http",
    channel: int | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
) -> list[LogicalClip]:
    if vendor == "onvif":
        return _onvif_search_clips(host, port, user, password)
    session = _session(user, password)
    if vendor == "hikvision":
        return _hikvision_search_clips(
            session,
            scheme=scheme,
            host=host,
            port=port,
            user=user,
            password=password,
            channel=channel,
            start_time=start_time,
            end_time=end_time,
        )
    return _dahua_search_clips(
        session,
        scheme=scheme,
        host=host,
        port=port,
        user=user,
        password=password,
        channel=channel,
        start_time=start_time,
        end_time=end_time,
    )


def download_logical_clip(
    *,
    host: str,
    port: int,
    user: str,
    password: str,
    vendor: Vendor,
    clip: LogicalClip,
    scheme: Scheme = "http",
) -> bytes:
    if vendor == "onvif":
        raise RuntimeError("ONVIF export URI download is operator-driven in this release")
    session = _session(user, password)
    if vendor == "hikvision":
        return _hikvision_download(
            session, scheme=scheme, host=host, port=port, user=user, password=password, clip=clip
        )
    return _dahua_download(
        session, scheme=scheme, host=host, port=port, user=user, password=password, clip=clip
    )


async def acquire_logical_network(
    case_id: str,
    actor: str,
    *,
    host: str,
    port: int,
    user: str,
    password: str,
    vendor: Vendor,
    scheme: Scheme = "http",
    max_clips: int = 4,
    channel: int | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
) -> dict:
    if not get_case(case_id):
        raise ValueError("Case not found")

    clips = discover_logical_clips(
        host=host,
        port=port,
        user=user,
        password=password,
        vendor=vendor,
        scheme=scheme,
        channel=channel,
        start_time=start_time,
        end_time=end_time,
    )
    if not clips:
        raise RuntimeError("No recordings returned by the device index")

    acquired: list[dict] = []
    storage = case_storage_dir(case_id)
    storage.mkdir(parents=True, exist_ok=True)

    for index, clip in enumerate(clips[:max_clips]):
        blob = download_logical_clip(
            host=host,
            port=port,
            user=user,
            password=password,
            vendor=vendor,
            clip=clip,
            scheme=scheme,
        )
        if not blob:
            continue
        track = clip.track or "0"
        dest_name = _logical_dest_name(vendor, track, index, clip.start_time, blob)
        dest = storage / dest_name
        if dest.exists():
            raise RuntimeError(f"Logical clip would overwrite existing file: {dest_name}")
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
        "scheme": scheme,
        "vendor": vendor,
        "clips_acquired": len(acquired),
        "devices": acquired,
        "note": "Logical network acquisition — Digest auth; tested against simulators on real firmware.",
    }
