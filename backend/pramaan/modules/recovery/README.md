# Recovery module

**Input:** `case_id`, `image_id`, `actor`, optional `max_scan_bytes`  
**Output:** `RecoveryJobRecord`, `SegmentRecord[]`, vendor hits  
**Adapters:** register via `pramaan.modules.recovery.registry.register()`  
**Env:** `PRAMAAN_RECOVERY_SCAN_BYTES` (0 = full image)  
**Public API:** `schedule_recovery`, `execute_recovery_job`
