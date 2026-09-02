from __future__ import annotations

import json
import logging
import os
import subprocess
import threading
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator, Literal
from urllib.parse import quote

import requests
from requests.auth import HTTPDigestAuth

from engine.app.core.config import APP_VERSION, FFMPEG_BIN
from engine.app.core.db import append_custody, get_db, utc_now
from engine.app.core.hashing import hash_file
from engine.app.core.repository import case_storage_dir, get_case, register_device_from_path
from engine.app.parsers.manufacturer_detect import identify_image
from engine.app.services.logical_acquisition import _base_url, _request_with_auth_fallback, _session

logger = logging.getLogger("forensic.engine")

LiveVendor = Literal["hikvision", "dahua", "onvif", "generic_rtsp"]
Scheme = Literal["http", "https", "rtsp"]

_MAX_STREAMS = 16
_STREAM_LOCK = threading.Lock()
_STREAM_PROCS: dict[str, subprocess.Popen[bytes]] = {}
_CREDENTIALS: dict[str, tuple[str, str]] = {}


@dataclass(frozen=True)
class ChannelInfo:
    channel: int
    label: str
    main_uri: str
    sub_uri: str
    snapshot_uri: str | None


def _gate_enabled() -> bool:
    return os.getenv("PRAMAAN_ALLOW_LOGICAL_ACQUIRE", "").strip().lower() in {"1", "true", "yes"}


def _ffmpeg_stderr_tail(stderr: str, limit: int = 2000) -> str:
    text = (stderr or "").strip()
    return text[-limit:] if len(text) > limit else text


def _probe_rtsp(uri: str, timeout: int = 8) -> str | None:
    if not _which_ffmpeg():
        return "ffmpeg not found on PATH"
    cmd = [
        FFMPEG_BIN,
        "-hide_banner",
        "-loglevel",
        "error",
        "-rtsp_transport",
        "tcp",
        "-i",
        uri,
        "-t",
        "1",
        "-f",
        "null",
        "-",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        return "ffmpeg probe timed out"
    if result.returncode == 0:
        return None
    return _ffmpeg_stderr_tail(result.stderr or result.stdout or "ffmpeg probe failed")


def _which_ffmpeg() -> bool:
    from shutil import which

    return which(FFMPEG_BIN) is not None


def _store_credentials(device_id: str, user: str, password: str) -> None:
    _CREDENTIALS[device_id] = (user, password)


def _get_credentials(device_id: str) -> tuple[str, str]:
    return _CREDENTIALS.get(device_id, ("", ""))


def _hikvision_device_info(session: requests.Session, base: str, user: str, password: str) -> dict[str, str]:
    info: dict[str, str] = {}
    url = f"{base}/ISAPI/System/deviceInfo"
    response = _request_with_auth_fallback(session, "GET", url, user, password)
    if response.status_code != 200:
        return info
    root = ET.fromstring(response.text)
    for element in root.iter():
        tag = element.tag.split("}")[-1]
        if tag in {"model", "serialNumber", "firmwareVersion", "deviceName"} and element.text:
            key = {"serialNumber": "serial"}.get(tag, tag.replace("Version", "").lower())
            info[key] = element.text.strip()
    return info


def _hikvision_channels(session: requests.Session, base: str, user: str, password: str, host: str) -> list[ChannelInfo]:
    channels: list[ChannelInfo] = []
    url = f"{base}/ISAPI/ContentMgmt/InputProxy/channels"
    response = _request_with_auth_fallback(session, "GET", url, user, password)
    channel_ids: list[int] = []
    if response.status_code == 200:
        root = ET.fromstring(response.text)
        for element in root.iter():
            tag = element.tag.split("}")[-1]
            if tag == "id" and element.text and element.text.strip().isdigit():
                channel_ids.append(int(element.text.strip()))
    if not channel_ids:
        channel_ids = [1]
    for ch in sorted(set(channel_ids))[:16]:
        main = f"rtsp://{quote(user)}:{quote(password)}@{host}:554/Streaming/Channels/{ch}01"
        sub = f"rtsp://{quote(user)}:{quote(password)}@{host}:554/Streaming/Channels/{ch}02"
        snap = f"{base}/ISAPI/Streaming/channels/{ch}01/picture"
        channels.append(ChannelInfo(ch, f"Channel {ch}", main, sub, snap))
    return channels


def _dahua_device_info(session: requests.Session, base: str, user: str, password: str) -> dict[str, str]:
    info: dict[str, str] = {}
    for action in ("getSystemInfo", "getProductDefinition"):
        response = _request_with_auth_fallback(
            session, "GET", f"{base}/cgi-bin/magicBox.cgi?action={action}", user, password
        )
        if response.status_code != 200:
            continue
        for line in response.text.splitlines():
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip().lower()
            value = value.strip()
            if key in {"devicetype", "deviceclass", "serialnumber", "serialno", "version", "hardwareversion"}:
                info[key] = value
    return info


def _dahua_channels(host: str, user: str, password: str, channel_count: int = 1) -> list[ChannelInfo]:
    channels: list[ChannelInfo] = []
    count = max(1, min(channel_count, 16))
    for ch in range(1, count + 1):
        main = f"rtsp://{quote(user)}:{quote(password)}@{host}:554/cam/realmonitor?channel={ch}&subtype=0"
        sub = f"rtsp://{quote(user)}:{quote(password)}@{host}:554/cam/realmonitor?channel={ch}&subtype=1"
        snap = f"http://{host}/cgi-bin/snapshot.cgi?channel={ch}"
        channels.append(ChannelInfo(ch, f"Channel {ch}", main, sub, snap))
    return channels


def _onvif_channels(host: str, port: int, user: str, password: str) -> tuple[list[ChannelInfo], dict[str, str]]:
    from onvif import ONVIFCamera  # type: ignore

    camera = ONVIFCamera(host, port, user, password)
    dev = camera.create_devicemgmt_service().GetDeviceInformation()
    info = {
        "model": getattr(dev, "Model", "") or "",
        "serial": getattr(dev, "SerialNumber", "") or "",
        "firmware": getattr(dev, "FirmwareVersion", "") or "",
    }
    media = camera.create_media_service()
    profiles = media.GetProfiles() or []
    channels: list[ChannelInfo] = []
    for index, profile in enumerate(profiles[:16], start=1):
        token = profile.token
        stream = media.GetStreamUri(
            {
                "StreamSetup": {"Stream": "RTP-Unicast", "Transport": {"Protocol": "RTSP"}},
                "ProfileToken": token,
            }
        )
        snap_uri = None
        try:
            snap_uri = media.GetSnapshotUri({"ProfileToken": token}).Uri
        except Exception:
            snap_uri = None
        uri = stream.Uri
        channels.append(ChannelInfo(index, getattr(profile, "Name", None) or f"Profile {index}", uri, uri, snap_uri))
    return channels, info


def _enumerate_channels(
    *,
    vendor: LiveVendor,
    host: str,
    port: int,
    scheme: Scheme,
    user: str,
    password: str,
    rtsp_url_override: str | None,
) -> tuple[list[ChannelInfo], dict[str, str]]:
    info: dict[str, str] = {}
    if vendor == "generic_rtsp":
        uri = rtsp_url_override or f"rtsp://{host}:{port}/"
        return [ChannelInfo(1, "RTSP stream", uri, uri, None)], info
    if vendor == "onvif":
        return _onvif_channels(host, port, user, password)
    session = _session(user, password)
    base = _base_url(scheme if scheme in {"http", "https"} else "http", host, port)
    if vendor == "hikvision":
        info = _hikvision_device_info(session, base, user, password)
        return _hikvision_channels(session, base, user, password, host), info
    info = _dahua_device_info(session, base, user, password)
    count = 1
    for key, value in info.items():
        if "channel" in key and value.isdigit():
            count = max(count, int(value))
    return _dahua_channels(host, user, password, count), info


def _channel_uri(device_row: dict[str, Any], channel: int, *, quality: str = "sub") -> str:
    channels = json.loads(device_row["channels_json"])
    match = next((c for c in channels if int(c["channel"]) == int(channel)), channels[0])
    return match["main_uri"] if quality == "main" else match["sub_uri"]


def _insert_live_device(
    *,
    case_id: str,
    display_name: str,
    host: str,
    port: int,
    scheme: str,
    vendor: str,
    channels: list[ChannelInfo],
    device_info: dict[str, str],
    actor: str,
) -> dict[str, Any]:
    device_id = uuid.uuid4().hex
    now = utc_now()
    payload = [
        {
            "channel": ch.channel,
            "label": ch.label,
            "main_uri": ch.main_uri,
            "sub_uri": ch.sub_uri,
            "snapshot_uri": ch.snapshot_uri,
        }
        for ch in channels
    ]
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO live_devices (
              id, case_id, display_name, host, port, scheme, vendor,
              channel_count, model_hint, serial_hint, firmware_hint,
              channels_json, added_by, added_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                device_id,
                case_id,
                display_name,
                host,
                port,
                scheme,
                vendor,
                len(channels),
                device_info.get("model") or device_info.get("devicetype"),
                device_info.get("serial") or device_info.get("serialnumber"),
                device_info.get("firmware") or device_info.get("version"),
                json.dumps(payload),
                actor,
                now,
            ),
        )
        append_custody(
            conn,
            actor=actor,
            action="live_device_added",
            target_type="case",
            target_id=case_id,
        )
        row = conn.execute("SELECT * FROM live_devices WHERE id = ?", (device_id,)).fetchone()
    return dict(row)


def add_live_device(
    case_id: str,
    *,
    actor: str,
    display_name: str,
    host: str,
    port: int,
    scheme: Scheme,
    vendor: LiveVendor,
    user: str,
    password: str,
    rtsp_url_override: str | None = None,
) -> dict[str, Any]:
    if not _gate_enabled():
        raise PermissionError("Live device access requires PRAMAAN_ALLOW_LOGICAL_ACQUIRE=1")
    if not get_case(case_id):
        raise ValueError("Case not found")
    channels, device_info = _enumerate_channels(
        vendor=vendor,
        host=host,
        port=port,
        scheme=scheme,
        user=user,
        password=password,
        rtsp_url_override=rtsp_url_override,
    )
    if not channels:
        raise RuntimeError("No channels enumerated on device")
    probe_uri = channels[0].sub_uri or channels[0].main_uri
    probe_error = _probe_rtsp(probe_uri)
    if probe_error:
        raise RuntimeError(probe_error)
    row = _insert_live_device(
        case_id=case_id,
        display_name=display_name,
        host=host,
        port=port,
        scheme=scheme,
        vendor=vendor,
        channels=channels,
        device_info=device_info,
        actor=actor,
    )
    _store_credentials(row["id"], user, password)
    return serialize_live_device(row, credentialed=True)


def serialize_live_device(row: dict[str, Any], *, credentialed: bool) -> dict[str, Any]:
    channels = json.loads(row["channels_json"])
    return {
        "id": row["id"],
        "case_id": row["case_id"],
        "display_name": row["display_name"],
        "host": row["host"],
        "port": row["port"],
        "scheme": row["scheme"],
        "vendor": row["vendor"],
        "channel_count": row["channel_count"],
        "channels": channels,
        "device_info": {
            "model": row.get("model_hint"),
            "serial": row.get("serial_hint"),
            "firmware": row.get("firmware_hint"),
        },
        "added_by": row["added_by"],
        "added_at": row["added_at"],
        "credentialed": credentialed,
    }


def list_live_devices(case_id: str) -> list[dict[str, Any]]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM live_devices WHERE case_id = ? ORDER BY added_at",
            (case_id,),
        ).fetchall()
    return [serialize_live_device(dict(row), credentialed=row["id"] in _CREDENTIALS) for row in rows]


def get_live_device(device_id: str) -> dict[str, Any] | None:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM live_devices WHERE id = ?", (device_id,)).fetchone()
    if not row:
        return None
    return dict(row)


def reconnect_live_device(device_id: str, *, user: str, password: str) -> dict[str, Any]:
    row = get_live_device(device_id)
    if not row:
        raise ValueError("Live device not found")
    channels, device_info = _enumerate_channels(
        vendor=row["vendor"],
        host=row["host"],
        port=int(row["port"]),
        scheme=row["scheme"],
        user=user,
        password=password,
        rtsp_url_override=None,
    )
    probe_uri = channels[0].sub_uri or channels[0].main_uri
    probe_error = _probe_rtsp(probe_uri)
    if probe_error:
        raise RuntimeError(probe_error)
    payload = json.dumps(
        [
            {
                "channel": ch.channel,
                "label": ch.label,
                "main_uri": ch.main_uri,
                "sub_uri": ch.sub_uri,
                "snapshot_uri": ch.snapshot_uri,
            }
            for ch in channels
        ]
    )
    with get_db() as conn:
        conn.execute(
            """
            UPDATE live_devices
            SET channel_count = ?, model_hint = ?, serial_hint = ?, firmware_hint = ?, channels_json = ?
            WHERE id = ?
            """,
            (
                len(channels),
                device_info.get("model"),
                device_info.get("serial"),
                device_info.get("firmware"),
                payload,
                device_id,
            ),
        )
        row = conn.execute("SELECT * FROM live_devices WHERE id = ?", (device_id,)).fetchone()
    _store_credentials(device_id, user, password)
    return serialize_live_device(dict(row), credentialed=True)


def delete_live_device(device_id: str, *, actor: str) -> None:
    row = get_live_device(device_id)
    if not row:
        raise ValueError("Live device not found")
    with get_db() as conn:
        conn.execute("DELETE FROM live_devices WHERE id = ?", (device_id,))
        append_custody(
            conn,
            actor=actor,
            action="live_device_removed",
            target_type="case",
            target_id=row["case_id"],
        )
    _CREDENTIALS.pop(device_id, None)


def _stream_key(device_id: str, channel: int, kind: str) -> str:
    return f"{device_id}:{channel}:{kind}"


def _acquire_stream_slot(key: str) -> None:
    with _STREAM_LOCK:
        active = sum(1 for proc in _STREAM_PROCS.values() if proc.poll() is None)
        if active >= _MAX_STREAMS and key not in _STREAM_PROCS:
            raise RuntimeError("Maximum concurrent live streams reached")


def _register_stream(key: str, proc: subprocess.Popen[bytes]) -> None:
    with _STREAM_LOCK:
        old = _STREAM_PROCS.get(key)
        if old and old.poll() is None:
            old.kill()
        _STREAM_PROCS[key] = proc


def _release_stream(key: str) -> None:
    with _STREAM_LOCK:
        proc = _STREAM_PROCS.pop(key, None)
    if proc and proc.poll() is None:
        proc.kill()


def mjpeg_stream(device_id: str, channel: int, fps: int = 6) -> subprocess.Popen[bytes]:
    row = get_live_device(device_id)
    if not row:
        raise ValueError("Live device not found")
    uri = _channel_uri(row, channel, quality="sub")
    key = _stream_key(device_id, channel, "mjpeg")
    _acquire_stream_slot(key)
    cmd = [
        FFMPEG_BIN,
        "-hide_banner",
        "-loglevel",
        "error",
        "-rtsp_transport",
        "tcp",
        "-i",
        uri,
        "-an",
        "-r",
        str(max(1, min(fps, 15))),
        "-q:v",
        "7",
        "-f",
        "mpjpeg",
        "pipe:1",
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    _register_stream(key, proc)
    return proc


def mp4_stream(device_id: str, channel: int) -> subprocess.Popen[bytes]:
    row = get_live_device(device_id)
    if not row:
        raise ValueError("Live device not found")
    uri = _channel_uri(row, channel, quality="main")
    key = _stream_key(device_id, channel, "mp4")
    _acquire_stream_slot(key)
    cmd = [
        FFMPEG_BIN,
        "-hide_banner",
        "-loglevel",
        "error",
        "-rtsp_transport",
        "tcp",
        "-i",
        uri,
        "-c",
        "copy",
        "-f",
        "mp4",
        "-movflags",
        "frag_keyframe+empty_moov+default_base_moof",
        "pipe:1",
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    _register_stream(key, proc)
    return proc


async def iter_mjpeg(device_id: str, channel: int, fps: int, disconnect) -> AsyncIterator[bytes]:  # type: ignore[no-untyped-def]
    key = _stream_key(device_id, channel, "mjpeg")
    proc = mjpeg_stream(device_id, channel, fps=fps)
    boundary = b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
    try:
        if not proc.stdout:
            return
        buffer = b""
        while True:
            if await disconnect():
                break
            chunk = proc.stdout.read(4096)
            if not chunk:
                if proc.poll() is not None:
                    break
                continue
            buffer += chunk
            while True:
                start = buffer.find(b"\xff\xd8")
                end = buffer.find(b"\xff\xd9", start + 2)
                if start < 0 or end < 0:
                    break
                frame = buffer[start : end + 2]
                buffer = buffer[end + 2 :]
                yield boundary + frame + b"\r\n"
    finally:
        _release_stream(key)


async def iter_mp4(device_id: str, channel: int, disconnect) -> AsyncIterator[bytes]:  # type: ignore[no-untyped-def]
    key = _stream_key(device_id, channel, "mp4")
    proc = mp4_stream(device_id, channel)
    try:
        if not proc.stdout:
            return
        while True:
            if await disconnect():
                break
            chunk = proc.stdout.read(65536)
            if not chunk:
                if proc.poll() is not None:
                    break
                continue
            yield chunk
    finally:
        _release_stream(key)


def capture_snapshot(case_id: str, device_id: str, *, actor: str, channel: int) -> dict[str, Any]:
    row = get_live_device(device_id)
    if not row:
        raise ValueError("Live device not found")
    uri = _channel_uri(row, channel, quality="main")
    live_dir = case_storage_dir(case_id) / "live"
    live_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = live_dir / f"{ts}_ch{channel}.jpg"
    cmd = [
        FFMPEG_BIN,
        "-hide_banner",
        "-loglevel",
        "error",
        "-rtsp_transport",
        "tcp",
        "-i",
        uri,
        "-frames:v",
        "1",
        "-q:v",
        "2",
        str(dest),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0 or not dest.exists():
        raise RuntimeError(_ffmpeg_stderr_tail(result.stderr))
    _, sha256 = hash_file(dest)
    with get_db() as conn:
        append_custody(
            conn,
            actor=actor,
            action="live_snapshot_captured",
            target_type="case",
            target_id=case_id,
            evidence_digest=f"sha256:{sha256}",
        )
    return {
        "filename": dest.name,
        "sha256": sha256,
        "taken_at_utc": ts,
        "channel": channel,
        "source_uri": uri,
    }


def capture_clip(
    case_id: str,
    device_id: str,
    *,
    actor: str,
    channel: int,
    duration_s: int,
) -> dict[str, Any]:
    row = get_live_device(device_id)
    if not row:
        raise ValueError("Live device not found")
    duration = max(1, min(int(duration_s), 120))
    uri = _channel_uri(row, channel, quality="main")
    live_dir = case_storage_dir(case_id) / "live"
    live_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = live_dir / f"{ts}_ch{channel}.mp4"
    cmd = [
        FFMPEG_BIN,
        "-hide_banner",
        "-loglevel",
        "error",
        "-rtsp_transport",
        "tcp",
        "-i",
        uri,
        "-c",
        "copy",
        "-t",
        str(duration),
        str(dest),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0 or not dest.exists():
        raise RuntimeError(_ffmpeg_stderr_tail(result.stderr))
    identification = identify_image(dest)
    device = register_device_from_path(
        case_id,
        actor,
        dest,
        identification=identification,
        acquisition_method="live_stream_capture",
        source_type="network_live",
        write_blocker="n/a_read_only_stream",
        source_identifier=f"{row['vendor']}://{row['host']}/{channel}",
    )
    return {
        "evidence": {
            "id": device["id"],
            "filename": dest.name,
            "sha256": device["image_sha256"],
            "size_bytes": dest.stat().st_size,
        },
        "channel": channel,
        "duration_s": duration,
        "source_uri": uri,
    }
