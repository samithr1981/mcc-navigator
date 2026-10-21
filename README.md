# MCC Navigator

A decision-support tool a card network can give to acquiring banks. For onboarding and for existing merchants it answers: which MCC is right, why, what else must be done, and what the rulebook says.

Run: `pip install -r requirements.txt` then `streamlit run app.py` (tested with Streamlit 1.66). No API key, no network calls, no database.

## Tabs
1. Classify: description, sales mix, channel and flags give ranked MCCs with the definition, close-call questions, findings with page references, and a case record (HTML/JSON).
2. Check existing: verdict on a merchant's current MCC (consistent, plausible, weak, does not fit, cannot be assigned).
3. Portfolio audit: upload a CSV, get a verdict per merchant.
4. Library: search 292 MCCs, filter by group, compare two.
5. Name, city, location: 25-character name, 13-character city, supplementary-data formats, location determination.
6. Rules guide: the rule pack in plain language with page references.
7. Change request: drafts an MCC change request.

## Where things come from
- From the manual (Visa Merchant Data Standards Manual, 2023 edition, as supplied): the 292 MCC definitions, included/similar lists, the 593 named airline, car rental and lodging entries (`data/`, built by `kb_build/build_kb.py`), and the substance of `navigator/rules.py`. Page numbers are printed pages; verify them against your edition.
- Navigator's own, not in the manual: MCC grouping, plain-language and Indian vocabulary (`navigator/synonyms.py`), scoring weights and structural adjustments (`engine._adjust`), wording of the close-call questions, abbreviation suggestions, and anything labelled "Navigator practice".
- The manual supplements the Visa Core Rules, which were not available; rules that live there are not covered.
- This is Visa's manual. A network such as NPCI/RuPay should replace `data/mcc_master.json`, `data/te_merchants.csv` and `navigator/rules.py` with its own and edit `config/network.json`. Confirm you may embed the manual's text before distributing.

## Accuracy
Run `python3 tests/run_checks.py`.
- 98 developer-written cases: top-1 about 89%, top-3 about 99%, top-5 100%. The synonym list was tuned on these cases, so this is a regression check, not an independent benchmark.
- Hold-one-out test (hide one "included" merchant type and see where its MCC ranks, n=1209): top-1 about 62%, top-3 about 81%, top-5 about 86%. It uses the manual's own vocabulary and is not a measure of real merchant descriptions.
- Neither has been measured on real onboarding data. Test on a labelled sample of your own merchants first.
- Match strength is not a probability.

## Limits
- The matcher is statistical (TF-IDF), not a language model; unusual wording can mislead it. The close-call questions and the definition shown beside each result are there for that.
- Close siblings (for example men's, women's and family clothing) are separated by the definition, not by the matcher.
- Do not host real customer data on a public deployment.
