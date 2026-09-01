# SAM OA Reference Profile

## Purpose

The SAM OA reference profile records the reusable SysML v2 structure observed in a project exported from SAM. It is a structural interoperability reference, not an example model and not a second semantic source of truth for the application.

The application knowledge graph remains the semantic source of truth. This profile defines how a later SAM projection layer should represent that semantic model in the SAM-compatible SysML v2 shape.

## Files

- `sysml/SAM_OA.reference.sysml` contains only the reusable definition library observed in the SAM export.
- `sysml/SAM_OA.reference.json` contains the machine-readable mapping and projection shape.
- `sam_reference_profile.py` loads and validates the two files as one profile.

The spelling of the exported library package is preserved only in the declarative reference files. Application code must read it from the profile and must not reproduce it as a Python constant.

## Reference definitions

The profile records these SAM-exported definition forms:

| Application concept | SAM reference definition |
| --- | --- |
| Operational Entity | `part def 'Operational Entity'` |
| Operational Actor | `part def 'Operational Actor' :> 'Operational Entity'` |
| Operational Activity | `action def 'Operational Activity'` |
| Operational Capability | `requirement def 'Operational Capability'` with `subject` |
| Operational Exchange | `flow def 'Operational Iteration'` |
| Operational Scenario | `action def 'Operational Scenario'` |
| Operational Constraint | `constraint def 'Operational Constraint'` |
| Communication Mean | `interface def 'Communication Mean'` |

`Operational Exchange` intentionally maps to the SAM-exported definition name `Operational Iteration`. This is translation metadata, not a rename of the application's semantic concept.

## Model organization captured from SAM

The generated OA package is expected to contain three subpackages:

- `Structure`
- `Requirements`
- `Scenarios`

The profile records the following projection shape for the next implementation step:

- entities and actors are usages in `Structure`;
- activities are nested under the entity or actor that performs them;
- operational exchanges are flows in `Structure` between qualified activity paths;
- capabilities are requirements in `Requirements`;
- capability support is represented by allocation;
- scenarios are actions in `Scenarios`, reference existing activities with `perform action`, and sequence them with `transition first ... then ...`.

## Communication Mean phase policy

The reusable `Communication Mean` definition is retained because it is part of the SAM-exported reference library. However, Communication Mean projection is explicitly disabled for the current phase:

- no Communication Mean usages are generated for SAM;
- Operational Exchanges do not depend on a Communication Mean;
- incremental synchronization must ignore Communication Mean until the phase is explicitly enabled later.

## Non-goals of this commit

This commit does **not** replace the existing full projection or Level 1C incremental synchronization. It creates the declarative, validated reference profile that those implementations will consume in the next commits. This separation avoids changing live SAM synchronization behavior before the SAM-compatible full projection is ready and tested.
