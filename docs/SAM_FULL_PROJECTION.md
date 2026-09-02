# SAM-Compatible Full Projection

## Scope

This increment makes the reviewed Level 1 SysML preview and the live managed-direct SAM baseline follow the structural shape captured in `sysml/SAM_OA.reference.*`.

The application knowledge graph remains the semantic source of truth. The SAM projection is a derived representation.

## Projected shape

A generated model contains an `Arcadia_OA` package with three children:

- `Structure`
- `Requirements`
- `Scenarios`

The projection rules are:

- Operational Entity and Operational Actor become part usages in `Structure`.
- `CONTAINS` is represented by nested part ownership.
- `PERFORMS` determines the owner of an Operational Activity; it is not emitted as a second standalone relationship in the full baseline.
- Operational Activity decomposition is represented by nested action usages.
- Operational Exchange is a flow typed by the reference definition `Operational Iteration` and connects the qualified source and target activity paths.
- Operational Capability becomes a requirement usage in `Requirements`.
- Capability decomposition is represented by nested requirement usages.
- Capability support is represented textually with allocation semantics. The existing reload-safe direct transport may persist the equivalent requirement-satisfaction relation when SAM rejects derived AllocationUsage connector fields.
- `LOCATED_IN` is represented by a reference usage.
- Characteristics remain attribute usages and retain their source values as metadata.
- Operational Scenario becomes an action usage in `Scenarios`; its activity steps are `perform action` references to the already-created activities and sequence is represented by transitions in the reviewed textual projection.

## Communication Mean phase boundary

`Communication Mean` remains in the reusable reference library because it is part of the SAM-exported library shape. Model-level Communication Mean relationships are classified as `ignore` and are not created in the SAM baseline in this phase.

## Baseline coexistence

The new baseline uses a versioned reusable library named `MBSE_SAM_OA_Reference_Library_v2` and versioned instance names beginning with `MBSE_Instance_SAM2_`. This prevents an existing legacy Level 1C library or instance from being mistaken for the new structural baseline.

The current incremental manifest is deliberately not migrated by this commit. After a fresh SAM2 baseline publish, `incremental_sync_deferred=true` is returned. Migration and full relationship-aware incremental synchronization belong to the next increment.

## Safety properties

- No example participant, activity, capability, exchange, scenario, or ID from the reference model is embedded in projection logic.
- The reviewed textual projection and the PySAM writer consume the same declarative reference profile.
- Unsupported source semantics block the new writer before the first model-content create.
- Existing legacy Level 1C artifacts can coexist with the SAM2 baseline because library and instance names are versioned.
