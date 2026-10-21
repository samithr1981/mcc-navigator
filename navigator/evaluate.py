"""Measure how well the text matching ranks the right MCC.

Two checks:
  * held-out terms: take each "included" merchant type of an MCC, hide it from the index, and see where its MCC ranks.
    This tests whether the method generalises beyond words it has seen. It uses the manual's own vocabulary, so it is
    easier than real merchant descriptions.
  * written cases: `tests/cases.csv`, merchant descriptions written by the developer with accepted MCCs.
    The synonyms were tuned while writing these, so treat the result as a regression check, not an independent benchmark.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

from .textmatch import Index, clean_desc, fold

ROOT = Path(__file__).resolve().parent.parent


def held_out(ix: Index, limit: int | None = None) -> dict:
    n = hit1 = hit3 = hit5 = 0
    misses = []
    for j, code in enumerate(ix.codes):
        m = ix.mccs[code]
        if len(m.included) < 2:
            continue
        for term in m.included:
            if len(fold(term)) < 4:
                continue
            # rebuild this MCC's description document without the term
            doc = fold(f"{m.title} {m.title} {' '.join(i for i in m.included if i != term)} {' '.join(i for i in m.included if i != term)}") + " " + clean_desc(m.description)
            drop = [k for k, e in enumerate(ix.entries) if e[0] == j and e[1] == fold(term)]
            res = ix.rank(term, top=5, doc_override={j: doc}, drop_entry=drop[0] if drop else None)
            codes = [r.code for r in res]
            n += 1
            hit1 += codes[:1] == [code]
            hit3 += code in codes[:3]
            hit5 += code in codes[:5]
            if code not in codes[:3] and len(misses) < 25:
                misses.append((term, code, codes[:3]))
            if limit and n >= limit:
                break
    return {"n": n, "top1": hit1 / n, "top3": hit3 / n, "top5": hit5 / n, "misses": misses}


def written_cases(ix: Index, path: Path | None = None) -> dict:
    path = path or ROOT / "tests" / "cases.csv"
    rows = list(csv.DictReader(open(path), delimiter="|"))
    n = t1 = t3 = t5 = 0
    misses = []
    for r in rows:
        ok = set(re.split(r"[,\s]+", r["accepted_mccs"].strip()))
        res = [m.code for m in ix.rank(r["description"], top=5)]
        n += 1
        t1 += res[0] in ok
        t3 += bool(ok & set(res[:3]))
        t5 += bool(ok & set(res[:5]))
        if not ok & set(res[:3]):
            misses.append((r["description"], sorted(ok), res[:3]))
    return {"n": n, "top1": t1 / n, "top3": t3 / n, "top5": t5 / n, "misses": misses}
