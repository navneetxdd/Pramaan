# Bharatiya Sakshya Adhiniyam Section 63 certificate appendix

## Status and use

The Bharatiya Sakshya Adhiniyam, 2023 (Act 47 of 2023) has an enforcement date of 1 July 2024. Section 63 governs admissibility of electronic records and subsection 63(4) requires a certificate to accompany the electronic record at each instance where it is submitted for admission. The statutory Schedule contains Part A for the party and Part B for the expert.

Authoritative sources:

- [India Code act record and enforcement date](https://www.indiacode.nic.in/handle/123456789/20063)
- [Official Act PDF, including Section 63 and the Schedule](https://upload.indiacode.nic.in/view-casepdf?id=AC_CEN_5_23_00049_2023-47_1719292804654&type=act)
- [Ministry of Home Affairs Gazette copy, Act 47 of 2023](https://www.mha.gov.in/sites/default/files/2024-04/250882_english_01042024_0.pdf)

This appendix is a completion aid, not a replacement for the statutory form or legal advice. Use the current official Schedule verbatim and have the responsible party, expert, and legal authority confirm applicability, especially for proceedings preserved under earlier law.

## Case-specific fact sheet

Complete without guessing. Write “not available” and explain when a fact cannot be established.

### Record being submitted

- Case/FIR/reference:
- Court/authority:
- Description of electronic record:
- File name(s):
- Submission instance and date:
- Source device class: computer / storage media / DVR / other:
- Make and model:
- Serial or unique identifier:
- Other identifying facts:

### Production method

- Person who produced the record:
- Lawful-control basis:
- Regular activity for which the source system created, stored, or processed information:
- How information was regularly supplied:
- Relevant operating period:
- Whether the device operated properly:
- Any malfunction and why it did or did not affect accuracy:
- Ownership/maintenance/management/operation relationship:
- Acquisition date, time, timezone, and location:
- Source condition and seal:
- Write-blocker make/model/serial/verification:
- Acquisition workstation and OS:
- Pramaan version:
- Acquisition method:
- Source path/device identifier:
- Output path/media identifier:
- Bytes acquired:
- Unreadable sectors and substitution method:

### Integrity values

- SHA-256:
- MD5, if included as a secondary compatibility value:
- Independent verification tool and version:
- Verification date/time/timezone:
- Hash-report filename:
- Hash-report SHA-256:

Pramaan's source for these technical fields is the device record and acquisition result created by `engine/app/services/physical_imaging.py`; verify every value independently before signing.

## Part A review — party

Using the official Schedule, the party should identify themselves, the device or digital-record source, make/model and identifiers, lawful control and regular activity, proper operation or relevant malfunction, relationship to the source, hash value and algorithm, then sign and date with IST time and place. Attach the hash report.

## Part B review — expert

Using the official Schedule, the expert should identify themselves and designation, identify the device or source, state the hash value and algorithm, then sign and date with IST time and place. Attach the hash report.

## Pramaan attachments checklist

- acquisition log and bad-sector map;
- source and destination identification photographs;
- write-blocker verification record;
- SHA-256 sidecar and independently generated hash report;
- evidence verification output;
- custody ledger plus signed human custody forms;
- parser and recovery method statement;
- recovered-file hashes;
- signed report and certificate fingerprint;
- case-bundle manifest when a bundle is submitted;
- explanation of every limitation relevant to the record.

Evidence for generated artifacts: `engine/app/core/db.py`, `engine/app/core/repository.py`, `engine/app/services/physical_imaging.py`, `engine/app/services/reporting.py`, and `engine/app/services/case_bundle.py`.

## Sign-off control

Do not sign until the official form has been compared with the current India Code text, all factual fields are supported by retained records, the hash report is attached, and the signatories understand that Pramaan uses a locally generated self-signed certificate unless an institutional signing process is separately applied.
