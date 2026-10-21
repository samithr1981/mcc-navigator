"""Run: python3 tests/run_checks.py  (from the project folder). Prints retrieval accuracy and a few smoke tests."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from navigator import engine, evaluate as ev, kb, descriptor
from navigator.textmatch import Index

ix = Index()
w = ev.written_cases(ix); h = ev.held_out(ix)
print("written cases", {k: v for k, v in w.items() if k != "misses"})
print("held-out terms", {k: v for k, v in h.items() if k != "misses"})
assert len(kb.load()) == 292
a = engine.assess(engine.Profile(description="Ride hailing platform")); assert a.primary == "4121"
assert engine.review(engine.Profile(description="Taxi", current_mcc="9702"))["level"] == "block"
assert descriptor.check("Merchant", "A" * 30, "Pune").checks[0].level in ("warn", "block")
print("smoke tests passed")
