"""M2: Structured fact memory for Group G14.

Extracts typed legal case facts (section, act, case, date, offence, party, location,
amount, claim) from user turns, handles user corrections by superseding prior entries
of the same fact type, scores stored facts with the Lecture 10 composite formula
(relevance + recency + importance) on read(), and injects key fact terms into
`retrieval_hint` so BM25 retrieval resolves multi-turn references accurately.
"""
from __future__ import annotations

import re
from typing import Callable

from .base import Memory, MemoryRead

_STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "in", "on", "at", "to", "for",
    "of", "and", "or", "that", "this", "it", "my", "i", "me", "we", "our", "you",
    "your", "what", "which", "who", "when", "where", "how", "does", "do", "did",
    "has", "have", "had", "be", "been", "with", "from", "by", "as", "about",
    "into", "please", "can", "could", "would", "should", "tell", "explain", "based",
    "earlier", "first", "message", "issue", "section", "act", "law", "applies",
}

_TYPE_IMPORTANCE = {
    "section": 0.95,
    "act": 0.92,
    "case": 0.90,
    "date": 0.88,
    "offence": 0.85,
    "amount": 0.78,
    "party": 0.75,
    "location": 0.70,
    "claim": 0.68,
}

_CORRECTION_RE = re.compile(
    r"\b(?:actually|sorry|correction|i meant|instead of|rather than|not\s+(?:on\s+)?[A-Z0-9]|"
    r"wrong\s+(?:date|section|act|year|amount|name)|changed\s+to|updated\s+to)\b",
    re.I,
)

_DATE_RE = re.compile(
    r"\b(?:\d{4}-\d{2}-\d{2}|\d{1,2}\s+(?:January|February|March|April|May|June|July|August|"
    r"September|October|November|December)\s+\d{4}|(?:January|February|March|April|May|June|"
    r"July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}|\d{1,2}/\d{1,2}/\d{2,4})\b",
    re.I,
)

_SECTION_RE = re.compile(r"\bSection\s+(\d+[A-Za-z\-]*)\b", re.I)
_ACT_RE = re.compile(
    r"\b([A-Z][A-Za-z\s,()]+?(?:Act|Ordinance|Code|Order|Rules),?\s*(?:18|19|20)\d{2})\b"
)
_DOC_ID_RE = re.compile(r"\b([A-Z]{2,6}-\d+[A-Za-z0-9\-]*)\b")
_AMOUNT_RE = re.compile(r"\b(?:Rs\.?|PKR|USD|\$)\s?[\d,]+(?:\.\d+)?\b", re.I)
_OFFENCE_RE = re.compile(
    r"\b(?:dispute\s+(?:about|regarding|over)|accused\s+of|charged\s+with|offence\s+of|"
    r"case\s+of|issue\s+(?:of|regarding)|matter\s+(?:of|involving))\s+([^.,;?!]{4,90})",
    re.I,
)
_PARTY_RE = re.compile(
    r"\b(?:my\s+(?:neighbour|neighbor|landlord|tenant|employer|employee|spouse|husband|wife|"
    r"brother|sister|partner|business\s+partner|client|contractor)|the\s+(?:other\s+party|"
    r"accused|complainant|petitioner|respondent|defendant|plaintiff|seller|buyer))\b",
    re.I,
)
_LOCATION_RE = re.compile(
    r"\b(?:in|at|from)\s+(Karachi|Lahore|Islamabad|Rawalpindi|Peshawar|Quetta|Multan|"
    r"Faisalabad|Hyderabad|Sukkur|Sindh|Punjab|KPK|Balochistan)\b",
    re.I,
)


def _tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 2 and w not in _STOPWORDS}


class FactMemory(Memory):
    code = "M2"
    backend = None
    seed = 13

    def __init__(self):
        self.facts: dict[str, list[dict]] = {}
        self._turn_counter: dict[str, int] = {}

    def reset(self, session_id: str) -> None:
        self.facts[session_id] = []
        self._turn_counter[session_id] = 0

    def _extract_candidates(self, user_msg: str) -> list[tuple[str, str]]:
        """Extract typed (fact_type, value) candidates from a user message.
        Never extracts from retrieved documents, tool outputs, or unverified bot guesses."""
        found: list[tuple[str, str]] = []
        msg = user_msg.strip()
        if not msg:
            return found

        # If message contains "X, not Y", strip the negated clause before extracting
        cleaned = re.sub(r",?\s*\bnot\s+[^.,;?!]+", "", msg, flags=re.I)

        for m in _SECTION_RE.finditer(cleaned):
            found.append(("section", f"Section {m.group(1)}"))
        for m in _ACT_RE.finditer(cleaned):
            found.append(("act", " ".join(m.group(1).split())))
        for m in _DOC_ID_RE.finditer(cleaned):
            found.append(("case", m.group(1)))
        for m in _DATE_RE.finditer(cleaned):
            found.append(("date", m.group(0).strip()))
        for m in _AMOUNT_RE.finditer(cleaned):
            found.append(("amount", m.group(0).strip()))
        for m in _OFFENCE_RE.finditer(cleaned):
            val = " ".join(m.group(1).split()).strip(" .")
            val = re.sub(r"\s+that\s+(?:happened|arose|occurred).*$", "", val, flags=re.I)
            if len(val) >= 4:
                found.append(("offence", val))
        for m in _PARTY_RE.finditer(cleaned):
            found.append(("party", " ".join(m.group(0).lower().split())))
        for m in _LOCATION_RE.finditer(cleaned):
            found.append(("location", m.group(1).title()))

        # Fallback: if no structured entity matched and message is substantive (not filler),
        # store a concise claim fact if it states a concrete circumstance.
        if not found and len(_tokens(cleaned)) >= 4 and not cleaned.endswith("?"):
            if not re.match(r"^(?:please|thank|ok|okay|got it|keep your answer)", cleaned, re.I):
                found.append(("claim", cleaned[:140]))

        # Deduplicate while preserving order
        deduped: list[tuple[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for item in found:
            key = (item[0], item[1].lower())
            if key not in seen:
                seen.add(key)
                deduped.append(item)
        return deduped

    def write(self, session_id: str, turn: int, user_msg: str, answer, state: dict) -> list[dict]:
        if session_id not in self.facts:
            self.reset(session_id)
        self._turn_counter[session_id] = max(self._turn_counter.get(session_id, 0), turn)

        candidates = self._extract_candidates(user_msg)
        is_correction = bool(_CORRECTION_RE.search(user_msg))
        table = self.facts[session_id]
        written_now: list[dict] = []

        for ftype, value in candidates:
            importance = _TYPE_IMPORTANCE.get(ftype, 0.65)
            if is_correction:
                importance = min(1.0, importance + 0.05)

            # Replace older facts of the same type when corrected, or for single-valued slots
            # (date, section, act, amount, offence) when updated by the user.
            single_value_types = {"date", "section", "act", "amount", "offence"}
            if is_correction or ftype in single_value_types:
                table[:] = [row for row in table if row["type"] != ftype]
            else:
                table[:] = [
                    row for row in table
                    if not (row["type"] == ftype and row["value"].lower() == value.lower())
                ]

            record = {
                "type": ftype,
                "value": value,
                "turn": turn,
                "importance": round(importance, 3),
                "corrected": is_correction,
            }
            table.append(record)
            written_now.append(dict(record))

        return written_now

    def _score_fact(self, row: dict, query_toks: set[str], current_turn: int) -> float:
        """Lecture 10 memory scoring: 0.45 * relevance + 0.30 * recency + 0.25 * importance."""
        fact_toks = _tokens(f"{row['type']} {row['value']}")
        if query_toks and fact_toks:
            overlap = len(query_toks & fact_toks) / len(query_toks | fact_toks)
            # Boost high-priority case anchors (section/act/offence/date) on follow-up questions
            anchor_boost = 0.35 if row["type"] in {"section", "act", "offence", "date", "case"} else 0.10
            relevance = min(1.0, overlap + anchor_boost)
        else:
            relevance = 0.50 if row["type"] in {"section", "act", "offence", "date", "case"} else 0.25

        age = max(0, current_turn - row["turn"])
        recency = 1.0 / (1.0 + 0.25 * age)
        importance = float(row.get("importance", 0.70))
        return round(0.45 * relevance + 0.30 * recency + 0.25 * importance, 4)

    def read(self, session_id: str, query: str, budget_tokens: int,
             count_tokens: Callable[[str], int]) -> MemoryRead:
        table = self.facts.get(session_id, [])
        if not table:
            return MemoryRead(text="", doc_ids=[], items=[], retrieval_hint="")

        current_turn = self._turn_counter.get(session_id, 1) + 1
        q_toks = _tokens(query)

        scored: list[dict] = []
        for row in table:
            s = self._score_fact(row, q_toks, current_turn)
            item = dict(row)
            item["score"] = s
            scored.append(item)

        # Highest composite score first; break ties by most recent turn
        scored.sort(key=lambda r: (r["score"], r["turn"]), reverse=True)

        lines: list[str] = []
        kept_items: list[dict] = []
        doc_ids: list[str] = []
        hint_parts: list[str] = []
        used_tokens = 0

        for item in scored:
            line = f"- [{item['type']}] {item['value']} (turn {item['turn']}, score={item['score']:.2f})"
            cost = count_tokens(line) + 1
            if used_tokens + cost > budget_tokens:
                continue
            lines.append(line)
            kept_items.append(item)
            used_tokens += cost

            if item["type"] == "case":
                doc_ids.append(item["value"])
            if item["type"] in {"section", "act", "offence", "case", "date"}:
                hint_parts.append(item["value"])

        # Deduplicate retrieval hint tokens while preserving priority order
        seen_h: set[str] = set()
        clean_hints: list[str] = []
        for h in hint_parts:
            if h.lower() not in seen_h:
                seen_h.add(h.lower())
                clean_hints.append(h)

        return MemoryRead(
            text="\n".join(lines),
            doc_ids=doc_ids,
            items=kept_items,
            retrieval_hint=" ".join(clean_hints[:6]),
        )