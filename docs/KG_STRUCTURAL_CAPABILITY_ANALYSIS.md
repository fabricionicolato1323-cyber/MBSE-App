# KG-Driven Structural Capability Analysis

## Purpose

Operational Capability input is analyzed without giving semantic authority to the local LLM.
The application separates linguistic structure from modeling knowledge:

```text
User capability text
        |
        v
Domain-neutral structural parser
        |
        v
Knowledge Graph structural vocabulary + policy
        |
        +--> predicate candidates
        +--> mention candidates
        +--> complexity / simplification decision
        |
        v
User confirmation
        |
        v
Existing deterministic write barrier
        |
        v
NetworkX project model
```

When AI is active, the same semantic path is used. The local LLM may only rephrase an already-decided question.

## No hardcoded application knowledge

Production Python and the base structural KG contain no application-specific participant, asset, stakeholder, industry, or scenario vocabulary.

The architectural rule is:

```text
STRUCTURE       -> algorithm
MODELING RULES  -> Knowledge Graph
DOMAIN KNOWLEDGE-> replaceable RDF data
USER FACTS      -> user confirmation
LLM             -> conversational wording only
```

Examples may appear in tests and documentation, but they must never become production special cases.

## Structural distinction

A single predicate with coordinated objects remains one capability candidate:

```text
<verb> <object A> and <object B>
```

Several independently coordinated predicates become multiple capability candidates:

```text
<verb A> <object A> and <verb B> <object B>
```

If one coordinated predicate omits a shared object, the structural parser may inherit the explicit following object before asking the user whether the candidates should be separated.

No separation is written to the project graph until the user confirms it.

## Mention discovery

Mention candidates can come from four domain-neutral sources:

- direct-object structure;
- prepositional structure;
- coordinated modifiers before an abstract outcome head;
- optional lexical Knowledge Graph data.

A mention is only a candidate. The normal participant classification and System-of-Interest boundary flow still runs before persistence.

## Complexity

The default structural policy is stored as RDF data in `knowledge_base/10_structural_language_lexicon.ttl`.
It currently defines maximum accepted tokens, maximum candidate predicates, and maximum complexity score.

Complexity is based on structure rather than raw sentence length alone. Independent predicates, subordinate-clause markers, non-independent predicate cues, and semicolons contribute to the score.

If the configured policy is exceeded and the parser cannot safely present a small decomposition, the app asks the user to express one main goal at a time.

## Replaceable lexical knowledge

Additional lexical or domain knowledge can be loaded without modifying Python:

```powershell
$env:MBSE_STRUCTURAL_KG_EXTENSIONS_PATH = "C:\path\to\extension.ttl"
python web_app.py
```

Multiple files can be supplied using the operating system path separator.

An extension can add `oa:ParticipantLexeme` resources, or extend generic structural cue classes such as `oa:PredicateCue` and `oa:OutcomeNounCue`.

Example schema for an external lexical item:

```turtle
@prefix oa: <https://github.com/fabricionicolato1323-cyber/MBSE-App/knowledge/arcadia/oa#> .

<urn:example:item> a oa:ParticipantLexeme ;
    oa:lexicalForm "<external lexical form>" ;
    oa:suggestedConcept "OperationalEntity" ;
    oa:suggestedNature "unspecified" .
```

The extension is data only. The user remains the authority for persistent model facts.

## Transient Knowledge Graph

Each analysis is materialized into a transient RDF graph containing:

- `oa:StructuralAnalysis`;
- `oa:PredicateCandidate`;
- `oa:MentionCandidate`;
- complexity and confidence metadata.

This transient graph is never merged into the approved Project Graph and never writes directly to NetworkX.
