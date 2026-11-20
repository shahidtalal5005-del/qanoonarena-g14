"""Runtime citation monitor (Step 4, item 2).

Policy:
- Any citation not present in `allowed_ids` (retrieved docs + memory docs) or not in `corpus`
  is treated as ungrounded and stripped from `answer.citations` (`action = "dropped"`).
- If the model originally cited sources (`had_cites == True`) and NONE of them were grounded,
  we block the ungrounded answer and force abstention (`action = "blocked"`).
"""
from __future__ import annotations

from harness.answer import Answer


def check(answer: Answer, allowed_ids: set[str], corpus) -> tuple[Answer, dict]:
    allowed_base = {a.split("@")[0] for a in allowed_ids}
    original_cites = list(answer.citations)
    grounded: list[str] = []
    ungrounded: list[str] = []

    for c in original_cites:
        base = c.split("@")[0]
        in_allowed = (c in allowed_ids) or (base in allowed_base)
        in_corpus = corpus.exists(c) or corpus.exists(base)
        if in_allowed and in_corpus:
            if c not in grounded:
                grounded.append(c)
        else:
            ungrounded.append(c)

    if not ungrounded:
        action = "none"
    elif original_cites and not grounded and not answer.abstain:
        answer = Answer(
            answer="I am not sure. The retrieved legal documents do not support a verified citation for this question.",
            citations=[],
            abstain=True,
            parse_ok=answer.parse_ok,
        )
        action = "blocked"
    else:
        answer = Answer(
            answer=answer.answer,
            citations=grounded,
            abstain=answer.abstain,
            parse_ok=answer.parse_ok,
        )
        action = "dropped"

    flags = {
        "ungrounded": ungrounded,
        "n_ungrounded": len(ungrounded),
        "action": action,
    }
    return answer, flags