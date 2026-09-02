# Pramaan — Audit Round 4 (SIH26150)

Date: 2026-09-02 · Auditor pass: full A-to-Z, code-grounded, live-run.
Engine tested at commit `cdece3e` on `main`. Real Dahua `.dav` + mock NVR exercised end-to-end.

---

## 0. TL;DR verdict (judge framing)

| Axis | Verdict | Note |
|---|---|---|
| **Delivers on the PS?** | **Partially — the forensic core does; the "unified vendor tool" claim is thin** | Acquisition + Dahua/Hikvision parsing + timeline + custody + signed report are real and work on real data. Only Dahua has been exercised on a genuine vendor file. CP Plus/TP-Link/Godrej/Uniview/Matrix = generic carving only. |
| **Actually works, or vibecoded?** | **Works.** | 72/72 tests pass. Real 25.7 MB Dahua `.dav` → identified 0.98 → 4 segments with real 2017 RTC timestamps → MP4 export decodes clean → 19 real CV leads. No fake data, no RNG, no stubbed endpoints found. |
| **Fake / placeholder data** | **None found.** | `grep` of `src/` and `engine/app/` for TODO/FIXME/placeholder/mock/dummy/random = clean. Only 2 deliberate `NotImplementedError` guards in `dhav.py` (they reject the old invented `0x72` TLV — correct). |
| **IP camera / live CCTV view** | **DOES NOT EXIST.** | This is the single biggest gap. There is no "add camera", no RTSP display, no single/multi live view, no video wall. The only network feature is a batch recording-pull hidden inside a collapsed `<details>` in the Acquire page sidebar. ONVIF is supported in the backend but not even selectable in the UI. |
| **Novelty** | Medium. | The hash-chained custody + PAdES-signed report + BSA §63 certificate angle is genuinely strong and court-relevant. The parsers are re-implementations of known formats (FFmpeg DHAV, HIKBTREE). Live forensic preview would add real novelty. |
| **Tech stack** | Sound. | Tauri 2 + loopback FastAPI + SQLite + local ffmpeg/OpenCV. Offline, no cloud, defensible for evidence handling. |
| **Architecture** | Sound, with 2 scale bugs. | Clean router/service/parser split. But Hikvision parser loads the **entire image into RAM**, and the Dahua parser **fabricates segment boundaries at 8 MiB read-chunk edges** (see F2/F3). |
| **Design** | Inconsistent. | 6 case pages carry a dark blue **gradient hero banner** (`visily-hero-dark`) while the rest of the app is a light theme. Pick one — and per your instruction it's **light**. Ignore `DESIGN.md` and any "go dark" note entirely. |

**If a judge opened this today:** the forensic pipeline would hold up on the Dahua demo. They would immediately ask "where's the camera view / how do I connect to a live NVR" and there would be no answer. Fix that (F1) and tighten F2–F8.

---

## 1. What was verified by running it

All commands run against a fresh engine on `127.0.0.1:8787`, `FORENSIC_WORKSTATION_DATA` = throwaway dir, `PRAMAAN_ALLOW_LOGICAL_ACQUIRE=1`.

### 1.1 Test suite
```
python -m pytest engine/tests -q   →  72 passed, 1 skipped   (81 s)
```

### 1.2 Real Dahua `.dav` — full pipeline
Source: `C:\Users\navne\Downloads\pramaan-real-data\dahua_19.25.00-19.25.50-R.dav`
(25,788,416 B, magic `44 48 41 56 f0 00 00 00`, ffprobe `format_name=dhav`, h264 2592×1520 + pcm_alaw, 51 s). Copied to `validation_data/oem/`.

| Step | Result |
|---|---|
| `POST /cases/{id}/devices/acquire/oem` | evidence registered, SHA-256 `c17602dd…`, `verification_status: verified` |
| `GET /devices/{id}/identification` | `Dahua` `dahua_dhav` **confidence 0.98**, markers `DHAV×2042`, `capability_tier: experimental_parser` |
| `POST /devices/{id}/recover` (`dahua_dhav`) | job completed, **4 segments**, channel 0, `validation: dual_signature_4`, confidence 0.92 |
| `GET /devices/{id}/timeline` | real RTC: `2017-09-18T19:25:16Z → 19:25:50Z`, `timestamp_source: dhav_header_date`, `timestamp_confidence: 0.85` |
| `POST /devices/{id}/sequences/{seg}/export` | `b62119…​.mp4` → **h264 1280×750, 231 frames @ 15 fps, decodes clean** (`ffmpeg -f null -` OK) |
| `POST /devices/{id}/ai-analytics` | job completed, **19 leads** — `opencv_mog2` motion, `opencv_yunet_2023mar` face, `yolox_nano` object; confidences vary 0.05–0.62 (real, not synthetic) |

The DHAV date bit-field decode is **correct** — the 2017 timestamps match the source filename `19.25.00-19.25.50`.

### 1.3 Logical / network pull — against a local mock NVR (Digest auth, serving the real files)
| Vendor | Result |
|---|---|
| **Hikvision ISAPI** | 2 clips pulled, `searchMatchItem / mediaSegmentDescriptor / playbackURI` parsed correctly (the round-3 fix holds), Digest auth OK, downloaded bytes hash-verified |
| **Dahua CGI** | 1 clip, `factory.create → findFile → findNextFile → close → destroy`, downloaded `.dav` SHA-256 == OEM source `c17602dd…` (byte-identical) |

### 1.4 Static cleanliness
* `src/`: **zero** `TODO/FIXME/placeholder/lorem/dummy/as any/@ts-ignore/eslint-disable`.
* `engine/app/`: **zero** `random/randint/uniform/np.random`; **zero** `fake/stub/mock/hardcode`; 2 intentional `NotImplementedError` in `parsers/schemas/dhav.py:221,225`.
* OEM drop folder now accepts `.dav .mp4 .avi .264 .h264 .mkv .ts` (`services/acquisition.py:112`) — round-3 fix confirmed.

---

## 2. Confirmed defects (each with evidence)

### F1 — **No IP camera / live CCTV view. No single or multi view. Nothing.**  ⟵ headline
* `src/App.tsx` route table: `cases, evidence, jobs, acquire, device-id, recover, timeline, custody, report, ai-analytics, settings`. No `live`, no `cameras`, no `viewer`.
* `grep -rniE "rtsp|onvif|live view|webrtc|hls|video wall|camera grid"` across `src/` → only string hits inside `logical_acquisition` copy and the Acquire page's collapsed advanced form.
* Backend has `_onvif_search_clips` in `services/logical_acquisition.py:234` but the UI `logicalVendor` state (`CaseAcquirePage.tsx:109`) is typed `"hikvision" | "dahua"` — ONVIF is unreachable from the UI.
* The one network feature: `CaseAcquirePage.tsx:719` — a `<details>` element titled "Network logical pull (advanced)", collapsed by default, in a 260-px sidebar column. Host / port / user / password / vendor / "Pull clips". No preview, no channel list, no display. It downloads recordings; it never shows a camera.

**This is the fix that matters most.** Full spec in the Cursor prompt (F1).

### F2 — Dahua parser fabricates segment boundaries at the 8 MiB read-chunk edge
`engine/app/parsers/dahua_dhfs.py:18` `chunk_size = 8*1024*1024`, `:19` `overlap = 128`.
Loop reads 8 MiB, keeps only the **last 128 bytes** as `carry`. A DHAV frame whose 24-byte header lands near the end of a chunk has its body split across the boundary; `validate_dhav_frame(window, hit)` then fails (frame_len points past `window`), the frame is skipped (`:82 local_offset = hit + 4`), a gap forms, and `_merge_adjacent` (`:100 seg.offset_start <= last.offset_end`) refuses to merge across it.

**Evidence:** the real `.dav` is **one continuous 34-second recording**. Recovery returned **4 segments**, every one stamped `2017-09-18 19:25:16 → 19:25:50` (identical window), splitting at byte `8,367,453 / 16,761,444 / 25,162,147` — i.e. ≈ 8 MiB, 16 MiB, 24 MiB. The segmentation is an artefact of the reader, not the recording.

**Fix:** when a `DHAV` header is found but `hit + frame_len > len(window)`, carry the buffer **from `hit` to end** into the next iteration (grow `carry` dynamically), don't advance past it. Or parse forward using the trailer `dhav` + `seek_back u32` to walk frame-to-frame. Add a regression test on the real `.dav` asserting `len(segments) == 1` (or ≤ expected GOP-run count), all with the same channel and a single contiguous byte range.

### F3 — Hikvision parser reads the entire image into RAM
`engine/app/parsers/hikvision.py:21`:
```python
data = image_path.read_bytes() if max_bytes is None else image_path.read_bytes()[:max_bytes]
```
`read_bytes()[:max_bytes]` reads the **whole file first, then slices** — `max_bytes` saves nothing. Fine for the 4 MiB fixture; a real Hikvision NVR disk is 1–12 TB and this OOMs the engine.
**Fix:** `mmap` the file (read-only) and index off the map, or stream in windows like the Dahua adapter. At minimum honour `max_bytes` with a bounded `handle.read(max_bytes)`.

### F4 — Hikvision logical clips overwrite each other on disk (evidence loss)
`services/logical_acquisition.py:114` names each clip `Path(uri.split("?")[0]).name` — for `rtsp://…/Streaming/tracks/101?…` that is **`101`** for every clip on track 101. `:330` `dest = storage / f"logical_{safe_name}"` → both clips write to `…/logical_101`. The **second `dest.write_bytes(blob)` overwrites the first**; the DB gets two evidence rows but the disk keeps one file. In my run both clips came back as `filename: "logical_101"` with different hashes/sizes — the first blob is gone.
**Fix:** disambiguate — `logical_{track}_{index}_{starttime}.{ext}`, derive extension from the container magic or `Content-Type`, and assert `not dest.exists()` before write (raise if it does).

### F5 — `frame_count` is not a frame count; timeline over-reports playable length
* `hikvision.py:46` `frame_count=max(1, run.count(b"\x00\x00\x01\xba"))` — that is the **MPEG-PS pack count**, labelled as frames.
* Dahua path emits `frame_count=1` per DHAV frame then sums on merge — closer, but for the real `.dav` the timeline says segment 0 = **690 frames** while the exported, decodable MP4 has **231 frames** (P-frames referencing carved-away anchors are dropped on transcode).
**Fix:** rename the field to `container_units` / `pack_count`, or compute a real decodable-frame count during export and store `playable_frame_count` alongside. The Timeline/Recovery tables must show the number the examiner can actually watch.

### F6 — PlaybackDeck: whole-segment re-transcode on every scrub; fake motion in byte-offset mode
`src/components/PlaybackDeck.tsx`:
* `:148–203` every playhead change calls `resolveExport(seg.id)` → `api.exportSegment` → a fresh server-side transcode of the **entire** segment, then sets `video.currentTime`. For a real hour-long DVR segment this re-transcodes hundreds of MB per drag tick.
* `:61` `parseSegmentEnd` fallback `return start + 5000` — an arbitrary 5 s when no end timestamp.
* `:214–221` in byte-offset mode the "play" loop advances `span * 0.02` per animation frame — the scrubber moves but nothing is actually played frame-accurately. It looks like playback; it isn't.
**Fix:** add a ranged transcode endpoint (`?from_ms=&to_ms=`) or an HLS/segmented export so scrubbing fetches a window, not the whole clip. In byte-offset mode, disable the auto-advance "play" and label the control "Step segments" (it can only jump segment-to-segment without a clock).

### F7 — Face detector emits sub-30-px "faces"; Haar fallback hardcodes confidence
`engine/app/services/ai_analytics.py:335` YuNet `score` is clamped `max(0.0, min(1.0, score))` (fine) but there is **no minimum face-size filter** — my run produced a `face` lead with bbox `25×33 px` on a 2592×1520 frame at confidence 0.616. `:363` a fallback path sets `"confidence": 0.68` literally for every hit.
**Fix:** drop face candidates below ~1 % of frame height (or an absolute ~24 px) *and* below a real score threshold; delete the hardcoded `0.68` — if the fallback detector gives no score, don't emit a confidence field at all.

### F8 — "Findings" leads never reach the report
`engine/app/services/reporting.py` `build_json_report` has no `ai_findings` key — Step 5 produces investigative leads that appear on the timeline and nowhere in the JSON/HTML/PDF deliverable.
**Fix (pick one):** (a) add a clearly-fenced *"Investigative leads — examiner-selected, not verified evidence"* section to the report, populated only from leads the examiner marks `INCLUDED` (add `ai_findings.report_state`, default `EXCLUDED`, `PATCH /ai-findings/{id}`); or (b) if leads are deliberately out of scope for the report, say so in the Findings page UI ("leads are not carried into the signed report").

### F9 — `GET /devices/{id}/structure` "DHAV frame" nodes are byte-string hits, not frames
The Identification "Layout tree" listed DHAV frames at offsets `0, 368, 736, …` — 368-byte spacing is impossible for 2592×1520 I-frames. The endpoint is `bytes.find(b"DHAV")` scanning, presented as structure.
**Fix:** run the same `validate_dhav_frame` gate the recovery adapter uses before emitting a node; label unvalidated hits "DHAV byte match (unverified)".

### F10 — ONVIF hidden; logical pull mis-placed
Expose `onvif` in the vendor selector, and move the whole logical-pull form out of the Acquire sidebar `<details>` onto the new Live Devices page (F1), where you already have a connected device with enumerated channels — then the clip search gets real channel + time-range pickers instead of a bare host box.

### F11 — Kill the half-committed dark theme
`src/index.css:49–62` `.visily-hero-dark*` + `--hero-gradient` (`tokens.css:38`) render a **blue gradient hero with white text** on Acquire, Identification, Recovery-adjacent, Timeline, Findings, Custody, Report, Jobs — while every card, table and page body is the light theme (`--surface-0:#ffffff`). It reads as two apps stitched together.
**Fix (per your instruction — light, and ignore `DESIGN.md`):** replace `visily-hero-dark` with a light page header (`--surface-0` bg, `--text-primary`, a thin `--border-subtle` bottom rule, the accent kicker text in `--accent-600`). Delete `--hero-gradient`, `--hero-pattern`, `--shadow-hero`, `.visily-hero-dark*`, and the `text-white / bg-white/10` button overrides that only existed to sit on the gradient. One header component, used on all pages.

### F12 — Evidence catalog labels are filename guesses
`src/pages/case/CaseEvidenceCatalogPage.tsx:27` `inferCategory` matches `"lab"/"specimen"/"physical"` in the filename; `:35` `inferStatus` reads `acquisition_status` and ignores the stronger `verification_status`; the "Evidence type" facet (`:117`) has no `count` values while the other two facets do.
**Fix:** category from `media_type` / `acquisition_method` (real fields), status from `verification_status`, and give every facet option a real count or drop the facet.

---

## 3. Real data — already staged, do not hardcode

Present on this machine (copy the ones you want into the repo's gitignored dirs; never commit them, never inline their bytes):

| File | Where | What | Use for |
|---|---|---|---|
| `dahua_19.25.00-19.25.50-R.dav` | `~/Downloads/pramaan-real-data/` **and** `validation_data/oem/` | Genuine Dahua DHAV, 25.7 MB, h264 2592×1520 + alaw, RTC 2017-09-18 | F2 regression test, DHAV parser truth |
| `hikvision_NVR_Camera01.mp4` | same | Hikvision NVR export, 17.5 MB | live-view test source (republish over RTSP), logical-pull payload |
| `hikvision_ch01_20090329.mp4` | `~/Downloads/pramaan-real-data/` | 3.2 MB Hik channel export | second RTSP test channel |
| `meva_school_G474.avi` | same + `validation_data/oem/` | MEVA (CC-BY-4.0) 352×240 surveillance | analytics on a real static camera scene |
| `nps-2013-canon1.E01` | same + `validation_data/oem/` | Digital Corpora camera-card E01 | E01 ingest + filesystem recovery |
| `nps-2009-canon2-gen6.E01` | `validation_data/oem/` | Digital Corpora, ≥6 deleted root entries | `generic_tier2` undelete regression |
| `dfr-02-xfat.dd` | same | NIST CFReDS exFAT, 64 MB | filesystem recovery |
| `dfr-01/dfr-13 *.dd.bz2` | `~/Downloads/pramaan-real-data/` | NIST CFReDS FAT/NTFS | decompress → filesystem recovery |
| `caviar_walk1_320x240.h264` | `validation_data/fixtures/media/` | regenerated, 20 IDRs / keyint 6, decodes to 120 frames | specimen builders |

**Rule for Cursor:** datasets enter only via `scripts/validation/fetch_validation_assets.py` (URL + recorded sha256 in `validation_data/manifest.json`) or the operator drop folder. No absolute paths in code, no committed media, no `bytes` literals.

### Live-view test source (no camera hardware needed)
Add `scripts/dev/rtsp_test_source.py`:
1. Downloads `mediamtx` (single static binary, MIT licence) into `validation_data/tools/` (gitignored) if absent — URL + sha256 in the manifest, same mechanism as datasets.
2. Starts it, then `ffmpeg -re -stream_loop -1 -i <real sample> -c copy -rtsp_transport tcp -f rtsp rtsp://127.0.0.1:8554/cam1` for `hikvision_NVR_Camera01.mp4`, `cam2` for `hikvision_ch01_20090329.mp4`, `cam3` for a transcode of the `.dav`.
3. Prints the 3 `rtsp://127.0.0.1:8554/camN` URLs to paste into "Add device → Generic RTSP".

Extend `mock_dvr.py` (already used for logical-pull tests) to answer ONVIF `GetDeviceInformation` / `GetProfiles` / `GetStreamUri` returning those mediamtx URLs, so the ONVIF path is exercised too.

Graders without mediamtx get an honest "unreachable" state — that is acceptable and must not be faked.

---

## 4. Cursor prompt

Everything below the line goes to Cursor verbatim.

---

### WORKING CONTRACT — read first, non-negotiable

Prior rounds shipped code that passed CI while the feature was broken, truncated H.264 so playback showed 0 frames, and left files double-spaced. Not again.

**Hard stops.** If any PoC command in a task exits non-zero after your change: do not commit, do not open a PR, do not move on. Paste the failing command's real stdout.

**You may not** make a check pass by `@pytest.mark.skip`/`xfail`, loosening an assert, deleting a test, `try/except: pass`, `# type: ignore`, or narrowing scope. Fix the code.

**You may not** add placeholder/sample/mock/fabricated data anywhere. Every number rendered in the UI is a real value from an API response or the element is not rendered. No fake EXIF, counts, hashes, telemetry, "AES-256" chrome, blockchain/Polygon strings, CPU/RAM gauges, or vanity metrics.

**You may not** hardcode dataset bytes or absolute dataset paths. Datasets come only from `scripts/validation/fetch_validation_assets.py` (URL + sha256 in `validation_data/manifest.json`) or the operator drop folder.

**Design:** the app is **light theme**. Ignore `DESIGN.md` and any note that says go dark — the dark direction is rejected. Do not introduce dark surfaces, near-black navy, or gradient heroes.

**Per task:** (1) make the change; (2) run the task's PoC block and paste real terminal output under a `### <task> PoC` heading in the PR; (3) run `python -m pytest engine/tests -q` **and** `python -m pytest engine/tests/test_export_playable.py engine/tests/test_media_fixture.py -q` (isolation) — both green; (4) run `npx prettier --check src && npx tsc --noEmit && npm run build`; (5) only then tick the task in the Final Gate with the command you ran.

**"Functional"** means a fresh process (new temp `FORENSIC_WORKSTATION_DATA`, cleared `__pycache__`) reproduces the PoC. "Works on the second run" = not functional.

---

### F1 — Live device connection & camera view (single + multi). **Primary task.**

**Goal:** an examiner can connect to a powered-on seized NVR / IP camera over the LAN, see every channel live (grid + single focused view) exactly as vendor NVR software does, capture a hash-sealed snapshot or a bounded clip into the case, and then drive the existing recording-pull from that connected device. This is a **forensic live-preview**, bound to a case and the custody chain — not a surveillance monitoring product. Do not add PTZ control, motion alerts, or 24/7 recording.

Gate the whole feature behind the existing `PRAMAAN_ALLOW_LOGICAL_ACQUIRE=1` env (network egress is already gated by it). If unset, the page renders an explanatory disabled state.

#### F1.1 Backend — `engine/app/services/live_devices.py` + `engine/app/api/v1/live.py`

No new Python dependencies. Use the bundled `ffmpeg` (`FFMPEG_BIN`, imageio fallback) and the already-present `onvif-zeep`, `requests`, `opencv-python-headless`.

**Persistence** — new table `live_devices` (migration in `core/db.py`, bump schema version):
`id, case_id, display_name, host, port, scheme, vendor, channel_count, model_hint, serial_hint, firmware_hint, added_by, added_at`.
**Credentials are never persisted** — they travel in each request body and live only in a short-lived in-memory `dict[device_id → (user, password)]` cleared on engine restart, mirroring how `CaseAcquirePage` already treats the logical-pull password.

**Endpoints** (all under `/api/v1`, `tags=["live"]`):

| Method + path | Body / query | Returns |
|---|---|---|
| `POST /cases/{case_id}/live-devices` | `{actor, display_name, host, port, scheme, vendor ∈ {hikvision,dahua,onvif,generic_rtsp}, user, password, rtsp_url_override?}` | probes the device, enumerates channels, persists the row (no creds), appends custody `live_device_added`, returns `{id, display_name, vendor, channels:[{channel,label,main_uri,sub_uri,snapshot_uri}], device_info:{model,serial,firmware}}` |
| `GET /cases/{case_id}/live-devices` | — | persisted rows (no creds) + `credentialed: bool` |
| `POST /live-devices/{id}/reconnect` | `{user, password}` | re-probe + refresh channel list |
| `DELETE /live-devices/{id}` | `{actor}` | drop row, custody `live_device_removed` |
| `GET /live-devices/{id}/stream.mjpeg` | `?channel=&fps=6` | `StreamingResponse`, `multipart/x-mixed-replace; boundary=frame`, backed by one `ffmpeg -rtsp_transport tcp -i <sub_uri> -an -r <fps> -q:v 7 -f mpjpeg pipe:1` child; **kill the child on client disconnect** (`await request.is_disconnected()` / generator `finally`). Cap concurrent children (e.g. 16) — 503 past the cap. |
| `GET /live-devices/{id}/stream.mp4` | `?channel=&quality=main` | `StreamingResponse`, `video/mp4`, `ffmpeg -rtsp_transport tcp -i <uri> -c copy -f mp4 -movflags frag_keyframe+empty_moov+default_base_moof pipe:1`; same disconnect cleanup. Focused single-view path (video + audio). |
| `POST /live-devices/{id}/snapshot` | `{actor, channel}` | `ffmpeg -rtsp_transport tcp -i <uri> -frames:v 1 -q:v 2 <case>/live/<ts>_ch<n>.jpg`; SHA-256 it; append custody `live_snapshot_captured` with `evidence_digest = sha256`; return `{filename, sha256, taken_at_utc, channel, source_uri}` |
| `POST /live-devices/{id}/capture` | `{actor, channel, duration_s ≤ 120}` | `ffmpeg -rtsp_transport tcp -i <uri> -c copy -t <n> <case>/live/<ts>_ch<n>.mp4`; then `register_device_from_path(..., acquisition_method="live_stream_capture", source_type="network_live", write_blocker="n/a_read_only_stream", source_identifier="<vendor>://<host>/<channel>")`; custody handled by the register call; return the evidence record |

**Channel enumeration & URL construction** (`live_devices.py`):
* **Hikvision:** `main = rtsp://{u}:{p}@{host}:554/Streaming/Channels/{ch}01`, `sub = …/{ch}02`, `snapshot = http://{host}/ISAPI/Streaming/channels/{ch}01/picture` (Digest). Channel list: try `GET /ISAPI/ContentMgmt/InputProxy/channels` then fall back to probing `ch = 1..(channel_count or 1)`. Get `channel_count`, model, serial, firmware from `GET /ISAPI/System/deviceInfo`.
* **Dahua:** `main = rtsp://{u}:{p}@{host}:554/cam/realmonitor?channel={ch}&subtype=0`, `sub = …&subtype=1`, `snapshot = http://{host}/cgi-bin/snapshot.cgi?channel={ch}` (Digest). Device info + channel count from `GET /cgi-bin/magicBox.cgi?action=getSystemInfo` and `getProductDefinition`.
* **ONVIF:** `ONVIFCamera(host, port, user, password)` → `create_media_service().GetProfiles()` → per profile `GetStreamUri({'StreamSetup':{'Stream':'RTP-Unicast','Transport':{'Protocol':'RTSP'}},'ProfileToken':tok})` and `GetSnapshotUri`. `create_devicemgmt_service().GetDeviceInformation()` → model/serial/firmware.
* **generic_rtsp:** use `rtsp_url_override` verbatim as the single channel; snapshot via `-frames:v 1` off that URL.

**Probe** = a 6-second `ffmpeg -rtsp_transport tcp -i <first uri> -t 1 -f null -` (or `-frames:v 1`); if it exits non-zero, return HTTP 502 with the **real ffmpeg stderr tail** as `detail` (`auth failed`, `Connection refused`, `401`, timeout — never a generic message).

#### F1.2 Frontend — `/cases/:caseId/live`

* Route in `src/App.tsx`; sidebar item in `src/layout/ModuleSidebar.tsx` — **un-numbered** entry "Live devices" directly under "Overview", above "1. Acquisition" (connecting to a powered device precedes acquisition). Icon `Radio` or `Cctv` from lucide.
* `src/pages/case/CaseLiveDevicesPage.tsx`:
  * **Left rail** — "Connected devices" list (persisted rows) + **Add device** button → dialog with: Display name, Vendor (`Hikvision ISAPI · Dahua · ONVIF · Generic RTSP`), Host/IP, Port (auto 554 for RTSP vendors, 80 for the HTTP APIs, editable), Username, Password, and — only when Vendor = Generic RTSP — a full `rtsp://…` field. A **Test connection** button hits `POST …/live-devices` and shows the real probe result inline. An authorisation confirm ("Only connect to devices you are lawfully authorised to examine") before the POST.
  * **Main area — camera grid.** Layout selector `1 · 4 · 9 · 16` (default = smallest that fits `channel_count`). Each cell:
    * `<img src="/api/v1/live-devices/{id}/stream.mjpeg?channel={n}&fps=6">` — MJPEG needs no JS player and no CSP exception.
    * Overlay: channel label, a live dot, "on-air Xs", and cell buttons **Snapshot**, **Record 30s**, **Expand**.
    * Connection state per cell from the stream response / an `onError` on the img: `connecting → live → stalled → auth failed → unreachable`, each with the real message. No fabricated "secure" badges.
  * **Single focused view** — clicking Expand (or a cell) swaps the grid for one large `<video src="/api/v1/live-devices/{id}/stream.mp4?channel={n}&quality=main" autoplay muted playsinline controls>` with Snapshot / Record / "capture 60s" / Back-to-grid. This is the "no compromises" view: full resolution, audio available via the controls.
  * **Snapshot / Record** results → toast showing the `sha256` (short) + a link to the Evidence catalog (for captures) or Custody log (for snapshots). Never silent.
  * **"Pull recordings from this device"** button on each connected device → opens the existing logical-acquire flow **pre-filled** with that host/vendor/creds, now with a channel dropdown (from the enumerated list) and start/end datetime pickers wired into the ISAPI `CMSearchDescription` / Dahua `condition.StartTime`. This replaces the collapsed `<details>` in `CaseAcquirePage` — delete that block there and link across to `/live`.
* `src/lib/api.ts`: typed methods for every F1.1 endpoint. Stream URLs via `resolveApiUrl` helpers (return the string; the `<img>`/`<video>` do the fetching).

#### F1.3 Identification tie-in
When a device is added and `device_info` comes back, show model/serial/firmware on the device card, and if the case has a matching evidence device with no `model_hint`, offer "apply to identification".

#### F1 PoC (paste real output)
```bash
# 1. start the test RTSP source (F1.4)
python scripts/dev/rtsp_test_source.py &     # prints rtsp://127.0.0.1:8554/cam1..3
# 2. engine up with the gate
PRAMAAN_ALLOW_LOGICAL_ACQUIRE=1 python run.py &
# 3. add a generic-RTSP device
CID=$(curl -s -XPOST localhost:8787/api/v1/cases -H 'content-type: application/json' -d '{"name":"Live PoC","examiner_name":"A"}' | python -c 'import sys,json;print(json.load(sys.stdin)["id"])')
curl -s -XPOST localhost:8787/api/v1/cases/$CID/live-devices -H 'content-type: application/json' \
  -d '{"actor":"A","display_name":"Test cam","vendor":"generic_rtsp","host":"127.0.0.1","port":8554,"scheme":"rtsp","user":"","password":"","rtsp_url_override":"rtsp://127.0.0.1:8554/cam1"}'
# expect: JSON with channels[0].main_uri and a device id  →  save as DEV
# 4. snapshot -> hashed file + custody row
curl -s -XPOST localhost:8787/api/v1/live-devices/$DEV/snapshot -H 'content-type: application/json' -d '{"actor":"A","channel":1}'
# expect: {"filename":...,"sha256":"<64 hex>","taken_at_utc":...}
# 5. the mjpeg stream actually streams
curl -s --max-time 4 "localhost:8787/api/v1/live-devices/$DEV/stream.mjpeg?channel=1" | head -c 64 | xxd | head
# expect: multipart boundary + JPEG SOI (ff d8 ff)
# 6. 10s capture -> registered evidence, decodes
curl -s -XPOST localhost:8787/api/v1/live-devices/$DEV/capture -H 'content-type: application/json' -d '{"actor":"A","channel":1,"duration_s":10}'
ffmpeg -v error -i "$(ls -t <case storage>/live/*.mp4 | head -1)" -f null - && echo DECODE_OK
# 7. custody chain still verifies after snapshot+capture
curl -s localhost:8787/api/v1/cases/$CID/custody-log/status   # expect intact:true
```
Add `engine/tests/test_live_devices.py`: probe failure returns 502 with real stderr; snapshot writes a file whose sha256 matches the response and appends exactly one custody row; disconnecting the MJPEG client kills the ffmpeg child (assert no orphan process); `capture` registers an evidence row with `acquisition_method="live_stream_capture"`.

#### F1.4 — `scripts/dev/rtsp_test_source.py`
Downloads `mediamtx` (URL + sha256 in `validation_data/manifest.json`, into `validation_data/tools/`, gitignored), starts it on `:8554`, and runs one `ffmpeg -re -stream_loop -1 -i <file> -c copy -f rtsp` per source: `cam1` = `validation_data/oem/hikvision_NVR_Camera01.mp4`, `cam2` = `hikvision_ch01_20090329.mp4` (fetch into `oem/` if missing), `cam3` = a one-time transcode of `dahua_19.25.00-19.25.50-R.dav` to mp4. Prints the three URLs. No bytes committed.

---

### F2 — Dahua chunk-boundary segmentation
Fix `engine/app/parsers/dahua_dhfs.py` so a DHAV frame straddling the 8 MiB read boundary is not dropped: when `hit + parsed.frame_len > len(window)` (or `validate_dhav_frame` returns `None` for want of bytes), set `carry = window[hit:]` and `break` to the next read instead of `local_offset = hit + 4`. Keep `offset_base` bookkeeping consistent.
**PoC:** acquire `validation_data/oem/dahua_19.25.00-19.25.50-R.dav`, recover with `dahua_dhav`, assert the result is **1 contiguous segment** on channel 0 spanning ~0 → ~25.16 MB with `recorder_start_ts 2017-09-18T19:25:16` and `recorder_end_ts …19:25:50`. Add `engine/tests/test_dahua_real_dav.py::test_single_continuous_segment`. Paste the `sequences` JSON.

### F3 — Hikvision streaming read
`engine/app/parsers/hikvision.py`: replace `image_path.read_bytes()[:max_bytes]` with an `mmap` (`mmap.mmap(fd, 0, access=ACCESS_READ)`) and index off the map; honour `max_bytes` by bounding the slice. Master-block / HIKBTREE parsing stays identical.
**PoC:** `python -c` that `mmap`s `validation_data/oem/lab_hikvision_fs.img`, runs `HikvisionAdapter().scan`, prints `len(segments)` and peak RSS via `resource`/`tracemalloc` — RSS delta must be well under the file size. Existing `test_e2e_hikvision.py` still green.

### F4 — Logical clip filename collision
`services/logical_acquisition.py`: name clips `logical_{vendor}_{track_or_channel}_{index:03d}_{start_compact}.{ext}` with `ext` from container magic (`DHAV`→`.dav`, `\x00\x00\x01\xba`→`.mpg`, `ftyp`→`.mp4`, else `.bin`); `if dest.exists(): raise RuntimeError`. 
**PoC:** run the Hikvision logical pull against `mock_dvr.py` with 2 clips on track 101; assert 2 distinct files on disk, 2 evidence rows, `sha256` of each file == its row. Paste `ls -l <case storage>` and the response.

### F5 — Honest frame counts
Rename `frame_count` semantics: keep the raw value as `container_units` (packs for Hik, DHAV frames for Dahua) and, during `sequences/{id}/export`, count real decoded frames of the output and persist `playable_frame_count`. Timeline + Recovery tables render `playable_frame_count` when present, else "—". Update `src/lib/api.ts` types.
**PoC:** export segment 0 of the real `.dav`; assert stored `playable_frame_count == 231` (matches `ffprobe -count_frames`). Paste both numbers.

### F6 — Playback scrubbing
Add `GET /devices/{id}/sequences/{seg}/export?from_ms=&to_ms=` (ranged transcode; `-ss/-t`). `PlaybackDeck.tsx`: fetch a ±15 s window around the playhead, not the whole segment; cache by `(seg,fromBucket)`. In byte-offset mode (`!useTime`) remove the RAF auto-advance and relabel the button "Step ▸" (jumps to next segment). Delete the `start + 5000` guess — if there is genuinely no end, use `offset_end`.
**PoC:** in the UI (or via curl) confirm a scrub fetches a range URL and the returned MP4 is < 3 MB for the real `.dav`; `npm run build` clean. Screenshot the deck.

### F7 — Face-lead quality
`services/ai_analytics.py`: reject face candidates with `bbox.h < max(24, 0.012*frame_h)` or score `< 0.7`; delete the literal `"confidence": 0.68` (omit the field if the fallback gives no score). 
**PoC:** re-run analytics on the real `.dav`; assert no `face` finding has `bbox.h < 24`; paste the findings JSON and the before/after `face` counts.

### F8 — Leads in the report
Add `ai_findings.report_state TEXT DEFAULT 'EXCLUDED'`, `PATCH /ai-findings/{id} {report_state}`, and an "Investigative leads (examiner-selected — not verified evidence)" section in `reporting.py` (JSON+HTML+PDF) listing only `INCLUDED` rows. Findings page: a per-row Include/Exclude toggle; default excluded.
**PoC:** mark one lead INCLUDED, regenerate the JSON report, assert the section exists with exactly that row and the custody gate still fires on a broken chain (`test_report_custody_gate.py` green). Paste the report section.

### F9 — Structure endpoint accuracy
Gate `GET /devices/{id}/structure` DHAV nodes through `validate_dhav_frame`; label raw hits "DHAV byte match (unverified)" and cap their count.
**PoC:** `GET /devices/{DID}/structure` on the real `.dav` — every `oem_marker` node either validates or carries the unverified label; paste the first 10 nodes.

### F10 — ONVIF + relocate logical pull
Covered by F1.2 (ONVIF in the Add-device vendor list; logical pull moves onto `/live`). Delete the `<details>` "Network logical pull" block from `CaseAcquirePage.tsx` and leave a one-line link to `/cases/:id/live`.
**PoC:** `grep -n "Network logical pull" src/` returns nothing; Acquire page still builds; ONVIF path probed in `test_live_devices.py` against the extended `mock_dvr.py`.

### F11 — Light theme unification
Replace every `visily-hero-dark` usage with a new `<PageHeader kicker title subtitle actions>` on `--surface-0` with `--text-primary` / `--accent-600` kicker and a `--border-subtle` bottom rule. Delete `.visily-hero-dark*` from `index.css`, and `--hero-gradient` / `--hero-pattern` / `--shadow-hero` from `tokens.css`. Remove the `bg-white/10 text-white border-white/20` button overrides. No dark surfaces anywhere.
**PoC:** `grep -rn "hero-dark\|hero-gradient\|hero-pattern" src/` returns nothing; screenshot Acquire, Timeline, Report, Custody — all fully light, one consistent header; `npm run build` + `npx prettier --check src` clean.

### F12 — Real catalog labels
`CaseEvidenceCatalogPage.tsx`: `category` from `acquisition_method`/`media_type`, `status` from `verification_status`, every facet option gets a real `count` (or the facet is removed).
**PoC:** acquire the real `.dav` + an `.E01`; catalog shows category/status from API fields (not filename), every visible facet has a count. Screenshot.

---

### FINAL GATE (tick each with the command you ran)

- [ ] `python -m pytest engine/tests -q` — green (paste tail)
- [ ] `python -m pytest engine/tests/test_export_playable.py engine/tests/test_media_fixture.py -q` — green in isolation
- [ ] `python -m pytest engine/tests/test_live_devices.py engine/tests/test_dahua_real_dav.py -q` — green
- [ ] `npx prettier --check src && npx tsc --noEmit && npm run build` — clean
- [ ] Fresh-process repro of the F1 + F2 PoCs (new temp `FORENSIC_WORKSTATION_DATA`, `find . -name __pycache__ -prune -exec rm -rf {} +` first) — paste output
- [ ] `rg -n "TODO|FIXME|placeholder|sample_|mock|dummy|lorem|AES-256|blockchain|Polygon|NODE TELEMETRY" src engine --glob '!*test*'` — no new hits
- [ ] `git diff --stat` — no file where blank lines > 40 % of lines
- [ ] `grep -rn "hero-dark\|hero-gradient" src/` — empty
- [ ] `python scripts/validation/check_routes.py` — passes with the new `/live` routes in the expected set
- [ ] Screenshots: `/cases/:id/live` grid (≥4 cells streaming from the test source), single focused view, and 3 re-themed pages — attached to the PR
