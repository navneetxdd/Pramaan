# User manual

## System purpose

Pramaan 0.6.0 manages local DVR/NVR image acquisition, manufacturer hints, recovery candidates, timeline review, integrity checks, custody records, reports, and signed case transfer. It is not a substitute for examiner judgment or independently validated laboratory procedures.

## Start

Development desktop:

```powershell
npm install
pip install -r engine/requirements.txt
npm run tauri:dev
```

Backend-only API testing:

```powershell
python run.py
```

The engine listens on `127.0.0.1:8787`; all client routes use `/api/v1/*`. Application data defaults to `%USERPROFILE%\ForensicWorkstation\data` on Windows and can be moved with `FORENSIC_WORKSTATION_DATA`.

Evidence: `README.md`, `run.py`, `engine/app/core/config.py`, and `src-tauri/tauri.conf.json`.

## Standard workflow

### 1. Create a case

Enter a descriptive case name and examiner identity. A case record and custody event are created. Avoid personal data not required by policy.

### 2. Add evidence

- **Physical/file imaging:** select the authorized source and create a raw DD copy.
- **Existing image:** import a forensic image through the available acquisition flow.
- **Generated specimen:** use only for training and tool verification; it is not case evidence.

Wait for completion. Review source identifier, size, SHA-256, MD5, destination verification, and bad-sector count before continuing.

### 3. Identify

Review every marker, confidence value, filesystem hint, and selected adapter. Detection is byte-token based. A listed brand or high score is not conclusive OEM attribution.

### 4. Recover

Start recovery and monitor the job to a terminal state. Review parser validation labels and offsets. For generic recovery, timestamps are unverified and ordering is based on byte offset.

### 5. Review and export

Inspect sequence playback or exported content. Confirm:

- the file decodes;
- scene and camera match the case;
- channel attribution is plausible;
- start/end labels have documented meaning;
- content is not duplicated or overwritten;
- exported SHA-256 matches the recorded value.

### 6. Verify and report

Run evidence verification before reporting. Generate JSON for structured review, HTML for inspection, or signed PDF for the case file. Report generation stops if the custody chain is broken.

### 7. Transfer

Export the signed case bundle, independently hash it, communicate the signer fingerprint separately, and follow [the transfer procedure](OPERATIONS-SOP.md#d-case-transfer).

Evidence: `engine/app/api/v1/cases.py`, `engine/app/api/v1/acquisition.py`, `engine/app/api/v1/devices.py`, `engine/app/api/v1/jobs.py`, `engine/app/api/v1/reports.py`, and `engine/app/api/v1/case_transfer.py`.

## Failure handling

| Symptom | Meaning | Action |
|---|---|---|
| Engine port already in use | another process owns port 8787 | stop the stale engine or identify the owning process; do not start duplicate jobs |
| Physical disks absent | insufficient Windows privilege or enumeration issue | restart under approved elevation and confirm disk identity |
| E01 rejected | optional `pyewf` unavailable | install an approved compatible build or provide raw/DD |
| Acquisition interrupted | source read or process failure | preserve files and logs; correct cause; resume only against the same source |
| Verification mismatch | stored bytes changed or wrong source/destination | quarantine the copy and reacquire; do not continue recovery |
| No vendor hit | no known marker in sampled prefix | use generic path only with its limitations, or escalate |
| No recovered segments | parser found no qualifying candidates | verify adapter and scan scope; do not interpret as proof of absence |
| Report rejected | custody chain is invalid or case is missing | preserve state, investigate discrepancy, and do not bypass |
| Bundle import rejected | signature, hash, archive, or format validation failed | quarantine bundle and contact sender |

Evidence: `engine/app/services/physical_imaging.py`, `engine/app/services/recovery.py`, `engine/app/services/reporting.py`, `engine/app/services/case_bundle.py`, and the recorded port collision in the existing 1 September 2026 terminal output.
