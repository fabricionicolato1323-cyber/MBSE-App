# SAM2 Baseline Performance

The SAM-compatible full baseline now uses PySAM transactional mode by default.

## Why

The proven direct-create transport commits each SysML element separately. PySAM
reloads the project after direct commits, so a baseline with participants,
activities, flows, connector ends, references, capabilities, and scenario steps
can require many server round trips.

## Fast path

For a new SAM2 baseline the application now:

1. reuses `MBSE_SAM_OA_Reference_Library_v2` when it already exists;
2. builds the complete `Arcadia_OA / Structure / Requirements / Scenarios`
   baseline locally inside PySAM transactional mode;
3. sends one model commit to SAM;
4. performs one fresh read to verify the completed package.

If the reusable library is absent, its definitions are also created
transactionally in one additional commit.

Optional per-element source Documentation/Comment objects are not transmitted
by this fast path. They were a major source of direct-create round trips. The one
exception is compact characteristic value/unit metadata attached to
`AttributeUsage`, because those values are semantic model content. Source
traceability for the other elements remains in the MBSE-App model and the
reviewed/exportable SysML Level 1 text.

The fast path intentionally continues the Commit 2 phase boundaries:

- Communication Mean is library-only and is not instantiated.
- Native Succession creation remains disabled for the current live SAM/PySAM
  combination; scenario order remains represented in the reviewed textual SysML.
- Level 1C migration to the SAM2 structure is still deferred.

For troubleshooting only, set `SAM_BASELINE_TRANSPORT=direct` to use the proven slower Commit 2 writer.
