# MEMORY.md — Group G14, memory type M2

## 1. What our memory stores
Our `FactMemory` (`agent/memory/m2_facts.py`) maintains a per-session structured table (`self.facts[session_id]`) of typed case facts extracted from user turns. Each row is a dictionary with five fields:
- `type`: one of `section` (importance 0.95), `act` (0.92), `case` (0.90), `date` (0.88), `offence` (0.85), `amount` (0.78), `party` (0.75), `location` (0.70), or `claim` (0.68).
- `value`: normalized string value of the extracted fact (e.g., `"Section 302"`, `"14 February 2025"`).
- `turn`: integer turn index when the fact was recorded or updated.
- `importance`: base schema priority in $[0.68, 1.0]$ (boosted by $+0.05$ on explicit user corrections).
- `corrected`: boolean flag indicating whether the entry superseded an earlier contradicted fact.

## 2. Write policy
| Question | Our rule |
| --- | --- |
| What is written to memory? | Structured legal case entities (`section`, `act`, `case`, `date`, `offence`, `amount`, `party`, `location`) and concise substantive `claim` statements stated by the user. |
| When is it written (every turn, only when a fact is found, ...)? | Executed in `memory_write` after each turn, writing rows **only when** regex/rule extractors find at least one candidate fact (`items_written >= 1`). |
| What is never written? (tool outputs, retrieved documents, the bot's guesses, ...) | Retrieved statute/judgment texts, BM25 scores, raw LLM outputs, unverified bot guesses, negated clauses (`"not X"`), and conversational filler (`"please keep your answer brief"`). |
| How is a new item scored before it is kept? (M2: relevance, recency, importance) | Candidate importance is assigned by schema type (`0.68`–`0.95`, $+0.05$ if corrected). On `read()`, every stored row is scored via the Lecture 10 composite formula: $\text{Score} = 0.45 \cdot \text{relevance}(q, f) + 0.30 \cdot \text{recency}(t, t_f) + 0.25 \cdot \text{importance}(f)$, where $\text{recency} = (1 + 0.25 \cdot \Delta t)^{-1}$ and $\text{relevance}$ combines query-fact Jaccard overlap with a legal-anchor boost ($+0.35$ for `section`/`act`/`offence`/`date`/`case`). |
| What happens when the user corrects an earlier fact? | Correction cues (`actually`, `sorry`, `not <X>`, `instead of`, `i meant`, `wrong date/section`) strip the negated value, set `corrected=True`, boost `importance` by $+0.05$, and replace any existing row of that fact type (and single-valued slots `date`, `section`, `act`, `amount`, `offence` overwrite stale values). |

## 3. Read policy
| Question | Our rule |
| --- | --- |
| What is read back for a new message? | All stored facts for `session_id` that fit within `memory_budget_tokens` (220 tokens), formatted as `- [<type>] <value> (turn <t>, score=<s.ss>)`. |
| How is it ordered or ranked? | Sorted descending by composite Lecture 10 score (`score`), breaking ties by most recent `turn`. |
| What is dropped first when it does not fit `memory_budget_tokens`? | Lowest-scoring facts (typically older, low-importance `location`, `party`, or generic `claim` rows) are skipped first while preserving high-scoring `section`, `act`, `date`, and `offence` anchors. |
| What do we add to `retrieval_hint`, and why? | Up to 6 deduplicated values from high-value anchor types (`section`, `act`, `offence`, `case`, `date`) are appended to `retrieval_hint` so `BM25Retriever` retrieves the exact statute or judgment on elliptical follow-ups (e.g., *"Which section applies to the issue I described earlier?"*). |

## 4. State versus memory
Transient turn artifacts—BM25 `hits`, full retrieved document texts, `messages`, `raw` model completions, token counts, and `cite_flags`—stay strictly inside LangGraph `TurnState` and JSONL traces so they never pollute the 220-token memory budget or propagate unverified model claims across turns. Only user-asserted case facts persist in `FactMemory` across turns.

## 5. Three example conversations

### Example 1: memory working normally
- **Turn 1 User:** `"I am researching Section 302 of the Pakistan Penal Code, 1860 regarding a dispute that happened on 14 February 2025."`
  - `memory_read`: `{"span": "memory_read", "memory": "M2", "mem_tokens": 0, "items_read": 0, "items": [], "text": ""}`
  - `memory_write`: `{"span": "memory_write", "memory": "M2", "items_written": 3, "items": [{"type": "section", "value": "Section 302", "turn": 1, "importance": 0.95, "corrected": false}, {"type": "act", "value": "Pakistan Penal Code, 1860", "turn": 1, "importance": 0.92, "corrected": false}, {"type": "date", "value": "14 February 2025", "turn": 1, "importance": 0.88, "corrected": false}]}`
- **Turn 2 User:** `"The other party lives in Karachi."`
  - `memory_read`: `{"span": "memory_read", "memory": "M2", "mem_tokens": 36, "items_read": 3, "items": [{"type": "section", "value": "Section 302", "turn": 1, "importance": 0.95, "corrected": false, "score": 0.635}, {"type": "act", "value": "Pakistan Penal Code, 1860", "turn": 1, "importance": 0.92, "corrected": false, "score": 0.6275}, {"type": "date", "value": "14 February 2025", "turn": 1, "importance": 0.88, "corrected": false, "score": 0.6175}], "text": "- [section] Section 302 (turn 1, score=0.64)\n- [act] Pakistan Penal Code, 1860 (turn 1, score=0.63)\n- [date] 14 February 2025 (turn 1, score=0.62)"}`
  - `memory_write`: `{"span": "memory_write", "memory": "M2", "items_written": 2, "items": [{"type": "party", "value": "the other party", "turn": 2, "importance": 0.75, "corrected": false}, {"type": "location", "value": "Karachi", "turn": 2, "importance": 0.7, "corrected": false}]}`
- **Turn 3 User:** `"What punishment does that section prescribe?"`
  - `memory_read`: `{"span": "memory_read", "memory": "M2", "mem_tokens": 58, "items_read": 5, "items": [{"type": "section", "value": "Section 302", "turn": 1, "importance": 0.95, "corrected": false, "score": 0.595}, {"type": "act", "value": "Pakistan Penal Code, 1860", "turn": 1, "importance": 0.92, "corrected": false, "score": 0.5875}, {"type": "date", "value": "14 February 2025", "turn": 1, "importance": 0.88, "corrected": false, "score": 0.5775}, {"type": "party", "value": "the other party", "turn": 2, "importance": 0.75, "corrected": false, "score": 0.4725}, {"type": "location", "value": "Karachi", "turn": 2, "importance": 0.7, "corrected": false, "score": 0.46}], "text": "- [section] Section 302 (turn 1, score=0.59)\n- [act] Pakistan Penal Code, 1860 (turn 1, score=0.59)\n- [date] 14 February 2025 (turn 1, score=0.58)\n- [party] the other party (turn 2, score=0.47)\n- [location] Karachi (turn 2, score=0.46)"}`
  - `memory_write`: `{"span": "memory_write", "memory": "M2", "items_written": 0, "items": []}`
- **Final Answer (Turn 3):** Grounded response citing `[PPC-302]` (`Pakistan Penal Code, 1860, section 302: Punishment of qatl-i-amd`), retrieved via `retrieval_hint="Section 302 Pakistan Penal Code, 1860 14 February 2025"`.

### Example 2: the user corrects an earlier fact
- **Turn 1 User:** `"My tenancy dispute in Lahore started on 3 March 2025 under Section 15."`
  - `memory_write`: `{"span": "memory_write", "memory": "M2", "items_written": 3, "items": [{"type": "section", "value": "Section 15", "turn": 1, "importance": 0.95, "corrected": false}, {"type": "date", "value": "3 March 2025", "turn": 1, "importance": 0.88, "corrected": false}, {"type": "location", "value": "Lahore", "turn": 1, "importance": 0.7, "corrected": false}]}`
- **Turn 2 User:** `"Sorry, it was 5 March 2025, not 3 March 2025."`
  - `memory_read`: `{"span": "memory_read", "memory": "M2", "mem_tokens": 31, "items_read": 3, "items": [{"type": "date", "value": "3 March 2025", "turn": 1, "importance": 0.88, "corrected": false, "score": 0.7975}, {"type": "section", "value": "Section 15", "turn": 1, "importance": 0.95, "corrected": false, "score": 0.7025}, {"type": "location", "value": "Lahore", "turn": 1, "importance": 0.7, "corrected": false, "score": 0.46}]}`
  - `memory_write`: `{"span": "memory_write", "memory": "M2", "items_written": 1, "items": [{"type": "date", "value": "5 March 2025", "turn": 2, "importance": 0.93, "corrected": true}]}`
- **Turn 3 User:** `"Summarize my case facts and applicable section."`
  - `memory_read`: `{"span": "memory_read", "memory": "M2", "mem_tokens": 31, "items_read": 3, "items": [{"type": "section", "value": "Section 15", "turn": 1, "importance": 0.95, "corrected": false, "score": 0.6625}, {"type": "date", "value": "5 March 2025", "turn": 2, "importance": 0.93, "corrected": true, "score": 0.63}, {"type": "location", "value": "Lahore", "turn": 1, "importance": 0.7, "corrected": false, "score": 0.42}], "text": "- [section] Section 15 (turn 1, score=0.66)\n- [date] 5 March 2025 (turn 2, score=0.63)\n- [location] Lahore (turn 1, score=0.42)"}`
- **Final Answer (Turn 3):** Uses the updated date `5 March 2025` (with `3 March 2025` cleanly overwritten) alongside `Section 15` and `Lahore`.

### Example 3: a case where our memory still fails, and why
- **Turn 1 User:** `"My neighbour blocked the shared lane outside my house last Tuesday."`
  - `memory_read`: `{"span": "memory_read", "memory": "M2", "mem_tokens": 0, "items_read": 0, "items": [], "text": ""}`
  - `memory_write`: `{"span": "memory_write", "memory": "M2", "items_written": 1, "items": [{"type": "party", "value": "my neighbour", "turn": 1, "importance": 0.75, "corrected": false}]}`
- **Turn 2 User:** `"Which provision covers this?"`
  - `memory_read`: `{"span": "memory_read", "memory": "M2", "mem_tokens": 10, "items_read": 1, "items": [{"type": "party", "value": "my neighbour", "turn": 1, "importance": 0.75, "corrected": false, "score": 0.4725}], "text": "- [party] my neighbour (turn 1, score=0.47)"}`
  - `memory_write`: `{"span": "memory_write", "memory": "M2", "items_written": 0, "items": []}`
- **Why it failed:** Our rule-based extractor captured `[party] my neighbour`, but missed both the relative temporal expression (`"last Tuesday"`) and the implicit legal offence (`"blocked the shared lane"` / public nuisance or wrongful restraint) because the sentence did not use explicit trigger phrases like `"dispute about"` or an absolute calendar date. Consequently, `retrieval_hint` was empty and the retriever could not locate the relevant easement or nuisance statute.