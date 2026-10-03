# 0002 — Canonical Business + Operational Model

## 1. Summary

MBSE-App shall evolve from an Arcadia Operational Analysis-centered persistent model into a methodology-independent Canonical Business + Operational Model.

The canonical model is the authoritative representation of engineering meaning. A project may be created, edited, saved, loaded, validated, and continued without selecting Arcadia, UAF, SysML v2, SAM, or any other methodology or downstream environment.

Arcadia, UAF, and future methodologies are optional semantic projections or adaptations of the canonical model and are not part of the canonical model itself.

This change shall be introduced incrementally. Existing deterministic graph behavior, human confirmation, provenance, project IDs, save/load behavior, operational modeling capability, scenarios, tests, and downstream SysML/SAM investment shall be preserved whenever their semantics remain valid.

---

## 2. User problem

The current application persists an Arcadia Operational Analysis model as its primary source of truth.

This creates three limitations:

1. users must effectively enter through an Arcadia/OA semantic structure even when they only want to perform Business or Operational Analysis;
2. business concepts cannot coexist naturally with operational concepts in the authoritative project model;
3. future methodology support would require modifying the core model instead of adding explicit semantic adapters.

The desired user experience is methodology-independent.

A user should be able to begin with a business problem, a stakeholder concern, an operational activity, an existing project, or later a document, and progressively construct one authoritative semantic model.

Methodology selection is optional.

---

## 3. Scope

### In scope

- Introduce the Canonical Business + Operational Model as the persistent semantic authority.
- Introduce explicit Canonical Mode.
- Allow a project to exist without an active methodology.
- Allow Business Analysis and Operational Analysis concepts to coexist in the same NetworkX model.
- Preserve the existing deterministic write barrier.
- Preserve explicit human confirmation before persistent inferred knowledge is written.
- Preserve stable model element identifiers.
- Preserve supported persistent attributes, including provenance.
- Introduce backward-compatible loading of existing OA JSON files.
- Ensure an existing `OperationalCapability` remains an `OperationalCapability` after migration.
- Introduce canonical Business Analysis concept identities.
- Retain existing supported Operational Analysis concepts.
- Remove Arcadia identity from canonical project metadata.
- Separate canonical runtime behavior from optional Arcadia knowledge services.
- Prevent existing Arcadia/SAM-specific projections from becoming implicit canonical semantics.
- Preserve existing scenario data and operational behavior where semantically unchanged.
- Establish extension seams for future methodology adapters.

### Out of scope

- Arcadia adapter implementation.
- UAF adapter implementation.
- Generic methodology adapter implementation.
- Business-to-Operational semantic mappings whose meaning has not yet been explicitly agreed.
- Round-trip synchronization with methodologies.
- Document semantic intake.
- Generalized Gap Engine.
- State / Mode / Situation / Configuration / Event semantic implementation.
- Redesign of Operational Scenario semantics.
- Canonical → SysML v2 projection.
- Arcadia → SysML v2 redesign.
- UAF → SysML v2.
- Changes to SAM's semantic contract.
- System Analysis.
- Logical Architecture.
- Physical Architecture.
- LLM fine-tuning.

---

## 4. Semantic rules

### 4.1 Canonical authority

The Canonical Business + Operational Model is the authoritative persistent project model.

Methodology-specific representations are projections from the canonical model and must not become alternative sources of truth.

### 4.2 Methodology independence

A canonical project shall not require a methodology selection.

Absence of a methodology is a valid project state and must not be treated as incomplete.

Canonical domain semantics shall not depend on Arcadia terminology, UAF terminology, SysML terminology, or SAM terminology.

### 4.3 Canonical concept identities

The first canonical version shall recognize these Business Analysis concept identities:

- `BusinessProblem` — Business Problem / Opportunity
- `Stakeholder`
- `Driver`
- `BusinessObjective`
- `DesiredOutcome`
- `Value`
- `BusinessCapability`

The first canonical version shall preserve these existing Operational Analysis concept identities:

- `OperationalCapability`
- `OperationalActor`
- `OperationalEntity`
- `OperationalActivity`

The wider canonical semantic vocabulary also includes concepts such as Evidence, Assumption, Constraint, Measure, Event, State, Mode, Situation, Configuration, Provenance, Operational Role, Operational Exchange, Communication Mean, Operational Scenario, and Environment. Their persistent graph representation is not decided by this Wave 1 specification unless an existing representation is explicitly preserved below.

### 4.4 No invented Business relationships

Wave 1 shall not invent Business↔Business or Business↔Operational relationships merely to connect the newly recognized Business concepts.

Business concepts may coexist with Operational concepts even when no semantic relationship between them has yet been confirmed.

Any proposed relationship such as drives, supports, realizes, enables, satisfies, contributes-to, or similar must be treated as a separate semantic decision before it becomes part of the canonical relation contract.

### 4.5 Existing operational concepts

Existing confirmed Operational concepts shall retain their identity and meaning during migration.

In particular, an existing `OperationalCapability` previously shown to the user as a "goal" shall not automatically become a `BusinessObjective`, `DesiredOutcome`, or other Business concept.

### 4.6 Existing operational relationship representations

Wave 1 shall preserve existing operational representations unless an explicit semantic decision changes them.

Existing representations include:

- participant → activity `PERFORMS`;
- activity → capability `SUPPORTS_CAPABILITY`;
- `DECOMPOSES`;
- `CONTAINS`;
- `LOCATED_IN`;
- operational exchanges currently represented by `OPERATIONAL_EXCHANGE` edges;
- communication means currently represented by `COMMUNICATION_MEAN` edges.

Existing Operational Scenario records shall be preserved.

Whether Operational Exchange, Communication Mean, Operational Role, Scenario, Evidence, Provenance, State, Mode, Situation, Configuration, Event, Environment, Assumption, Constraint, and Measure should eventually be represented as nodes, relationships, structured records, attributes, or another canonical construct is a separate semantic decision.

Wave 1 shall not perform an implicit representation migration.

### 4.7 Candidate knowledge

Candidates, inferred classifications, LLM suggestions, document extraction results, and semantic parsing results are not canonical facts.

They become persistent knowledge only after deterministic validation and the required human confirmation.

### 4.8 Provenance

All provenance already attached to confirmed model content shall survive migration and save/load without modification or loss.

Wave 1 shall not invent a new provenance ontology before its canonical representation is agreed.

### 4.9 IDs

Migration and save/load shall preserve existing element IDs.

A compatibility migration must not recreate existing model elements merely to change project format metadata.

### 4.10 Optional downstream projections

Arcadia, UAF, SysML v2, and SAM are not required to construct or edit a canonical project.

Failure, absence, non-configuration, or semantic incompleteness of one of these components must not prevent ordinary canonical modeling.

### 4.11 One-way adaptation

Where methodology adaptation is later enabled, the initial direction is:

`Canonical → Methodology`

Round-trip synchronization is outside this phase.

---

## 5. User interaction rules

Canonical Mode shall be the normal methodology-independent project state.

The UI shall continue to use conversation-first interaction, one small decision at a time, with progressive disclosure.

Internal migration details shall not be exposed to the user during normal project loading.

Loading an older OA project shall continue the project rather than forcing the user through a migration wizard when migration is deterministic and lossless.

The interface shall not require the user to choose Arcadia or UAF before they can model.

Methodology-specific commands, validation, terminology, or help shall only appear when the relevant methodology context is explicitly active or when operating through a clearly identified legacy compatibility path.

Business terminology and Operational terminology shall not be collapsed into one ambiguous user-facing term.

In particular, the existing generic UI word "goal" shall not be used in a way that silently equates Operational Capability with Business Objective or Desired Outcome.

---

## 6. Deterministic / AI boundary

### Deterministic responsibilities

The deterministic layer remains responsible for:

- persistent graph mutation;
- node and relationship validation;
- ID creation and preservation;
- project-mode metadata;
- file-format validation;
- backward-compatible migration;
- canonical invariants;
- save/load;
- provenance preservation;
- methodology-boundary enforcement.

### AI / LLM responsibilities

LLMs may:

- interpret user language;
- propose classifications;
- identify candidate concepts;
- explain alternatives;
- suggest relationships;
- later classify document passages.

LLMs may not:

- select a methodology for the user;
- write directly to the canonical graph;
- convert an Operational Capability to a Business Objective or Desired Outcome;
- create Business↔Operational relationships without confirmation;
- hide semantic mismatches;
- perform project migration by generating replacement semantic content.

### Explicit prohibition

The LLM must not mutate the persistent model directly or convert an unconfirmed inference into a canonical fact.

---

## 7. Data and model impact

```text
[x] ontology / semantic registry
[x] graph nodes
[x] graph relations — compatibility and validation only in Wave 1
[x] persistent attributes
[ ] new decomposition/composition semantics
[x] existing scenarios preserved
[x] validation
[x] save/load compatibility
[x] undo/revision compatibility
[ ] diagram semantic redesign
[ ] knowledge graph / SHACL redesign
[x] SysML v2 boundary protection
[x] SAM boundary protection
```

The current NetworkX `MultiDiGraph` remains the persistent implementation.

Wave 1 does not require migration to RDF, a database, or another graph technology.

The current internal class name `OAGraph` may remain temporarily as a compatibility API. Its name must not determine or constrain canonical semantics.

### Canonical project metadata contract

New canonical projects shall use, at minimum, the following graph metadata semantics:

```json
{
  "model": "Canonical Business + Operational Analysis",
  "model_mode": "canonical",
  "methodology": null,
  "mbse_app_format": "mbse-app-canonical-business-operational",
  "mbse_app_version": 2
}
```

`model_name` remains the user-supplied project name when present.

The `methodology` field being null is a valid state, not an error and not a gap.

---

## 8. Application/UI impact

```text
[x] terminal/guided runtime initialization
[x] web worker initialization
[x] model load/resume
[x] model export
[x] model state API
[x] help/guidance terminology where Arcadia is currently implicit
[ ] major web layout redesign
[ ] methodology-selection UI
[ ] document UI
```

The existing conversation-first browser architecture shall be preserved.

---

## 9. Compatibility and migration

### New canonical format

New projects shall be persisted as:

- format: `mbse-app-canonical-business-operational`
- version: `2`
- model mode: `canonical`
- methodology: `null`

Canonical project metadata shall identify the model as `Canonical Business + Operational Analysis` rather than `Arcadia Operational Analysis`.

### Legacy formats

The loader shall continue to accept existing Operational Analysis JSON projects, including projects that:

- identify `Arcadia Operational Analysis` in graph metadata;
- use `mbse-app-operational-analysis`;
- contain version 1 metadata;
- predate explicit format metadata but otherwise satisfy the supported legacy OA schema.

### Migration behavior

Legacy migration shall be deterministic and must not use an LLM.

Migration shall:

- preserve node IDs;
- preserve node types;
- preserve relationship types;
- preserve edge keys where supplied;
- preserve names;
- preserve characteristics;
- preserve confirmation attributes;
- preserve classification metadata;
- preserve provenance;
- preserve scenarios;
- preserve other supported non-presentation node, edge, and graph attributes;
- replace project-format identity with the canonical v2 metadata contract;
- optionally retain explicit source-format provenance indicating that the project was loaded from the legacy OA format.

Migration shall not:

- convert `OperationalCapability` into `BusinessObjective` or `DesiredOutcome`;
- create Business concepts;
- create Business↔Operational relationships;
- reinterpret existing relationships;
- call an LLM;
- require methodology selection.

A migrated legacy project is a valid Canonical Mode project containing operational semantics.

### Existing SysML/SAM projections

Current Arcadia/SAM-specific projection implementations shall remain available as compatibility code.

They shall not be presented as the canonical SysML projection introduced by this feature.

A canonical project containing semantics unsupported by the existing projection must remain editable and persistable even when no valid downstream projection can currently be produced.

---

## 10. Acceptance criteria

1. Given a fresh project, when it is created, then its graph metadata identifies Canonical Mode, canonical format version 2, and no selected methodology.

2. Given a canonical project, when Business and Operational concepts are added through deterministic model operations, then both kinds of concepts can coexist in the same persistent NetworkX graph.

3. Given a canonical project, when it is saved and loaded, then stable IDs, relationships, persistent attributes, provenance, graph metadata, and Canonical Mode are preserved.

4. Given an existing OA JSON project, when it is loaded, then it is accepted and migrated deterministically without semantic data loss.

5. Given an existing `OperationalCapability`, when its legacy project is loaded, then it remains an `OperationalCapability`.

6. Legacy migration shall not generate a `BusinessObjective`, `DesiredOutcome`, or any other Business element.

7. Absence of a methodology shall not produce a model validation error.

8. Existing deterministic graph validation remains the only persistent write authority.

9. No LLM code path can persist a canonical fact without the existing validation and confirmation boundary.

10. Existing operational-only projects retain their nodes, edges, characteristics, scenarios, IDs, and supported attributes after a load/save cycle.

11. Existing Operational Scenario representation and behavior remain unchanged in Wave 1 unless a later explicit semantic decision supersedes them.

12. Existing Next Best Question behavior for supported operational-only models remains regression compatible until its planned Wave 2 generalization.

13. Existing SysML/SAM modules remain covered by their current regression tests.

14. Canonical model editing and persistence do not fail merely because the current SysML/SAM projection does not support a canonical concept.

15. Wave 1 introduces no Business relation semantics that are absent from this specification.

---

## 11. Test plan

### Focused unit/contract tests

Add canonical semantic-registry tests covering the Business concept identities and the preserved Operational concept identities.

Extend model I/O tests with:

- canonical v2 validation and round-trip;
- Canonical Mode metadata;
- Business + Operational coexistence;
- legacy v1 loading;
- legacy files without explicit format metadata;
- ID preservation;
- relationship and edge-key preservation;
- arbitrary provenance/persistent attribute preservation;
- `OperationalCapability` non-conversion;
- migration without creation of Business nodes;
- methodology null accepted as valid.

Add canonical graph tests verifying deterministic add/update/relation behavior remains authoritative.

### Compatibility tests

Retain and run the existing focused tests for:

- Next Best Question;
- Operational Scenario;
- SysML v2;
- SysML Level 1;
- SAM full projection.

Add a regression test showing that canonical-only unsupported content does not prevent the model from being edited or persisted.

### Web integration

When the runtime-decoupling slice is implemented, test:

```text
fresh session
→ Canonical Mode
→ deterministic modification
→ autosave
→ export
→ load
→ resume
```

and:

```text
legacy OA JSON
→ load
→ deterministic migration
→ continue editing
→ canonical export
```

### E2E

When browser-visible canonical initialization is implemented, add or update one narrow browser test demonstrating that a fresh project starts without methodology selection and survives save/load.

### Local regression

Run focused tests first.

At a meaningful Wave 1 checkpoint run:

```bash
python -m pytest -q
```

Run relevant Playwright E2E locally when browser-visible behavior changes.

GitHub CI is not required for intermediate implementation steps. Trigger CI only at a meaningful integration checkpoint.

---

## 12. Implementation notes

Wave 1 shall use an incremental compatibility seam.

Recommended direction:

1. introduce a methodology-independent canonical semantic registry;
2. retain `ontology.py` temporarily as a compatibility facade for existing imports;
3. move canonical project identity and supported core concept identities behind that facade;
4. retain the current `OAGraph` API temporarily to avoid a repository-wide rename;
5. migrate persistence through explicit deterministic format handling rather than rebuilding graphs;
6. decouple mandatory Arcadia knowledge initialization from Canonical Mode in a later vertical slice;
7. prevent automatic Arcadia/SAM-specific projection from becoming a prerequisite for canonical editing.

### First implementation slice — Wave 1A

Wave 1A is intentionally limited to:

- canonical semantic registry;
- compatibility exports through the current ontology boundary;
- Canonical Mode graph metadata;
- canonical file format/version 2;
- deterministic legacy OA → canonical v2 migration;
- Business + Operational node coexistence at the persistent graph layer;
- save/load preservation;
- focused tests.

Wave 1A shall not:

- add Business relations;
- change Operational Scenario representation;
- generalize the Next Best Question engine;
- modify methodology adapters;
- redesign SysML/SAM;
- implement document intake;
- redesign the browser interaction flow.

No adapter framework shall be implemented as part of Wave 1A.

---

## 13. Risks

### Semantic ambiguity

The target conceptual model contains concepts whose persistent representation has not yet been agreed, including Operational Role, Operational Exchange, Communication Mean, Operational Scenario, Evidence, Provenance, State, Mode, Situation, Configuration, Event, Environment, Assumption, Constraint, and Measure.

Wave 1 must not settle those questions accidentally through implementation convenience.

### Backward compatibility

Existing OA JSON exists in more than one metadata state. Migration detection must therefore use explicit format metadata where present and conservative structural recognition where it is absent.

### Duplicated source of truth

Canonical content must not be duplicated into an Arcadia representation during normal editing.

### UI terminology

The word "goal" currently represents Operational Capability. Introducing Business Objective and Desired Outcome makes that shortcut potentially ambiguous.

### Projection mismatch

Existing SysML/SAM implementations are narrower than the future canonical model. Unsupported canonical semantics must be reported or deferred rather than silently omitted as though full projection had occurred.

---

## 14. Definition of done

- [ ] Canonical Model is the persistent authority.
- [ ] Fresh projects start in Canonical Mode.
- [ ] No methodology selection is required.
- [ ] Business and Operational concepts can coexist.
- [ ] Existing operational semantics remain available.
- [ ] Save/load preserves IDs.
- [ ] Save/load preserves relationships and edge keys.
- [ ] Save/load preserves provenance and persistent attributes.
- [ ] Legacy OA JSON loads successfully.
- [ ] Legacy migration does not create Business concepts.
- [ ] `OperationalCapability` remains `OperationalCapability`.
- [ ] Arcadia knowledge is not mandatory for Canonical Mode before Wave 1 is complete.
- [ ] SysML/SAM is not mandatory for Canonical Mode before Wave 1 is complete.
- [ ] deterministic write barrier is preserved.
- [ ] explicit human confirmation is preserved.
- [ ] no duplicated semantic source of truth is introduced.
- [ ] relevant focused local tests pass.
- [ ] full local regression passes at a meaningful Wave 1 checkpoint.
- [ ] relevant local browser E2E passes when browser-visible behavior changes.
- [ ] documentation reflects the methodology-independent product direction.
