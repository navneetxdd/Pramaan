# Acquisition module

**Input:** multipart disk image upload (`file`), `actor`, `case_id`  
**Output:** `EvidenceRecord` JSON + `vendor_hints` + `.sha256` sidecar path  
**Env:** `PRAMAAN_MAX_UPLOAD_BYTES`, `PRAMAAN_STORAGE_ROOT`  
**Public API:** `pramaan.modules.acquisition.service.acquire_disk_image`
