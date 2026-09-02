from __future__ import annotations

from engine.app.core.repository import get_device, list_ai_findings_for_device, list_sequences


def build_timeline_for_device(device_id: str) -> dict:
    device = get_device(device_id)
    if not device:
        raise ValueError("Device not found")

    sequences = list_sequences(device_id)
    findings = list_ai_findings_for_device(device_id)
    drift = float(device.get("drift_offset_seconds") or 0)
    findings_by_sequence: dict[str, list[dict]] = {}
    for finding in findings:
        findings_by_sequence.setdefault(finding["sequence_id"], []).append(finding)
    by_channel: dict[int | None, list[dict]] = {}

    for index, seq in enumerate(sequences):
        raw_channel = seq.get("channel")
        channel_key: int | None = int(raw_channel) if raw_channel is not None else None
        start_off = int(seq.get("byte_start") or 0)
        end_off = int(seq.get("byte_end") or start_off)
        entry = {
            **seq,
            "timeline_index": index,
            "sequence_on_channel": len(by_channel.get(channel_key, [])) + 1,
            "byte_length": seq.get("byte_length") or max(end_off - start_off, 0),
            "offset_time_label": seq.get("corrected_start_ts") or seq.get("recorder_start_ts"),
            "deleted_candidate": seq["validation_level"] in {
                "honeywell_expired_index",
                "filesystem_deleted_inode",
                "slack_recovered",
                "unreferenced_carve",
                "h264_nal_tail",
            },
            "offset_start": start_off,
            "offset_end": end_off,
            "validation": seq["validation_level"],
            "ai_findings": findings_by_sequence.get(seq["id"], []),
        }
        by_channel.setdefault(channel_key, []).append(entry)

    def _channel_label(channel: int | None) -> str:
        if channel is None:
            return "Unknown channel"
        return f"Channel {channel}"

    channels = [
        {
            "channel": channel,
            "label": _channel_label(channel),
            "segment_count": len(items),
            "segments": items,
        }
        for channel, items in sorted(by_channel.items())
    ]

    return {
        "job_id": device_id,
        "case_id": device["case_id"],
        "vendor": device.get("declared_brand"),
        "adapter": device.get("detected_engine"),
        "status": "completed",
        "total_segments": len(sequences),
        "channel_count": len(channels),
        "channels": channels,
        "ai_findings": findings,
        "normalization": {
            "method": "recorder_timestamp_then_byte_offset"
            if any(seq.get("recorder_start_ts") for seq in sequences)
            else "byte_offset_order",
            "rtc_parsed": any(seq.get("recorder_start_ts") for seq in sequences),
            "drift_offset_seconds": drift,
            "note": (
                "Timeline retains explicit byte ordering per channel."
                + (
                    f" Drift calibration applied ({drift:+.1f}s)."
                    if drift
                    else " No drift correction applied."
                )
            ),
        },
    }
