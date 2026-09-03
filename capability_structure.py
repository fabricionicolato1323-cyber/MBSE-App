from __future__ import annotations

import re
from dataclasses import dataclass


_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z'-]*|[,;]")


@dataclass(frozen=True)
class ParticipantLexeme:
    lexical_form: str
    suggested_concept: str | None = None
    suggested_nature: str = "unspecified"


@dataclass(frozen=True)
class StructuralPolicy:
    max_accepted_tokens: int = 40
    max_candidate_predicates: int = 4
    max_complexity_score: int = 5


@dataclass(frozen=True)
class StructuralLexicon:
    predicates: frozenset[str]
    coordinators: frozenset[str]
    mention_prepositions: frozenset[str]
    clause_markers: frozenset[str]
    determiners: frozenset[str]
    qualifiers: frozenset[str]
    outcome_nouns: frozenset[str]
    participant_lexemes: tuple[ParticipantLexeme, ...] = ()
    policy: StructuralPolicy = StructuralPolicy()


@dataclass(frozen=True)
class CapabilityMention:
    text: str
    source: str
    suggested_concept: str | None = None
    suggested_nature: str = "unspecified"


@dataclass(frozen=True)
class CapabilityStructuralAnalysis:
    source_text: str
    normalized_text: str
    predicate_texts: tuple[str, ...]
    capability_candidates: tuple[str, ...]
    mentions: tuple[CapabilityMention, ...]
    complexity_score: int
    requires_simplification: bool
    confidence: str

    @property
    def has_multiple_capabilities(self) -> bool:
        return len(self.capability_candidates) > 1


@dataclass(frozen=True)
class _Token:
    text: str
    normalized: str


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _tokenize(value: str) -> list[_Token]:
    return [
        _Token(match.group(0), match.group(0).casefold())
        for match in _TOKEN_RE.finditer(value)
    ]


def _join_tokens(tokens: list[_Token]) -> str:
    text = " ".join(token.text for token in tokens if token.text != ";")
    text = re.sub(r"\s+,\s*", ", ", text)
    return _normalize_text(text).strip(" ,;")


def _word_count(tokens: list[_Token]) -> int:
    return sum(token.text not in {",", ";"} for token in tokens)


def _previous_word_index(tokens: list[_Token], index: int) -> int | None:
    for current in range(index - 1, -1, -1):
        if tokens[current].text not in {",", ";"}:
            return current
    return None


def _independent_predicate_indices(
    tokens: list[_Token],
    lexicon: StructuralLexicon,
) -> tuple[list[int], list[int]]:
    predicate_indices = [
        index
        for index, token in enumerate(tokens)
        if token.normalized in lexicon.predicates
    ]
    if not predicate_indices:
        return [], []

    first = predicate_indices[0]
    independent = [first]
    non_independent: list[int] = []

    for index in predicate_indices[1:]:
        previous = _previous_word_index(tokens, index)
        directly_coordinated = (
            previous is not None
            and tokens[previous].normalized in lexicon.coordinators
        )
        semicolon_before = index > 0 and tokens[index - 1].text == ";"
        if directly_coordinated or semicolon_before:
            independent.append(index)
        else:
            non_independent.append(index)

    return independent, non_independent


def _segment_capabilities(
    tokens: list[_Token],
    predicate_indices: list[int],
    coordinators: frozenset[str],
) -> tuple[str, ...]:
    if len(predicate_indices) <= 1:
        return (_join_tokens(tokens),) if tokens else ()

    segments: list[list[_Token]] = []
    for offset, start in enumerate(predicate_indices):
        if offset + 1 < len(predicate_indices):
            next_predicate = predicate_indices[offset + 1]
            end = next_predicate
            previous = _previous_word_index(tokens, next_predicate)
            if previous is not None and tokens[previous].normalized in coordinators:
                end = previous
            while end > start and tokens[end - 1].text in {",", ";"}:
                end -= 1
        else:
            end = len(tokens)
        segments.append(tokens[start:end])

    # A coordinated verb can share the following object, e.g. "A and B item".
    # If a segment contains only its predicate, inherit only the following
    # segment's post-predicate tail. This is a grammatical rule, not domain data.
    for index in range(len(segments) - 1):
        words = [token for token in segments[index] if token.text not in {",", ";"}]
        if len(words) != 1:
            continue
        next_words = [
            token for token in segments[index + 1]
            if token.text not in {",", ";"}
        ]
        if len(next_words) > 1:
            segments[index] = [*segments[index], *next_words[1:]]

    return tuple(
        candidate
        for candidate in (_join_tokens(segment) for segment in segments)
        if candidate
    )


def _strip_noise(
    tokens: list[_Token],
    lexicon: StructuralLexicon,
) -> list[_Token]:
    cleaned = list(tokens)
    while cleaned and (
        cleaned[0].normalized in lexicon.determiners
        or cleaned[0].normalized in lexicon.qualifiers
        or cleaned[0].text in {",", ";"}
    ):
        cleaned.pop(0)
    while cleaned and cleaned[-1].text in {",", ";"}:
        cleaned.pop()
    return cleaned


def _split_coordinated_mentions(
    tokens: list[_Token],
    lexicon: StructuralLexicon,
) -> list[str]:
    groups: list[list[_Token]] = [[]]
    for token in tokens:
        if token.text == "," or token.normalized in lexicon.coordinators:
            if groups[-1]:
                groups.append([])
            continue
        groups[-1].append(token)

    result: list[str] = []
    for group in groups:
        cleaned = _strip_noise(group, lexicon)
        text = _join_tokens(cleaned)
        if not text:
            continue
        normalized = text.casefold()
        if normalized in lexicon.outcome_nouns or normalized in lexicon.qualifiers:
            continue
        result.append(text)
    return result


def _lexeme_mentions(
    tokens: list[_Token],
    lexicon: StructuralLexicon,
) -> list[CapabilityMention]:
    word_tokens = [token for token in tokens if token.text not in {",", ";"}]
    words = [token.normalized for token in word_tokens]
    matches: list[tuple[int, int, CapabilityMention]] = []

    ordered = sorted(
        lexicon.participant_lexemes,
        key=lambda item: (-len(item.lexical_form.split()), item.lexical_form.casefold()),
    )
    for lexeme in ordered:
        phrase = [part.casefold() for part in lexeme.lexical_form.split() if part]
        if not phrase:
            continue
        width = len(phrase)
        for start in range(0, len(words) - width + 1):
            if words[start : start + width] != phrase:
                continue
            text = " ".join(token.text for token in word_tokens[start : start + width])
            matches.append(
                (
                    start,
                    start + width,
                    CapabilityMention(
                        text=text,
                        source="lexical_knowledge",
                        suggested_concept=lexeme.suggested_concept,
                        suggested_nature=lexeme.suggested_nature,
                    ),
                )
            )

    accepted: list[CapabilityMention] = []
    occupied: set[int] = set()
    for start, end, mention in matches:
        positions = set(range(start, end))
        if positions & occupied:
            continue
        occupied.update(positions)
        accepted.append(mention)
    return accepted


def _prepositional_mentions(
    tokens: list[_Token],
    lexicon: StructuralLexicon,
    independent_predicates: set[int],
) -> list[CapabilityMention]:
    result: list[CapabilityMention] = []
    for index, token in enumerate(tokens):
        if token.normalized not in lexicon.mention_prepositions:
            continue
        segment: list[_Token] = []
        for current in range(index + 1, len(tokens)):
            item = tokens[current]
            if current in independent_predicates:
                break
            if item.normalized in lexicon.mention_prepositions:
                break
            if item.normalized in lexicon.clause_markers or item.text == ";":
                break
            segment.append(item)
        for text in _split_coordinated_mentions(segment, lexicon):
            result.append(CapabilityMention(text=text, source="prepositional_structure"))
    return result


def _modifier_mentions(
    tokens: list[_Token],
    lexicon: StructuralLexicon,
    first_predicate: int | None,
) -> list[CapabilityMention]:
    if first_predicate is None:
        return []

    end = len(tokens)
    for index in range(first_predicate + 1, len(tokens)):
        if tokens[index].normalized in lexicon.mention_prepositions:
            end = index
            break

    outcome_index = None
    for index in range(end - 1, first_predicate, -1):
        if tokens[index].normalized in lexicon.outcome_nouns:
            outcome_index = index
            break
    if outcome_index is None:
        return []

    prefix = tokens[first_predicate + 1 : outcome_index]
    if not any(
        token.text == "," or token.normalized in lexicon.coordinators
        for token in prefix
    ):
        return []

    return [
        CapabilityMention(text=text, source="coordinated_modifier_structure")
        for text in _split_coordinated_mentions(prefix, lexicon)
    ]


def _dedupe_mentions(mentions: list[CapabilityMention]) -> tuple[CapabilityMention, ...]:
    seen: set[str] = set()
    result: list[CapabilityMention] = []
    for mention in mentions:
        key = _normalize_text(mention.text).casefold()
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(mention)
    return tuple(result)


def analyze_capability_structure(
    value: str,
    lexicon: StructuralLexicon,
) -> CapabilityStructuralAnalysis:
    normalized = _normalize_text(value)
    tokens = _tokenize(normalized)
    independent, non_independent = _independent_predicate_indices(tokens, lexicon)

    predicate_texts = tuple(tokens[index].text for index in independent)
    capability_candidates = _segment_capabilities(
        tokens,
        independent,
        lexicon.coordinators,
    )
    if not capability_candidates and normalized:
        capability_candidates = (normalized,)

    clause_hits = sum(
        token.normalized in lexicon.clause_markers
        for token in tokens
    )
    semicolons = sum(token.text == ";" for token in tokens)
    extra_predicates = max(0, len(independent) - 1)
    complexity_score = extra_predicates + len(non_independent) + clause_hits + semicolons

    policy = lexicon.policy
    requires_simplification = (
        _word_count(tokens) > policy.max_accepted_tokens
        or len(independent) > policy.max_candidate_predicates
        or (
            complexity_score > policy.max_complexity_score
            and len(independent) <= 1
        )
    )

    mentions = _dedupe_mentions(
        [
            *_lexeme_mentions(tokens, lexicon),
            *_prepositional_mentions(tokens, lexicon, set(independent)),
            *_modifier_mentions(
                tokens,
                lexicon,
                independent[0] if independent else None,
            ),
        ]
    )

    if requires_simplification:
        confidence = "low"
    elif independent:
        confidence = "high" if complexity_score <= 2 else "medium"
    else:
        confidence = "medium"

    return CapabilityStructuralAnalysis(
        source_text=value,
        normalized_text=normalized,
        predicate_texts=predicate_texts,
        capability_candidates=capability_candidates,
        mentions=mentions,
        complexity_score=complexity_score,
        requires_simplification=requires_simplification,
        confidence=confidence,
    )
