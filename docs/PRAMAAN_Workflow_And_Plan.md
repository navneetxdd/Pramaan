# PRAMAAN — Evidence Pipeline & Team Plan

Answers the "what's the correct workflow" question, sets three scope decisions, and assigns what's left. Short on purpose — read it once, keep it open while you work.

> **Design ground rule still applies.** Light theme only. `DESIGN.md` is dead.

---

## 1. The pipeline — resolved

Two ideas got framed as alternatives that aren't actually in tension. Here's the real sequence, and where each concern lands.

| # | Step | What happens | Why nothing gets lost |
|---|---|---|---|
| 1 | **Acquire** | Bit-for-bit forensic image of the whole storage device (`.dd`/`.raw`/`.E01`). Hashed (MD5+SHA-256). Never touched again. | This step *is* "preserve everything first." The raw image contains every byte — including structures we don't yet know matter. Nothing downstream can lose data that's still sitting in the image. |
| 2 | **Identify** | Signature-match the vendor/filesystem directly on the image bytes. | Read-only. No conversion happening yet. |
| 3 | **Parse** | Vendor-specific adapter walks the proprietary index (HIKBTREE, DHFS, GPT-like) **directly on the raw image**. Extracts: channel, start/end timestamp, allocation state (normal / recording / deleted), byte offset. | This is "the friend's idea" — read the original structure directly, no intermediate conversion. It's correct: converting before you've parsed the index would destroy the very thing you're trying to read. |
| 4 | **Recover** | For each index entry — including ones flagged `deleted` — carve the byte range out of the image. | Deleted-flagged entries are still inside the image; the index just says the slot was reused/cleared. If the underlying bytes weren't overwritten, they carve out cleanly. If they were overwritten, recovery is genuinely impossible — mark `PARTIAL`, never invent frames to fill the gap. |
| 5 | **Unwrap** | Strip the vendor's per-recording wrapper (DHAV frame headers, HIKBTREE data block, Honeywell NAL headers) to expose the raw H.264/H.265 elementary stream underneath. | **Not conversion.** Every vendor wraps standard H.264/H.265 in a proprietary envelope — unwrapping removes the envelope, the video bytes are untouched. Reversible: given the image + the recorded byte offset, you can always re-derive this. |
| 6 | **Repackage** | Put the unwrapped stream into a standard container (`.mp4`) via `ffmpeg -c copy` — a **remux**, not a transcode. Re-encode only as a last-resort fallback when a stream is too damaged to copy, and that fallback must be logged, never silent. | Remux copies bits into a new box; zero quality loss, near-instant. Transcode decodes and re-encodes — slow, lossy, and never the first choice for evidence. |
| 7 | **Normalize timestamps** | Correct the recorder's own clock against a reference offset, per channel. | Metadata-level. Doesn't touch video bytes. |
| 8 | **Hash + analyze** | Hash the derived MP4 (separate from the image's hash, both recorded and linked). Run AI/cross-camera analysis on the derived, playable copy. | This is the one place lossy operations legitimately happen (frame decode for detection) — because it's *analysis*, not evidence transformation. Results are always labeled investigative leads, never presented as the evidence itself. |
| — | **Custody + report** | Every step above appends a hash-linked custody entry. Report cites both hashes (image + derived clip) for every artifact shown. | Runs alongside every step, not after them. |

**One line if someone asks "don't we lose metadata on conversion?"** — No, because we never convert the evidence. We read metadata from the untouched original in step 3, and derive an additional, always-regenerable playable copy in steps 5–6. The original and the extracted metadata both stay intact regardless of what happens to the derived copy.

---

## 2. Three scope decisions

**Initial input format.** A forensic disk image (`.dd` / `.raw` / `.E01`) of the DVR/NVR's storage — that is the PS's actual ask ("create forensic images"). Already-exported video files (`.mp4`, `.dav`, `.264`…) are accepted as a secondary shortcut path — useful when someone hands you a clip that's already off the device — but they skip identify/recover entirely because there's no proprietary filesystem left to parse. Don't present the shortcut path as equivalent to the real pipeline in a demo.

**Corrupted footage.** Recover what's genuinely present. Missing/overwritten bytes get marked `PARTIAL` — never silently patched with guessed or interpolated content. This is already the pattern in the codebase (`recovery_status`); keep it that way everywhere.

**Upscaling / image enhancement — out of scope, on purpose.** Not in the PS. More importantly: AI super-resolution on evidence is a real liability, not a feature — a generative model fills in pixels that were never captured, which is exactly the kind of thing that gets forensic video analysis thrown out (this is standard guidance in the field, not a Pramaan-specific opinion). If it comes up: Pramaan is one focused tool in a forensic workstation, the same way DVR Examiner and UFS Explorer are — recovery, parsing, and hashing here; hand off to a dedicated video-enhancement tool downstream if a case genuinely needs it. Saying this plainly is a stronger answer than building a half-safe upscaler.

---

## 3. Where things stand — spot-checked today, not a full re-audit

| Area | Status | How I know |
|---|---|---|
| Cross-camera trace, Findings proximity flags | **Shipped** | Built and merged this session (Navneet). |
| Live devices | **Removed entirely** | Confirmed out of PS scope; deleted frontend/backend/tests/CI job. Drop it from every plan, script, and demo checklist. |
| Hikvision parser (`hikvision_fs.py`) | **Solid** | Cites 2 peer-reviewed papers + 1 corroborating OSS project; tracks `deleted` as a first-class state. |
| Hikvision recovery on the current lab image | **Bug, reproduced today** | `lab_hikvision_fs.img` identifies correctly (HIKBTREE match, 0.6 confidence) but `recover` returns **0 segments**. Not yet root-caused. |
| Dahua recovery on the real `.dav` | **Works** | Ran it today end to end: acquire → identify (0.98 confidence) → recover → 1 segment recovered → playable. |
| Dahua DHFS parsing | **Still carve-only** | `dahua_dhfs.py` still scans for the `DHAV` frame magic and treats a 4KB gap as "deleted" — it never reads the DHFS index/allocation table. |
| Recovery page deleted column/filter | **Present** | `deletedOnly` toggle + allocation glyphs exist in `CaseRecoverPage.tsx`. |
| Ranged export (`-ss`/`-c copy`) | **Verifies before trusting** | Checks return code + file size, falls back to re-encode on failure — the old silent-empty-file bug looks fixed. |
| Report HTML preview | **Still dark-themed** | `reporting.py` still sets `background:#0a0e1a` — the one place the rejected dark UI is still live. |
| Job log | **Still recovery-only** | Only filters `job.kind === "recovery"` — analytics/export/import jobs still invisible. |
| Settings | **"Parser sanity check" panel still present** | Still shipped as a product feature, not moved to CI-only. |
| Evidence catalog | **"Lab specimen" category still present** | Still a real filter option in the UI. |
| Blockchain & Cybersecurity theme fit | **Already answered, not stated as such** | The custody log already *is* an append-only hash-chained ledger — exactly what the theme calls for. Nobody says this out loud in the report or pitch yet. |
| BSA Section 63 certificate format | **Gap** | `reporting.py` has no "Section 63" / "responsible official" language — the report isn't shaped like the specific legal certificate format Indian courts expect for electronic evidence. |
| Clock-drift warning | **Gap** | `drift_offset_seconds` silently defaults to 0 when nobody's calibrated it — no warning surfaced when a device's clock was never synced. |

---

## 4. Who does what

Weighted by real effort, not bullet count — a one-line reverse-engineering bug can eat more time than five small UI fixes. If any list below turns out heavier in practice than it reads, say so and we redistribute; nobody should be quietly stuck.

### Navneet — Cross-camera trace (own scope, already shipped and refining)
- Get genuine multi-**angle** test footage — even two phones filming the same walking path from different sides is enough. Today's demo proves the correlation machinery (tracklets → clustering → search) works across separate sources, but the two "cameras" used were two time-windows of *one* real feed, not two distinct viewpoints. Cross-view appearance matching is the harder, more honest test.
- Optional, coordinate with Roshan first: the PS's literal phrase is "correlate events across cameras," which is broader than person matching — aligning Findings' motion/object timestamps across channels on Timeline's shared axis would answer that more completely. Don't start this without checking Roshan isn't already covering it in his shared-axis work — same feature built twice is wasted effort either way.
- Rehearse the "show me that traceability right now" moment: click an appearance dot → open the frame → Save as evidence → sha256 appears live. Already works end to end; just make sure it's part of the demo script, not left implicit.

### Aravind — Hikvision recovery
- Root-cause the 0-segments bug on `lab_hikvision_fs.img` (identification works, recovery doesn't — start at `HikvisionAdapter._scan` / `list_recordings`).
- If a real (not lab-built) Hikvision disk image can be sourced, swap it in and re-verify every offset in `docs/reference/hikvision_fs.md` against it.
- **Done when:** the lab image (or a real one) recovers a non-zero, correct count of recordings, at least one marked `deleted`, with a regression test.

### Aslam — Dahua filesystem + the unwrap/remux pipeline
- Replace the DHAV magic-carve with real DHFS index parsing (partition marker `DHFS4.1`) — enumerate recordings from the index instead of scanning for frame headers. Keep the magic-scan as an explicit `carve_fallback` for damaged indexes.
- Entries whose byte range falls outside any allocated index entry → `deleted (unallocated extent)`, replacing the current 4KB-gap heuristic.
- Audit-round-5 already tightened the ranged-export ffmpeg path — re-verify it against a Dahua recording specifically (today's test only exercised the full-segment path).
- **Done when:** Dahua recovery reports a real deleted count sourced from the index, not a gap heuristic.

### Roshan — Timeline & playback, multi-channel
- Confirm the per-channel grouping in `timeline.py` actually drives a **shared absolute axis** in `TimelineView.tsx` with one scrub moving every lane (this existed as a gap in the last audit — re-verify it's actually wired end to end, not just present in the backend).
- Deleted segments get a distinct lane color + legend + "deleted only" toggle, fed from the real `allocation_state` Aravind/Aslam now emit.
- Small add-on: surface a visible warning when a device's `drift_offset_seconds` was never calibrated, instead of silently treating it as zero — a judge who knows forensics will ask what happens when the recorder clock was never NTP-synced.
- **Done when:** a 2-channel case shows both lanes on one absolute axis, deleted segments visually distinct, one scrub moves both, and an uncalibrated device says so.

### Jai Pranav — Report, Job log, Settings, Evidence catalog, integration
- **Report:** restyle `reporting.py`'s generated HTML off the dark palette (`#0a0e1a` → white/near-black/one blue accent, matching every other screen). Last place the rejected dark UI survives.
- Small add-on: shape the report's attestation section like a **BSA Section 63 certificate** — device details, hash, extraction method, operator, all pre-filled and ready for a named responsible official's signature. The tool drafts it; it doesn't remove the human legal signatory — that's the legally correct framing, and it's the one explicit legal-compliance deliverable this PS has that nothing in the app currently names.
- **Job log:** add a job-kind column; stop filtering to `recovery` only — analytics, export, and cross-camera jobs need to show up too.
- **Settings:** remove the "Parser sanity check" panel and its backend; those checks belong in CI (`pytest`), not the product.
- **Evidence catalog:** remove the "Lab specimen" category/filter/icon.
- **Integration:** update (or retire) `scripts/demo/mvp.sh` — it still assumes Live devices exists as a demo step; drop it. Re-run the demo script end to end on the real Dahua `.dav` and confirm every step in Section 1 above actually happens on screen.
- **Done when:** report preview is light-themed and Section-63-shaped, job log shows every kind, Settings/Evidence catalog have no fake surfaces left, and the demo script runs clean top to bottom.

---

## 5. How this actually gets judged

Two things changed the calculus for 2026 (from a 3x official SIH evaluator's own breakdown): AI coding tools mean anyone can show a working-looking frontend in minutes, so "a demo runs" dropped from ~60% to 20–30% of the score. The other 70–80% is architecture, whether the codebase is logically structured, and whether *you personally* can explain every piece you built — not just click through it. Practically: everyone on this team needs to be able to explain their own module's internals cold, not just demo it.

**Five questions to have real answers for, not deflections** (the pattern an NTRO-style evaluator opens with):
1. "Is your input data real or synthetic?" — Real Dahua `.dav`, real Hikvision NVR export, real Digital Corpora `.E01` images; synthetic only for filesystem-structure fixtures, and say so plainly.
2. "What's the AI doing that a rule-based system couldn't?" — Be precise per feature. Person re-identification genuinely needs learned embeddings. Motion/scene-change detection is classical CV, not AI. The proximity flag is pure geometry. Don't call the classical parts "AI."
3. "Does it degrade gracefully?" — Yes: model-availability checks skip cleanly with a clear message, `PARTIAL` recovery status for damaged data, confidence disclosed rather than guessed.
4. "Production-scale data?" — Honest answer: validated on real single-device samples, not a fleet. Say that outright.
5. "How do you know the hash chain itself wasn't tampered with after generation?" — The custody log is an append-only, hash-chained ledger — every entry's hash depends on the previous one, so altering an old entry breaks every entry after it. That's also the direct answer to this PS's "Blockchain & Cybersecurity" theme; say so explicitly in the report and pitch, it's a genuine fit nobody's stated out loud yet.

**The honest OEM-breadth answer**, since it's the single most likely thing a sharp judge targets first: don't claim "8/8 OEM support." The PS's own text says teams realistically go deep on one or two brands, not all eight — that's exactly Pramaan's shape already (Dahua, Hikvision, Honeywell parsed properly; the rest get honest acquisition + generic recovery, clearly labeled). Leading with that is a stronger answer than a slide that collapses under one follow-up question.

**The PPT itself** follows the official 5-slide structure: Problem Understanding → Tech Stack & Architecture → Feasibility/Risks & Mitigation → Real-World Impact → Research & References. The architecture slide needs real backend depth, not a UI screenshot. The references slide should cite the same academic sources already backing the Hikvision engine (ICDF2C 2015, *Journal of Forensic Sciences* 2023, MDPI *Information* 2025) — exactly the kind of citation this format rewards, and it's already sitting in `docs/reference/hikvision_fs.md`; it just needs to be pulled onto a slide.

**One stack note:** if you've seen other SIH26150 material suggesting YOLOv11 + ByteTrack + InsightFace as the AI layer — that's a different team's plan, not ours. Pramaan deliberately runs YOLOX-nano + a compact re-identification model, all ONNX via `cv2.dnn`, no PyTorch — a judge who asks about compute cost gets a real answer instead of "it needs a GPU." Don't switch to the heavier stack; it undoes a deliberate choice.

---

## 6. Before calling anything done

- `python -m pytest engine/tests -q` green.
- Frontend typecheck, build, and format check clean on your changed files (`npm run build`, `npx tsc`, `npm run format:check`).
- Your "done when" line above, demonstrated on real evidence — not a fixture, not your first try.
