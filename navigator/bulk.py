"""Portfolio audit: run the review over a table of existing merchants."""
from __future__ import annotations

import pandas as pd

from . import engine, kb

COLUMNS = ["merchant_id", "name", "description", "current_mcc", "country", "channel", "perishables_pct", "annual_txn"]


def run(df: pd.DataFrame, default_country: str = "India") -> pd.DataFrame:
    rows = []
    cols = {c.lower().strip(): c for c in df.columns}
    g = lambda r, k, d="": (r[cols[k]] if k in cols and pd.notna(r[cols[k]]) else d)
    for _, r in df.iterrows():
        ch = str(g(r, "channel", "")).lower()
        channel = engine.CHANNELS[1] if "online" in ch or "web" in ch or "ecom" in ch else engine.CHANNELS[2] if "phone" in ch or "mail" in ch else engine.CHANNELS[0]
        pp = g(r, "perishables_pct", None)
        at = g(r, "annual_txn", None)
        p = engine.Profile(legal_name=str(g(r, "name")), dba_name=str(g(r, "name")), description=str(g(r, "description")) or str(g(r, "name")),
                           country=str(g(r, "country", default_country)), channel=channel, current_mcc=str(g(r, "current_mcc")).replace(".0", ""),
                           perishables_pct=float(pp) if pp not in (None, "") else None, annual_txn=int(float(at)) if at not in (None, "") else None)
        a = engine.assess(p)
        v = engine.review(p, a)
        cur = kb.get(v["current"]) if v["current"] else None
        rows.append({"merchant_id": g(r, "merchant_id"), "name": g(r, "name"), "current_mcc": v["current"], "current_title": cur.short_title if cur else "",
                     "verdict": v["verdict"], "level": v["level"], "suggested_mcc": a.primary, "suggested_title": a.candidates[0].title if a.candidates else "",
                     "match_strength": round(a.candidates[0].score, 2) if a.candidates else 0, "confidence": a.confidence,
                     "alternatives": ", ".join(c.code for c in a.candidates[1:4]),
                     "findings": "; ".join(f.title for f in a.findings if f.level in ("warn", "block")),
                     "notes": "; ".join(v["why"])})
    return pd.DataFrame(rows)
