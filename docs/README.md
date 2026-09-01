# Pramaan release documentation

This index describes Pramaan 0.6.0 as implemented and tested on 1 September 2026. Capability statements distinguish generated-fixture verification from independent OEM-media validation.

## Release set

- [Release audit](SIH26150-AUDIT.md)
- [Architecture, data flow, and trust boundaries](ARCHITECTURE.md)
- [OEM capabilities and limitations](CAPABILITIES-AND-LIMITATIONS.md)
- [Acquisition, recovery, custody, and transfer procedures](OPERATIONS-SOP.md)
- [User manual](USER-MANUAL.md)
- [Validation report](VALIDATION-REPORT.md)
- [BSA Section 63 certificate appendix](BSA-SECTION-63-CERTIFICATE.md)
- [Final project report](FINAL-PROJECT-REPORT.md)
- [Third-party dependency and license notices](THIRD-PARTY-NOTICES.md)
- [Release checklist and external blockers](RELEASE-CHECKLIST.md)
- [Desktop launch notes](DESKTOP.md)

## Evidence convention

Repository references are relative to the project root. A command result is a recorded observation for the named environment and date, not a guarantee for other machines or evidence media. Statutory statements link to India Code or the Gazette text.

## Required reading before operational use

1. Review the capability level for the source recorder.
2. Follow the acquisition procedure and use an independently verified hardware write blocker where preservation policy requires one.
3. Treat parser output as leads until an examiner corroborates the content, timestamps, channels, and hashes.
4. Complete the Section 63 certificate with case-specific facts and obtain legal review.

Evidence: `package.json`, `engine/app/__init__.py`, `validation_data/manifest.json`, and the 1 September 2026 command record in [Validation report](VALIDATION-REPORT.md).
