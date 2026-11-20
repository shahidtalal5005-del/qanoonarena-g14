import json, re
from harness.common import Corpus, read_jsonl

c = Corpus()
used = {
    cite
    for fn in ["harness/data/dev.jsonl", "harness/data/smoke.jsonl", "harness/data/example_sessions.jsonl"]
    for s in read_jsonl(fn)
    for t in s["turns"]
    if t.get("gold")
    for cite in t["gold"].get("citations", [])
}

statutes, amended, judgments = [], [], []
for did, doc in sorted(c.docs.items()):
    if did in used or "Omitted" in doc.text or len(doc.text) < 180:
        continue
    title = (getattr(doc, "title", "") or "").strip(" .[]")
    if did.startswith("SHC-") and doc.meta.get("outcome") and title and len(doc.text) > 400:
        judgments.append(doc)
    elif "Amendment notes:" in doc.text:
        m = re.search(r"\[Amendment notes:.*?((?:18|19|20)\d{2}).*?\]", doc.text, re.S)
        if m:
            amended.append((doc, m.group(1), m.group(0)))
    elif not did.startswith("SHC-") and len(title) >= 12 and not title.lower().startswith("repealed"):
        statutes.append(doc)

def q(txt, n=130):
    return " ".join(txt.split())[:n].rsplit(" ", 1)[0]

def gold(ans, kws, cites, ev, mem=False):
    return {
        "answer": ans,
        "answer_keywords": kws,
        "citations": cites,
        "exact_version": False,
        "abstain": len(cites) == 0,
        "memory_dependent": mem,
        "depends_on_turns": [1] if mem else [],
        "as_of": None,
        "evidence": ev,
    }

sessions = []

for i, d in enumerate(statutes[:2], 1):
    act, sec, title = d.meta["act"], d.meta["section"], d.title.strip(" .[]")
    sessions.append({
        "session_id": f"G14-T1-0{i}",
        "type": "T1",
        "author": "G14",
        "turns": [{
            "user": f"What does Section {sec} of the {act} provide?",
            "gold": gold(f"Section {sec} of the {act} deals with {title}.", [str(sec)], [d.doc_id], [{"doc_id": d.doc_id, "quote": q(d.text)}]),
        }],
    })

for i, d in enumerate(judgments[:2], 1):
    title, date, out = d.title.strip(), d.meta.get("date", ""), d.meta["outcome"].strip()
    oq = (d.meta.get("outcome_quote") or "").strip()
    if len(oq) < 20 or oq not in d.text:
        oq = q(d.text[-450:])
    date_part = f" decided on {date}" if date else ""
    sessions.append({
        "session_id": f"G14-T2-0{i}",
        "type": "T2",
        "author": "G14",
        "turns": [{
            "user": f"What was the final decision of the Sindh High Court in {title}{date_part}?",
            "gold": gold(f"In {title}, the court's decision was: {out}.", [out.split()[0].lower()], [d.doc_id], [{"doc_id": d.doc_id, "quote": oq}]),
        }],
    })

for i, d in enumerate(statutes[2:4], 1):
    act, sec, title = d.meta["act"], d.meta["section"], d.title.strip(" .[]").lower()
    sessions.append({
        "session_id": f"G14-T3-0{i}",
        "type": "T3",
        "author": "G14",
        "turns": [
            {"user": f"I need legal guidance regarding a dispute about {title} that happened on 14 February 2025.", "gold": None},
            {"user": "The other party lives in Karachi and refuses to resolve it.", "gold": None},
            {"user": "I have saved all relevant documents and messages from that time.", "gold": None},
            {
                "user": f"Based on the issue I mentioned in my first message, which section of the {act} applies?",
                "gold": gold(f"Section {sec} of the {act} applies to {title}.", [str(sec)], [d.doc_id], [{"doc_id": d.doc_id, "quote": q(d.text)}], True),
            },
        ],
    })

for i, (d, yr, note) in enumerate(amended[:2], 1):
    act, sec = d.meta["act"], d.meta["section"]
    sessions.append({
        "session_id": f"G14-T4-0{i}",
        "type": "T4",
        "author": "G14",
        "turns": [
            {"user": f"I am preparing a case note on Section {sec} of the {act}.", "gold": None},
            {"user": "Please keep your answer brief and direct.", "gold": None},
            {"user": "I need the exact statutory details for my file.", "gold": None},
            {
                "user": "Has this section been amended, and in which year was that amendment enacted?",
                "gold": gold(f"Yes, Section {sec} of the {act} was amended in {yr}.", [str(yr)], [d.doc_id], [{"doc_id": d.doc_id, "quote": note}], True),
            },
        ],
    })

for i, p in enumerate([
    "What does Section 999 of the Pakistan Penal Code, 1860 state regarding cryptocurrency fraud?",
    "What penalty does Section 450 of the Contract Act, 1872 impose for late delivery of software?",
], 1):
    sessions.append({
        "session_id": f"G14-T5-0{i}",
        "type": "T5",
        "author": "G14",
        "turns": [{
            "user": p,
            "gold": gold("I am not sure. The provided legal documents do not contain this provision.", [], [], []),
        }],
    })

with open("contrib/G14.jsonl", "w", encoding="utf-8") as f:
    for s in sessions:
        f.write(json.dumps(s, ensure_ascii=False) + "\n")
print("Wrote contrib/G14.jsonl")