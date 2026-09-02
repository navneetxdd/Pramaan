# Pramaan — Audit Round 5 (SIH26150)

Date: 2026-09-02 · Re-audit after Cursor commit `b1670b9` (+ `1551220` CI fix).
Method: read every changed file, ran the suite, started a **real RTSP source** (mediamtx + real Hikvision NVR sample) and drove the live-device feature end-to-end through the API and the browser UI.

---

## 0. TL;DR verdict

Cursor implemented most of F1–F12. Roughly half landed cleanly; the other half is **half-shipped in the exact ways the working contract forbade** — a fake fix, a feature that misses its own point, a not-done item, and — worst — **the headline live-camera feature ships with 100% mocked tests and two of its five paths dead on real hardware.**

| | |
|---|---|
| **Test suite** | `76 passed, 1 failed, 1 skipped`. The fail (`test_hikvision_isapi_search_finds_nested_playback_uri`, ConnectionError) is order-dependent — passes in isolation. Cursor **committed with a red suite.** |
| **Live camera (F1)** | Skeleton is real. **MJPEG grid works** — verified live in the browser against a real RTSP camera. **Snapshot works** (hash + custody verified). **Single "Expand" view: dead** — 200 OK, 0 bytes. **Clip capture: 502.** Both die on `pcm_mulaw`/`pcm_alaw` audio, which every real Hikvision/Dahua camera streams. |
| **Real-data test harness (F1.4)** | `scripts/dev/rtsp_test_source.py` **crashes on Windows before it starts** (missing default file + a `→` char the cp1252 console can't print). |
| **Fake data** | One new violation: every live grid cell shows a hardcoded green "● live" badge regardless of whether the stream is up. |
| **Light theme (F11)** | Done well — verified in browser, every page is light, no gradient hero. |
| **Forensic core** | Improved. F2 fix is real: the genuine Dahua `.dav` now recovers as **one contiguous segment** with correct RTC, instead of 4 phantom splits. |

**If a judge clicked "Expand" on a camera today, they'd see a black player that never plays, with no error.** That has to be the #1 fix.

---

## 1. F1–F12 scorecard (verified, not assumed)

### ✓ Landed and verified
| Item | Evidence |
|---|---|
| **F2** Dahua chunk-boundary segmentation | Ran the real `dahua_19.25.00-19.25.50-R.dav` through recovery: **1 segment**, bytes `0–25 786 748`, `container_units 2042`, RTC `2017-09-18T19:25:16 → 19:25:50`, `dual_signature_4`. Was 4 phantom segments last round. `test_dahua_real_dav.py::test_single_continuous_segment_on_real_dav` added. |
| **F4** Logical clip filename collision | `_logical_dest_name(vendor, track, index, start, blob)` + magic-sniffed extension + `if dest.exists(): raise`. Collision path closed. |
| **F8** Leads in the report | `ai_findings.report_state` col (default `EXCLUDED`), `PATCH /ai-findings/{id}`, `investigative_leads[]` in JSON report + a leads table in HTML/PDF. Verified: PATCH one lead → `INCLUDED` → report JSON `investigative_leads` count `1`. Custody gate still fires. |
| **F9** `/structure` DHAV accuracy | Nodes now gated through `validate_dhav_frame`; unverified hits relabelled "DHAV byte match (unverified)" and capped at 20. |
| **F11** Light theme | `.visily-hero` → `background: var(--surface-2)`, `.visily-hero-bg` → subtle `--accent-soft` radial mask; `.visily-hero-dark*` / `--hero-gradient` deleted. Browser: Timeline, Live, Overview all render fully light. `prettier --check`, `tsc --noEmit`, `npm run build` all clean. |
| **F12** Evidence catalog real fields | `inferCategory` reads `acquisition_method`, `inferStatus` reads `verification_status`, every facet option has a real `count`. |
| **F1 (partial)** MJPEG grid + snapshot | Browser screenshot: live CCTV frame rendering in the grid from `rtsp://…/cam1` → engine `mpjpeg` transcode → `<img>`. `POST /snapshot` → real JPEG, SHA-256, `live_snapshot_captured` custody row, chain stays `intact`. |

### ✗ Broken, faked, or not done

**F1-a — Single focused view (`GET /live-devices/{id}/stream.mp4`) returns 0 bytes on any camera with audio.**
`live_devices.py:505` runs `ffmpeg … -c copy -f mp4 -movflags frag_keyframe+…`. Reproduced directly:
```
[mp4] Could not find tag for codec pcm_mulaw in stream #1, codec not currently supported in container
[out#0/mp4] Could not write header (incorrect codec parameters ?): Invalid argument
→ 0 bytes
```
Hikvision streams G.711µ (`pcm_mulaw`), Dahua streams G.711a (`pcm_alaw`) — neither is legal in an MP4 with `-c copy`. In the browser, "Expand" → a black `<video>` stuck at `0:00`, HTTP `200`, empty body, no console error. **This is the "camera view, no compromises" the brief specifically asked for, and it is completely dead on real hardware.**
Fix: `-c:v copy -c:a aac -b:a 128k` (transcode only the audio; video stays copy). Verified working: same command with `-c:v copy -c:a aac` → 1 MB fragmented MP4 in 5 s. Add `-an` as a fallback if the AAC encoder is unavailable.

**F1-b — Clip capture (`POST /live-devices/{id}/capture`) 502s on the same cause.**
`live_devices.py:647` `-c copy -t N` into `.mp4`. Live test: `{"detail":"[mp4 …] Could not find tag for codec pcm_mulaw …"}`. Same fix (`-c:v copy -c:a aac`), or capture to `.mkv` (Matroska takes G.711 with `-c copy` and is still a valid evidence container).

**F1-c — Every F1 test is mocked; the feature was shipped believing it worked.**
`test_live_devices.py`: 17 `patch`/`Mock` references, **zero** real ffmpeg. `_probe_rtsp` is `patch`ed to return `None`; capture is a `subprocess.run` mock that writes `b"\x00\x00\x00\x18ftypmp42" + b"\x00"*64`. That is why F1-a/F1-b sailed through. Needs **one** real integration test (below).

**F1-d — `scripts/dev/rtsp_test_source.py` is broken on Windows (the user's platform).**
`--source` defaults to `validation_data/fixtures/caviar/logical_clip1.mp4` — **does not exist**. And line 109 `print(f"Publishing {source} → {publish_url}")` — the `→` throws `UnicodeEncodeError: 'charmap' codec can't encode character '→'` on the cp1252 console **before ffmpeg is launched**. So the harness never publishes anything. (mediamtx itself downloads and runs fine — I confirmed by publishing manually.)

**F1-e — The grid only ever shows ONE device.**
`CaseLiveDevicesPage.tsx:65` `activeDevice = devices.find(…) ?? devices[0]`; the grid maps `activeDevice.channels`. Connect three separate IP cameras (the normal case the brief describes — "how the ip can be given … camera displayed") and you still see only one at a time. A real NVR video-wall tiles **all** connected cameras. The current grid is "one multi-channel NVR" only.

**F1-f — Fake "live" status on every cell.**
`CaseLiveDevicesPage.tsx:284` — `<Radio className="h-3 w-3 text-emerald-400" /> live` is hardcoded on every tile. No `onError` on the `<img>`, no probe. If the stream 404s or ffmpeg dies, the tile shows a broken image and still says "● live". This is the one "no fake data" breach in the new code. Needs real per-cell state (`connecting / live / stalled / auth failed / unreachable`) driven by `<img onError>` + an optional `HEAD` on the stream URL.

**F1-g — "Pull recordings from this device" is a dead link.**
`CaseLiveDevicesPage.tsx:340` → `to={`/cases/${caseId}/live?pull=${activeDevice.id}`}`. Nothing in the page reads `?pull=`. Clicking it navigates to the same page and does nothing.

**F3 — Hikvision "mmap" is a fake fix; still loads the whole file into RAM.**
`hikvision.py`: `with mmap.mmap(handle.fileno(), view_len, ACCESS_READ) as data: return self._scan_mapped(bytes(data))`. `bytes(data)` **copies the entire mapping into a `bytes` object** — a 12 TB disk still allocates 12 TB. `_scan_mapped(data: bytes)` never touches the map. The prompt said "index off the map." Operate on the `mmap` object directly (it supports `[a:b]` and `.find()`), or read bounded windows.

**F6 — Ranged playback export is implemented but 28.6 s for a 15 s window — the deck is now permanently stuck on "Exporting…".**
`devices.py:448` `cmd.extend(["-ss", f"{from_ms/1000:.3f}", "-t", …])` — `-ss` is **after** `-i`, so ffmpeg decodes from byte 0, and the segment is re-encoded, not stream-copied. Live measurement: `POST …/export?from_ms=0&to_ms=15000` → **28.609 s**. In the browser the PlaybackDeck sat on "Exporting…" indefinitely and fired the request twice. The point of F6 was fast scrubbing; this is slower than useless.
Fix: `-ss` **before** `-i` (input seek, near-instant) + `-c copy` (no re-encode) + snap `from_ms` to the previous keyframe; target < 2 s for a 30 s window. Or pre-cut GOP-aligned chunks once at recovery time and serve them static.

**F7 — Faces fixed; motion is now 91 % of findings and mostly noise.**
Face filter works: re-ran analytics on the real `.dav` — the 25 px face is gone, now 1 face `h=112 @ 0.81`. But of **46 findings, 42 are `motion`** with min confidence **0.042**. On a 34-second clip that's ~1.2 motion pings/second — the Findings page and the timeline "MOTION / AI FINDINGS" track (screenshotted: a solid wall of 46 ticks) are unusable. Raise the motion floor (drop `< 0.35`, or keep only the top N per sequence, or merge contiguous motion into one span).

**F10 — Logical pull was NOT relocated.**
`CaseAcquirePage.tsx` still carries the entire logical-acquire block: `logicalHost/logicalPort/logicalUser/logicalPassword/logicalVendor/logicalScheme` state, the confirm dialog, the form, and `logicalVendor` still typed `"hikvision" | "dahua"` (no ONVIF). The Live page's replacement is the dead `?pull=` link (F1-g). Net result: logical pull is in neither place properly.

**F5 — half.** `container_units` and `playable_frame_count` were added and verified (exported segment: `playable_frame_count 726` == `ffprobe -count_frames`). But the old `frame_count` field is still emitted alongside, still equal to the raw `2042`. Pick one; the UI should show `playable_frame_count`.

**Test isolation.** `engine/tests/test_socket_guard.py::block_outbound_sockets()` monkeypatches `socket.create_connection` process-wide with **no teardown**. Under `pytest-randomly` it intermittently strands the ISAPI mock-server test with `ConnectionError`. Wrap it in an autouse fixture that restores the original, or `monkeypatch`-scope it.

---

## 2. Real data — staged and confirmed working

The live-preview path now has a **working real RTSP source** on this machine (I ran it):

```bash
# mediamtx already downloaded to .localdata/dev/mediamtx/mediamtx.exe by the (crashing) harness
.localdata/dev/mediamtx/mediamtx.exe <config.yml>   # config: rtspAddress :8554, paths cam1/cam2 source: publisher
ffmpeg -re -stream_loop -1 -i validation_data/oem/hikvision_NVR_Camera01.mp4 -c copy -f rtsp -rtsp_transport tcp rtsp://127.0.0.1:8554/cam1
ffmpeg -re -stream_loop -1 -i validation_data/oem/hikvision_ch01_20090329.mp4 -c copy -f rtsp -rtsp_transport tcp rtsp://127.0.0.1:8554/cam2
```
- `validation_data/oem/hikvision_NVR_Camera01.mp4` — 17.5 MB, **h264 1600×1200 + pcm_mulaw** (exactly the codec combo that breaks F1-a/b — use it in the integration test).
- `validation_data/oem/hikvision_ch01_20090329.mp4` — 3.2 MB, second channel.
- `validation_data/oem/dahua_19.25.00-19.25.50-R.dav` — real Dahua, F2 regression fixture.
- `validation_data/oem/meva_school_G474.avi`, `nps-2013-canon1.E01`, `nps-2009-canon2-gen6.E01`, `dfr-02-xfat.dd` — recovery/analytics corpora.

Everything is under `validation_data/oem/` (gitignored). No bytes committed, no absolute paths in code.

---

## 3. Cursor prompt — Round 5

Everything below the line goes to Cursor verbatim.

---

### WORKING CONTRACT — this is the third time. Read it.

Round 3 shipped an order-dependent test. Round 4 shipped: a failing test committed to main; a "mmap" fix that still loads the whole file; a ranged-export that takes 28 s; a live-camera feature whose tests are 100 % mocked and whose single-view + capture are dead on real hardware; and an F-item (F10) simply not done.

**Rules, non-negotiable:**
1. **No mocked test counts as proof of a feature that shells out.** Every task that runs `ffmpeg`/`subprocess` needs at least one test that actually runs it against real input. If you `patch` `subprocess`, `_probe_rtsp`, `ffmpeg`, or a network call, that test does **not** satisfy the task.
2. **Run the PoC block. Paste the real terminal output** (not "it should work") under `### <task> PoC` in the PR. If it exits non-zero or is empty, the task is not done — do not commit, do not move on.
3. **Do not commit if `python -m pytest engine/tests -q` is red.** The Round 4 fail is a real bug (task G7), not "flaky — ignore".
4. No placeholder/fake/hardcoded UI state. A status indicator must reflect real state.
5. No `bytes(mmap)`, no `read_bytes()[:n]`, no "looks like streaming".
6. Light theme only. Do not touch `DESIGN.md`. Do not reintroduce dark surfaces or gradient heroes.
7. Per task: change → real PoC output pasted → `pytest engine/tests -q` green → `npx prettier --check src && npx tsc --noEmit && npm run build` clean → then tick it.

---

### G1 — Live single-view + capture must survive real camera audio  *(highest priority)*

`engine/app/services/live_devices.py`:
* `mp4_stream()` (~line 505): change `-c copy` → `-c:v copy -c:a aac -b:a 128k`. Keep `-movflags frag_keyframe+empty_moov+default_base_moof`.
* `capture_clip()` (~line 647): change `-c copy` → `-c:v copy -c:a aac -b:a 128k`. Keep `-t <duration>`.
* Both: if the process exits non-zero **and** stderr contains `aac` or `Audio encoder`, retry once with `-an` (video-only) and set a `audio: "dropped"` field on the response / a log line. Never return an empty 200 — if the retry also fails, raise so the API returns 502 with the real stderr tail.
* `capture_snapshot()` already uses `-frames:v 1` — leave it, but confirm it uses `quality="main"` (it does).

**PoC (must use a real RTSP source with pcm_mulaw audio):**
```bash
# terminal 1 — real RTSP source (see G6 for the fixed harness; until then, manual:)
.localdata/dev/mediamtx/mediamtx.exe scripts/dev/mediamtx.yml &
ffmpeg -re -stream_loop -1 -i validation_data/oem/hikvision_NVR_Camera01.mp4 -c copy -f rtsp -rtsp_transport tcp rtsp://127.0.0.1:8554/cam1 &
# terminal 2
PRAMAAN_ALLOW_LOGICAL_ACQUIRE=1 python run.py &
CID=$(curl -s -XPOST localhost:8787/api/v1/cases -H content-type:application/json -d '{"name":"G1","examiner_name":"A"}' | python -c 'import sys,json;print(json.load(sys.stdin)["id"])')
DEV=$(curl -s -XPOST localhost:8787/api/v1/cases/$CID/live-devices -H content-type:application/json -d '{"actor":"A","display_name":"c1","vendor":"generic_rtsp","host":"127.0.0.1","port":8554,"scheme":"rtsp","user":"","password":"","rtsp_url_override":"rtsp://127.0.0.1:8554/cam1"}' | python -c 'import sys,json;print(json.load(sys.stdin)["id"])')
# single view must now be non-empty AND have a moov
curl -s --max-time 8 "localhost:8787/api/v1/live-devices/$DEV/stream.mp4?channel=1" -o /tmp/live.mp4; ls -l /tmp/live.mp4
ffprobe -v error -show_entries format=format_name -of default=nw=1 /tmp/live.mp4        # expect: mov,mp4,...
# capture must register decodable evidence
curl -s -XPOST "localhost:8787/api/v1/live-devices/$DEV/capture" -H content-type:application/json -d '{"actor":"A","channel":1,"duration_s":8}'
ffmpeg -v error -i "<case storage>/live/<the .mp4>" -f null - && echo DECODE_OK
```
**Test:** `engine/tests/test_live_devices_integration.py` — marked `@pytest.mark.integration`, skipped if `ffmpeg`/mediamtx absent, otherwise: start an ffmpeg RTSP push of a **generated** stream *with* pcm_mulaw audio (`ffmpeg -re -f lavfi -i testsrc2=size=320x240:rate=10 -f lavfi -i sine=frequency=800 -c:v libx264 -c:a pcm_mulaw -f rtsp rtsp://127.0.0.1:8554/t`), then assert: `stream.mjpeg` yields ≥ 2 JPEG SOIs; `stream.mp4` yields bytes containing `moov`/`ftyp`; `capture` produces a file `ffprobe` reads as h264. No `patch` on ffmpeg/subprocess in this file.

### G2 — One real (non-mocked) live-devices test is mandatory
Keep the existing mocked unit tests, but they no longer count as F1 proof. G1's integration test is the gate. Add to CI a job that installs ffmpeg (already done for E1) and runs `pytest -m integration engine/tests/test_live_devices_integration.py`.

### G3 — Fix `scripts/dev/rtsp_test_source.py` (Windows-first)
* Default `--source` → `validation_data/oem/hikvision_NVR_Camera01.mp4` (exists). If missing, print a clear "fetch it into validation_data/oem/ first" and exit 1.
* Remove every non-ASCII char from `print()` (`→` → `->`), or `sys.stdout.reconfigure(encoding="utf-8")` at top.
* Publish **three** paths in parallel (`cam1` = hikvision_NVR_Camera01.mp4, `cam2` = hikvision_ch01_20090329.mp4, `cam3` = a one-time `ffmpeg -i dahua_…dav -c:v copy -c:a aac cam3.mp4` transcode), each its own `ffmpeg -re -stream_loop -1` child; write the mediamtx config to `scripts/dev/mediamtx.yml` (committed) not a tempfile.
* On Ctrl-C, terminate every child.
**PoC:** `python scripts/dev/rtsp_test_source.py` on Windows → prints 3 `rtsp://127.0.0.1:8554/camN` lines and stays up; `ffprobe rtsp://127.0.0.1:8554/cam1` succeeds. Paste it.

### G4 — Grid tiles ALL connected devices, not one
`CaseLiveDevicesPage.tsx`: the grid source is the flat list `devices.flatMap(d => d.channels.map(c => ({device: d, channel: c})))`, sliced to `gridSize`. Each tile streams `api.liveMjpegUrl(deviceId, channel)` for its own device. The left rail still selects a device to **focus** (single view), but the grid is the whole wall. Label each tile `"<device.display_name> · <channel.label>"`.
**PoC:** connect 2 generic_rtsp devices (cam1, cam2); screenshot the 4-grid showing both feeds live simultaneously. Attach.

### G5 — Real per-tile connection state (kill the fake "live")
Each tile tracks `state: "connecting" | "live" | "error"`:
* `onLoad` of the `<img>` → `live`; `onError` → `error`.
* While `connecting`, show a spinner, not a green dot.
* On `error`, show "stream unavailable" + a Retry that re-mounts the `<img>` with a cache-busting `?t=`.
Remove the hardcoded `<Radio className="text-emerald-400"/> live`. The dot is green **only** in `live` state.
**PoC:** point a device at `rtsp://127.0.0.1:8554/nonexistent`; screenshot the tile showing the error state (not "● live").

### G6 — Ranged export must be fast (fix F6 properly)
`engine/app/api/v1/devices.py` ranged branch: put `-ss` **before** `-i`, snap `from_ms` down to the previous keyframe, and use `-c copy` (no `-c:v libx264`):
```
ffmpeg -hide_banner -ss <from_s> -i <segment> -t <dur_s> -c copy -movflags +faststart <out.mp4>
```
If `-c copy` produces an unplayable head (no leading keyframe), fall back to `-c:v libx264 -preset ultrafast -crf 28` for that one window only.
Target: **< 3 s** for a 30 s window on `dahua_19.25.00-19.25.50-R.dav`. Also de-dupe the double request in `PlaybackDeck.tsx` (the effect fires twice — guard with a ref or key on `(seg, fromBucket)`).
**PoC:** `time curl -s -XPOST "localhost:8787/api/v1/devices/$DID/sequences/$SEG/export?from_ms=0&to_ms=30000" -d '{"actor":"A"}'` → paste the `real` time (must be < 3 s) and `ffprobe` of the output.

### G7 — Fix the failing test (do not ship red)
`engine/tests/test_socket_guard.py`: `block_outbound_sockets()` has no teardown, so `test_hikvision_isapi_search_finds_nested_playback_uri` fails under randomized full-suite order. Wrap the socket patch in an `@pytest.fixture` that saves and restores `socket.socket.connect` / `socket.create_connection`, or apply it via `monkeypatch` so pytest unwinds it.
**PoC:** `python -m pytest engine/tests -q -p randomly --randomly-seed=last` green ×3 runs with different seeds. Paste all three summary lines.

### G8 — Real mmap for Hikvision (fix F3 properly)
`engine/app/parsers/hikvision.py`: `_scan_mapped` must accept the `mmap.mmap` object and operate on it directly — `data[a:b]` and `data.find(b"…")` both work on `mmap`. Delete `bytes(data)`. If a helper genuinely needs `bytes`, slice only the bounded region it needs (`bytes(data[off:off+SIZE])`), never the whole map.
**PoC:** a script that `mmap`s a synthetic 2 GB sparse Hikvision image (`truncate -s 2G` + real master block + one HIKBTREE entry) and runs `HikvisionAdapter().scan`; print `tracemalloc` peak — must be « 2 GB (e.g. < 200 MB). Paste it.

### G9 — Cut the motion noise (finish F7)
`engine/app/services/ai_analytics.py`: for `motion` findings, either (a) drop confidence `< 0.35`, or (b) keep only the top 8 per sequence by confidence, or (c) merge motion events < 2 s apart into one span with `start_ms`/`end_ms`. Pick one; document it in the finding's `bbox_json` as `"filter": "…"`.
**PoC:** re-run analytics on `dahua_19.25.00-19.25.50-R.dav`; assert `motion` findings ≤ 10 and none below the floor. Paste the `Counter(finding_type)` before/after.

### G10 — Actually relocate the logical pull (finish F10)
* Delete the logical-acquire block from `CaseAcquirePage.tsx` (state, dialog, form, `handleLogicalAcquire`). Leave one line: "Pulling recordings from a powered device? → Live devices".
* `CaseLiveDevicesPage.tsx`: read `?pull=<deviceId>` via `useSearchParams`; when set, render a real panel below the grid — channel `<select>` (from `activeDevice.channels`), start/end `datetime-local` inputs, "Pull recordings" button → `api.acquireLogical(caseId, {host, vendor, user/pass from the credentialed session, scheme, channel, start, end, max_clips})`. Wire `channel`/`start`/`end` into the ISAPI `CMSearchDescription` (`trackID = channel*100+1`, `timeSpan`) and Dahua `condition.Channel`/`StartTime`/`EndTime` in `logical_acquisition.py`.
* Expose `onvif` in the vendor dropdown there too.
**PoC:** `grep -n "logicalHost\|handleLogicalAcquire" src/pages/case/CaseAcquirePage.tsx` → empty. Then a curl pull with an explicit channel + time range against `mock_dvr.py` returns only clips in range. Paste both.

### G11 — Collapse `frame_count` / `playable_frame_count` (finish F5)
Stop emitting the raw `frame_count` in the sequences/timeline API — keep `container_units` (raw) and `playable_frame_count` (nullable, filled on export). `src/lib/api.ts` + the Recovery/Timeline tables render `playable_frame_count ?? "—"`. Grep the frontend for `frame_count` and update.
**PoC:** `curl …/sequences | python -m json.tool` shows `container_units` + `playable_frame_count`, no `frame_count`. Screenshot the Recovery table.

### FINAL GATE
- [ ] `python -m pytest engine/tests -q` — green (paste tail). No `x`/`F`.
- [ ] `python -m pytest engine/tests -p randomly` ×3 different seeds — green (G7)
- [ ] `pytest -m integration engine/tests/test_live_devices_integration.py` — green, and it does **not** patch ffmpeg/subprocess (G1/G2)
- [ ] `npx prettier --check src && npx tsc --noEmit && npm run build` — clean
- [ ] G1 PoC: `stream.mp4` non-empty with `moov`, `capture` output `DECODE_OK` — pasted
- [ ] G3 PoC: `rtsp_test_source.py` runs on Windows, 3 URLs — pasted
- [ ] G6 PoC: 30 s ranged export `< 3 s` — pasted
- [ ] G8 PoC: 2 GB image scan peak RAM « file size — pasted
- [ ] Screenshots: 4-grid with 2 live devices (G4); a tile in error state, not "● live" (G5); Recovery table with `playable_frame_count` (G11)
- [ ] `grep -rn "text-emerald-400.*live\|>live<" src/` — no hardcoded live badge
- [ ] `grep -rn "bytes(data)\|read_bytes()\[" engine/app/parsers/` — empty
