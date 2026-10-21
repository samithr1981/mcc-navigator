"""Case record: a JSON and an HTML summary of one assessment, for the onboarding file."""
from __future__ import annotations

import datetime as dt
import html
import json

from . import kb, engine


def case_dict(a: engine.Assessment, rev: dict | None = None) -> dict:
    cfg = engine.config()
    p = a.profile
    return {
        "generated": dt.datetime.now().isoformat(timespec="seconds"),
        "network": cfg["network_name"], "rulebook": cfg["rulebook_label"],
        "merchant": {"legal_name": p.legal_name, "dba_name": p.dba_name, "country": p.country, "channel": p.channel,
                     "description": p.description, "sales": [{"text": s.text, "pct": s.pct} for s in p.sales]},
        "answers": p.probe_answers,
        "recommendation": {"mcc": a.primary, "title": a.candidates[0].title if a.candidates else "", "confidence": a.confidence, "note": a.confidence_note},
        "candidates": [{"mcc": c.code, "title": c.title, "match_strength": round(c.score, 3), "reasons": c.reasons, "flags": c.flags, "manual_page": c.page} for c in a.candidates],
        "findings": [{"level": f.level, "title": f.title, "detail": f.detail, "reference": f.ref} for f in a.findings],
        "review": rev, "disclaimer": cfg["disclaimer"],
    }


def to_json(a, rev=None) -> str:
    return json.dumps(case_dict(a, rev), indent=2, ensure_ascii=False)


def to_html(a, rev=None) -> str:
    d = case_dict(a, rev)
    e = html.escape
    rows = "".join(f"<tr><td>{e(c['mcc'])}</td><td>{e(c['title'])}</td><td>{c['match_strength']:.2f}</td><td>{e('; '.join(c['reasons'] + c['flags']))}</td><td>p.{c['manual_page']}</td></tr>" for c in d["candidates"])
    fr = "".join(f"<li><b>[{e(f['level'])}]</b> {e(f['title'])}. {e(f['detail'])} <i>{e(f['reference'])}</i></li>" for f in d["findings"])
    ans = "".join(f"<li>{e(k)}: {e(str(v))}</li>" for k, v in d["answers"].items()) or "<li>None</li>"
    rv = f"<h2>Existing MCC review</h2><p><b>{e(rev['current'])}</b>: {e(rev['verdict'])}. {e(' '.join(rev['why']))}</p>" if rev and rev.get("current") else ""
    m = d["merchant"]
    return f"""<!doctype html><meta charset=utf-8><title>MCC case record</title>
<style>body{{font:15px/1.5 system-ui,sans-serif;max-width:900px;margin:2rem auto;padding:0 1rem;color:#1d2433}}table{{border-collapse:collapse;width:100%}}td,th{{border-bottom:1px solid #ddd;padding:6px;text-align:left;vertical-align:top}}h1{{font-size:1.5rem}}.box{{background:#f2f5fa;padding:1rem;border-radius:8px}}</style>
<h1>MCC case record</h1><p>{e(d['network'])} · {e(d['rulebook'])} · {e(d['generated'])}</p>
<div class=box><b>Recommended MCC: {e(d['recommendation']['mcc'])} {e(d['recommendation']['title'])}</b><br>Confidence: {e(d['recommendation']['confidence'])}<br><small>{e(d['recommendation']['note'])}</small></div>
<h2>Merchant</h2><p>{e(m['dba_name'] or m['legal_name'])} · {e(m['country'])} · {e(m['channel'])}<br>{e(m['description'])}</p>
<h2>Answers given</h2><ul>{ans}</ul><h2>Candidates</h2><table><tr><th>MCC</th><th>Title</th><th>Strength</th><th>Why / flags</th><th>Definition</th></tr>{rows}</table>
<h2>Findings</h2><ul>{fr}</ul>{rv}<p><small>{e(d['disclaimer'])}</small></p>"""
