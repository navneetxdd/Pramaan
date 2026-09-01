# DESIGN.md — Forensic Workstation
## Single source of visual truth. Never improvise a color, spacing value, or animation outside what's specified here.

### 0. The one-sentence brief
This looks like instrumentation, not a website. Think avionics HUD, a Bloomberg terminal,
Wireshark, a SOC wall display, EnCase/Autopsy's case tree — tools built by and for people
whose job is to trust the numbers on screen. Not a SaaS landing page, not a "beautiful
AI-generated dashboard." If a screen would look at home in a demo video with a gradient
hero and a testimonial carousel, it is wrong for this app.

Anti-slop rule, apply everywhere: every animation must communicate a real state change
(a job started, a hash verified, a gap was found in the timeline). Zero animations that
exist purely for "delight" with no informational payload. Install and run
`npx skills add https://github.com/emilkowalski/skills --skill review-animations --skill apple-design --skill emil-design-eng --skill find-animation-opportunities`
at project setup; run `review-animations` against every motion addition and only keep it
if that review passes.

### 1. Color system
Base is near-black navy, not pure black — pure black + pure white reads as an unstyled
terminal. A deep desaturated navy with a real blue undertone reads as engineered.

    :root {
      --surface-0: #05070d;   /* app chrome / outermost background */
      --surface-1: #0a0e1a;   /* page background */
      --surface-2: #0f1524;   /* card / panel background */
      --surface-3: #161d30;   /* raised panel / modal / active row */
      --surface-4: #1e263d;   /* hover state, input fields */
      --border-subtle: #232c45;
      --border-default: #2e3a5c;
      --border-strong: #3d4d78;

      --text-primary:   #eef1f8;
      --text-secondary: #aab4cc;
      --text-tertiary:  #6b7593;

      --accent-500: #2f6fed;   /* primary actions, active nav, links — the ONE accent hue */
      --accent-400: #5b8dff;
      --accent-glow: rgba(47, 111, 237, 0.35);   /* focus rings / active-job pulse ONLY */

      --status-success: #3ba676;
      --status-warning: #d9a441;
      --status-danger:  #d6584f;
      --status-info:    #4a9fd8;

      --confidence-high:   #3ba676;   /* dual-signature validated */
      --confidence-medium: #d9a441;   /* header-only candidate */
      --confidence-low:    #6b7593;   /* offset-ordered / unverified timestamp */
    }

Rules:
- Never introduce a second accent hue — no purple, no teal, no gradient between two hues.
- No gradients on large surfaces. The one exception: a slow, low-opacity animated border
  on an actively-running job card (§5.3) — navy to accent-blue and back, only while that
  job is running.
- No glassmorphism / frosted blur panels — the single most common "AI dashboard" tell.
  Every panel is opaque, flat, 1px `--border-subtle` edge. Depth = subtle elevation
  shadow (`box-shadow: 0 1px 2px rgba(0,0,0,0.4)` max), never blur.
- No light mode. Skip it entirely — forensic examiners work long hours in low-light labs.

### 2. Typography
- UI text: Inter (variable font).
- ALL numeric/hex/timestamp/hash/byte-offset values, everywhere in the app, in a
  monospace family (JetBrains Mono or IBM Plex Mono) — the single decision that most
  signals "real forensic tool" rather than a generic dashboard.
- Type scale: 12/13/14(body default)/16/20/26/34px only. Line-height 1.4 body, 1.15
  headings/data.
- All-caps section labels ("CHAIN OF CUSTODY", "DEVICE IDENTIFICATION") at +0.02em
  letter-spacing, used as every panel's title.

### 3. Layout grammar
- Persistent left rail (72px collapsed / 220px expanded), not a top navbar.
- Every primary screen is a two- or three-pane layout, never a single centered column.
- Persistent bottom status bar (VS Code-style): active case name, current job with live
  micro-progress, chain-of-custody status dot (green=verified, amber=unverified since
  last check, red=broken), signing-certificate fingerprint.
- Corner radius: 6px cards/inputs, 4px badges/pills, 0px on the rail and status bar.
- Default table row density: compact (32-36px). "Comfortable" toggle in Settings only.

### 4. Iconography
- Lucide icons, 1.5px stroke, 18-20px, no fills except status dots.
- One consistent icon per module everywhere referenced: Acquisition=HardDriveDownload,
  Device ID=Fingerprint, Recovery=ScanSearch, Timeline=GanttChartSquare, Chain of
  Custody=ShieldCheck, Reporting=FileText, AI Analytics=ScanEye, Case Mgmt=FolderKanban,
  Tool Verification=BadgeCheck.

### 5. Motion
5.1 Four purposeful, code-authored (CSS/SVG/Framer Motion — not Rive; an AI coding agent
    cannot author .riv files, they require Rive's visual editor with no code-only
    creation path) event-driven pieces, and only these four:
    - Disk-scan sweep: a thin line sweeping across a schematic disk icon, width bound to
      real job progress % from the SSE stream. Freezes at the exact frame the job
      pauses/completes.
    - Hash-verify badge: pending -> verified (green check) OR pending -> mismatch
      (red X), plays once, on the exact backend result.
    - Chain-link status icon (status bar): idle/static green; brief single-cycle
      "verifying" animation while a verification check runs; broken = link visibly
      separates and STAYS separated until resolved — never auto-resets.
    - Manufacturer-detection radar sweep: plays during Layer 1/2 signature scanning,
      freezes and snaps to the labelled result the instant detection completes.
5.2 Framer Motion, restrained: 120-160ms opacity+4px-translate page transitions,
    ease-out. Numeric counters animate ONLY while the underlying value is actively
    changing during a running job. New table rows during a live job: a 150ms background
    flash from --accent-glow fading to transparent. NO hover-lift, NO hover-scale, NO
    button bounce — hover = simple background/border color change, 100ms. Sonner toasts
    for background-job completion/custody events/exports, bottom-right, 4s auto-dismiss
    except errors.
5.3 The one ambient element in the entire app: an actively-running job's card gets a
    slow (3s cycle) low-opacity animated border gradient, navy-to-accent and back. This
    is the ONLY idle-animating thing anywhere in the app.

### 6. Component sourcing
- shadcn/ui (Radix) base primitives, fresh init.
- Bklit UI for the multi-camera timeline and confidence-tier breakdown chart — restyled
  to the tokens above, never their default theme.
- driver.js, one opt-in first-run tour, dismissible, stored in local settings so it
  never re-triggers.
- `@tanstack/react-virtual` for the recovered-sequences table, the chain-of-custody
  ledger, and the hex/byte-grid inspector — any of these can grow to thousands of rows.
- A curated handful of Aceternity/cult-ui/skiper-ui STRUCTURAL patterns only (command
  palette, animated-number primitive, tree-view for the partition tree) — restyle every
  color/shadow/border to this file's tokens, never import their default themed CSS.
- Do NOT install: scroll-jacking libraries, particle-background libraries, marketing-
  site template packs, any component library's default hero/pricing/testimonial blocks.

### 7. Page-by-page treatment
1. Case Dashboard — compact table, command palette (Cmd/Ctrl+K) front and center,
   "New Case" = small modal not a full wizard.
2. Acquisition — solid `--status-warning`-bordered READ-ONLY banner whenever a live
   physical device is selected; disk-scan-sweep + live monospace hash readout; bad-
   sector count and a resume affordance if a prior run was interrupted.
3. Device Identification — three-pane: partition tree / hex-and-struct inspector styled
   like a real hex editor / chronological detection trace log with exact offsets.
4. Recovery — config panel on top; live auto-scrolling monospace log colored by
   confidence tier; a live confidence-tier ring chart; results table populates live.
5. Timeline & Playback — full-width multi-track timeline, gaps visibly hatched, native
   <video> player synced to scrub position across all lanes.
6. AI Analytics — persistent, non-dismissible `--status-warning` banner: "Investigative
   leads only — not verified evidence."
7. Chain of Custody — read-only monospace ledger; status is shown live, not behind a
   button the examiner has to remember to press (Part G.7).
8. Report Generation — two-pane live preview (section checklist / actual rendered
   report), signature-validity indicator shown once generated.
9. Tool Verification — one-click "Run Verification Suite," pass/fail per stage, exportable
   as a report appendix.
10. Settings — plain, functional, grouped form fields, including the signing-certificate
    management screen (Part G.7). No special design effort here.

### 8. What "done" looks like
If a screenshot could be mistaken for a generic Cursor/v0/Lovable SaaS dashboard, the
design has failed regardless of backend correctness. If it could pass for a screen from
Wireshark, Autopsy, or a SOC monitoring wall — navy, monospace data, dense tables, one
restrained accent, motion that only ever reports real state — it has succeeded.
