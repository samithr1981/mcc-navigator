"""MCC Navigator: merchant category code classification and review for acquirers."""
from __future__ import annotations

import io

import pandas as pd
import streamlit as st

from navigator import bulk, descriptor, engine, kb, location, report, rules
from navigator.engine import CHANNELS, Profile, SalesLine

cfg = engine.config()
st.set_page_config(page_title="MCC Navigator", page_icon="🧭", layout="wide")
st.markdown("""<style>.block-container{max-width:1200px;padding-top:1.4rem}
.pill{display:inline-block;padding:2px 10px;border-radius:12px;font-size:.8rem;font-weight:600}
.ok{background:#e3f4e8;color:#14683a}.warn{background:#fff1d6;color:#8a5a00}.block{background:#fde4e4;color:#a12727}.info{background:#e6eefb;color:#1f4e9c}
.card{border:1px solid #dde3ee;border-radius:10px;padding:.8rem 1rem;margin:.4rem 0;background:#fff}
.big{font-size:2rem;font-weight:700;line-height:1.1}</style>""", unsafe_allow_html=True)

st.title("🧭 MCC Navigator")
st.caption(f"{cfg['network_name']} · rulebook: {cfg['rulebook_label']}")
with st.expander("How to read this tool", expanded=False):
    st.markdown("""
- **Decision support, not a decision.** The match strength shows how closely your description fits an MCC definition. It is not a probability. The acquirer remains responsible for the final MCC.
- Findings carry a **Manual p.X** label when they come from the manual (page printed on the manual, please verify against your edition) and **Navigator practice** when they are our own advice.
- The plain-language vocabulary (for example *kirana*, *chemist*) and the grouping of MCCs are the Navigator's own additions.
- Do not enter real customer data in a public deployment.""")

TAGS = {"ok": "OK", "warn": "Check", "block": "Stop", "info": "Note"}
def pill(level): return f'<span class="pill {level}">{TAGS.get(level, level)}</span>'

tabs = st.tabs(["1 Classify a merchant", "2 Check an existing MCC", "3 Portfolio audit", "4 MCC library", "5 Name, city and location", "6 Rules guide", "7 Change request"])


def profile_form(prefix: str, with_current: bool) -> Profile:
    c1, c2 = st.columns(2)
    with c1:
        dba = st.text_input("Name customers know (DBA)", key=prefix + "dba")
        legal = st.text_input("Legal name", key=prefix + "legal")
        country = st.text_input("Country of the outlet", "India", key=prefix + "country")
        channel = st.selectbox("How does the merchant sell?", CHANNELS, key=prefix + "channel")
        cur = st.text_input("Current MCC (4 digits)", key=prefix + "cur") if with_current else ""
    with c2:
        desc = st.text_area("What does the business do? Include what it sells and to whom.", height=120, key=prefix + "desc",
                            placeholder="Example: neighbourhood store selling groceries, vegetables, milk and snacks")
        st.caption("Sales mix (optional): list each product or service line with its share of sales. The largest line decides the primary MCC.")
        df = st.data_editor(pd.DataFrame({"Line of business": ["", "", ""], "Share of sales %": [0.0, 0.0, 0.0]}), num_rows="dynamic", key=prefix + "mix", hide_index=True, width="stretch")
    with st.expander("More facts that change the answer"):
        a, b, c = st.columns(3)
        gov = a.checkbox("Government entity", key=prefix + "gov")
        dig = a.checkbox("Sells digital goods", key=prefix + "dig")
        mkt = a.checkbox("Marketplace or payment facilitator", key=prefix + "mkt")
        pump = b.checkbox("Automated pay-at-pump fuel", key=prefix + "pump")
        cash = b.checkbox("Provides cash or quasi-cash", key=prefix + "cash")
        gam = b.checkbox("Takes wagers or sells chances", key=prefix + "gam")
        b2b = c.slider("Share of sales to businesses %", 0, 100, 0, key=prefix + "b2b")
        per = c.number_input("Perishable food, % of monthly sales (food retail)", 0.0, 100.0, None, key=prefix + "per", placeholder="unknown")
        txn = c.number_input("Card transactions a year (digital goods)", 0, None, None, key=prefix + "txn", placeholder="unknown")
    sales = [SalesLine(str(r["Line of business"]), float(r["Share of sales %"] or 0)) for _, r in df.iterrows() if str(r["Line of business"]).strip()]
    return Profile(legal_name=legal, dba_name=dba, country=country or "India", description=desc, sales=sales, channel=channel, is_government=gov, b2b_share=float(b2b),
                   sells_digital_goods=dig, is_marketplace_or_pf=mkt, perishables_pct=per, annual_txn=int(txn) if txn else None, pay_at_pump=pump,
                   cash_or_quasi_cash=cash, gambling=gam, current_mcc=cur)


def show_candidates(a: engine.Assessment):
    if not a.candidates:
        st.warning(a.confidence_note); return
    top = a.candidates[0]
    c1, c2 = st.columns([1, 2])
    with c1:
        st.markdown(f'<div class="card"><div style="color:#667">Recommended MCC</div><div class="big">{top.code}</div><div>{top.title}</div><div style="margin-top:.5rem">Confidence: <b>{a.confidence}</b> · strength {top.score:.2f}</div></div>', unsafe_allow_html=True)
        st.caption(a.confidence_note)
    with c2:
        rows = [{"MCC": c.code, "Title": c.title, "Strength": round(c.score, 2), "Why": "; ".join(c.reasons) or c.matched_on, "Flags": "; ".join(c.flags), "Manual page": c.page} for c in a.candidates]
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    m = kb.get(top.code)
    with st.expander(f"Definition of {top.code} (verbatim from the manual, p.{m.page})"):
        st.write(m.description)
        if m.included:
            st.markdown("**Included:** " + "; ".join(m.included))
        if m.similar:
            st.markdown("**Similar, but different MCCs:** " + "; ".join(f"{c} {t}" for c, t in m.similar))


def probes_ui(prefix: str, p: Profile):
    a0 = engine.assess(p)
    if not a0.probes:
        return
    st.subheader("Questions that settle close calls")
    st.caption("Each question comes from a test in the MCC definitions. Answer what you know; leave the rest.")
    for pr in a0.probes:
        labels = ["Not answered"] + [o[0] for o in pr.options]
        v = st.selectbox(f"{pr.title}: {pr.question}", labels, key=prefix + "pr_" + pr.id, help=pr.basis)
        if v != "Not answered":
            p.probe_answers[pr.id] = v


def findings_ui(a: engine.Assessment):
    st.subheader("What the acquirer needs to know")
    for f in a.findings:
        ref = f' <span style="color:#667;font-size:.85rem">[{f.ref}]</span>' if f.ref else ""
        st.markdown(f'{pill(f.level)} **{f.title}**{ref}<br><span style="color:#445">{f.detail}</span>', unsafe_allow_html=True)
    if a.named:
        st.markdown("**Matches in the manual's named travel and lodging list**")
        st.dataframe(pd.DataFrame([{"MCC": e.code, "Merchant": e.merchant, "Required name": e.required_name, "Match": round(s, 2), "Page": e.page} for e, s in a.named]), hide_index=True)
    if a.secondary:
        st.markdown("**Each sales line, classified separately**")
        st.dataframe(pd.DataFrame([{"Line": s["text"], "Share %": s["pct"], "Best MCC": f"{s['mcc']} {s['title']}", "Differs from primary": "Yes" if s["differs"] else "No"} for s in a.secondary]), hide_index=True, width="stretch")


# ---------------------------------------------------------------- tab 1
with tabs[0]:
    st.subheader("Onboarding: what is the right MCC?")
    p = profile_form("n_", False)
    if p.description.strip() or p.sales or p.dba_name.strip():
        probes_ui("n_", p)
        a = engine.assess(p)
        st.divider(); show_candidates(a); findings_ui(a)
        d1, d2 = st.columns(2)
        d1.download_button("Download case record (HTML)", report.to_html(a), "mcc_case.html", "text/html")
        d2.download_button("Download case record (JSON)", report.to_json(a), "mcc_case.json", "application/json")
    else:
        st.info("Describe the business to start.")

# ---------------------------------------------------------------- tab 2
with tabs[1]:
    st.subheader("Existing merchant: is the MCC right?")
    p2 = profile_form("e_", True)
    if p2.current_mcc.strip() and (p2.description.strip() or p2.sales or p2.dba_name.strip()):
        probes_ui("e_", p2)
        a2 = engine.assess(p2); rv = engine.review(p2, a2)
        st.divider()
        st.markdown(f'{pill(rv["level"])} **{rv["current"]} {rv["current_title"]}: {rv["verdict"]}**', unsafe_allow_html=True)
        for w in rv["why"]:
            st.write("• " + w)
        if rv["level"] != "ok":
            st.write(f"Suggested: **{a2.primary}**")
        show_candidates(a2); findings_ui(a2)
        st.download_button("Download review (HTML)", report.to_html(a2, rv), "mcc_review.html", "text/html")
    else:
        st.info("Enter the current MCC and a description.")

# ---------------------------------------------------------------- tab 3
with tabs[2]:
    st.subheader("Portfolio audit")
    st.caption("Upload a CSV with columns: merchant_id, name, description, current_mcc, country, channel (online, phone or blank), perishables_pct, annual_txn. Only name or description and current_mcc are needed.")
    st.download_button("Download a template", ",".join(bulk.COLUMNS) + "\n1,ABC Pharmacy,Chemist shop,5912,India,,,\n", "template.csv", "text/csv")
    up = st.file_uploader("CSV file", type="csv")
    if up:
        df = pd.read_csv(up, dtype=str)
        out = bulk.run(df)
        c = out["level"].value_counts()
        k = st.columns(4)
        for col, (lab, lv) in zip(k, [("Consistent", "ok"), ("Check", "warn"), ("Does not fit", "block"), ("Other", "info")]):
            col.metric(lab, int(c.get(lv, 0)))
        st.dataframe(out, hide_index=True, width="stretch")
        st.download_button("Download results (CSV)", out.to_csv(index=False), "audit.csv", "text/csv")

# ---------------------------------------------------------------- tab 4
with tabs[3]:
    st.subheader("MCC library")
    q = st.text_input("Search by merchant type or code")
    fam = st.multiselect("Group", sorted({m.family for m in kb.load().values()}))
    allm = list(kb.load().values())
    if q.strip():
        if q.strip().isdigit():
            allm = [m for m in allm if m.code.startswith(q.strip())]
        else:
            order = [m.code for m in engine.index().rank(q, top=30)]
            allm = [kb.get(c) for c in order[:15]]
    if fam:
        allm = [m for m in allm if m.family in fam]
    st.dataframe(pd.DataFrame([{"MCC": m.code, "Title": m.short_title, "Group": m.family, "Special handling": ", ".join(sorted(m.tags)), "Region": ", ".join(m.regions), "Page": m.page} for m in allm]), hide_index=True, width="stretch")
    st.markdown("**Compare two MCCs**")
    c1, c2 = st.columns(2)
    codes = sorted(kb.load())
    a_ = c1.selectbox("First", codes, index=codes.index("5411") if "5411" in codes else 0, format_func=lambda c: kb.get(c).label)
    b_ = c2.selectbox("Second", codes, index=codes.index("5499") if "5499" in codes else 1, format_func=lambda c: kb.get(c).label)
    for col, c in zip((c1, c2), (a_, b_)):
        m = kb.get(c)
        col.markdown(f"**{m.label}** (p.{m.page})"); col.write(m.description)
        if m.included: col.markdown("*Included:* " + "; ".join(m.included))
        if m.similar: col.markdown("*Similar:* " + "; ".join(f"{x} {t}" for x, t in m.similar))

# ---------------------------------------------------------------- tab 5
with tabs[4]:
    st.subheader("Name, city and location")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Descriptor**")
        kind = st.selectbox("Who is the name for?", descriptor.TYPES)
        nm = st.text_input("Merchant name", key="d_name")
        extra = st.text_input("Supplier, biller or seller name (if the format needs one)", key="d_extra")
        city = st.text_input("City field (or customer service contact for card-absent)", key="d_city")
        ca = st.checkbox("Card-absent merchant", key="d_ca")
        mc = st.text_input("MCC (optional, to check the name fits the business)", key="d_mcc")
        r = descriptor.check(kind, nm, city, extra, ca, mc.strip())
        if nm:
            st.code(f"{r.name_field}  |  {r.city_field}")
            for ck in r.checks:
                st.markdown(f'{pill(ck.level)} {ck.text} <span style="color:#667;font-size:.85rem">[{ck.ref}]</span>', unsafe_allow_html=True)
    with c2:
        st.markdown("**Location**")
        ent = st.selectbox("Entity", location.ENTITY)
        cp = st.radio("Sales channel", ["Card-present", "Card-absent"], horizontal=True) == "Card-present"
        tp = st.text_input("Where the transaction takes place (city, country)") if cp else ""
        pp = st.text_input("Principal place of business (city, country)") if not cp else ""
        shows = True if cp else st.checkbox("Checkout page shows the outlet country on the page", True)
        extra_site = st.text_input("Another site claimed as a location (optional)")
        d1 = d2 = d3 = weak = False
        if extra_site:
            d1 = st.checkbox("Decisions are taken there on a permanent basis")
            d2 = st.checkbox("Sales tax is assessed there")
            d3 = st.checkbox("Its governing law applies")
            weak = st.checkbox("It is only a PO box, payment processing site or customer-service centre")
        tl = st.checkbox("Travel or lodging merchant"); ee = st.checkbox("EEA merchant")
        res = location.determine(location.LocationAnswer(ent, cp, tp, pp, extra_site, d1, d2, d3, weak, tl, shows, ee))
        for lv, tx, rf in res.steps:
            st.markdown(f'{pill(lv)} {tx} <span style="color:#667;font-size:.85rem">[{rf}]</span>', unsafe_allow_html=True)

# ---------------------------------------------------------------- tab 6
with tabs[5]:
    st.subheader("Rules guide")
    st.caption("Plain-language summaries in our own words with the manual's printed page. Read the manual page itself before relying on a rule.")
    for topic, rs in rules.by_topic().items():
        with st.expander(topic, expanded=False):
            for r in rs:
                st.markdown(f"**{r.id}** · {r.summary} <span style='color:#667'>[{r.ref}]</span>", unsafe_allow_html=True)

# ---------------------------------------------------------------- tab 7
with tabs[6]:
    st.subheader("Change request helper")
    st.write(cfg["mcc_change_process"])
    cur = st.text_input("Current MCC", key="cr_cur"); new = st.text_input("Proposed MCC", key="cr_new")
    why = st.text_area("Evidence for the change (website, licence, invoice mix, sales split)", key="cr_why")
    nmx = st.text_input("Merchant", key="cr_nm")
    if cur and new:
        c, n = kb.get(cur), kb.get(new)
        if c and n:
            txt = (f"MCC change request\nMerchant: {nmx}\nCurrent: {c.label}\nProposed: {n.label}\n\nDefinition of the proposed MCC ({cfg['rulebook_label']}, p.{n.page}):\n{n.description}\n\nEvidence:\n{why}\n\n"
                   "Declaration: the proposed MCC reflects the primary business by sales volume.\n")
            st.code(txt)
            st.download_button("Download", txt, "mcc_change_request.txt")
        else:
            st.warning("One of the codes is not in the list.")

st.divider()
st.caption(cfg["disclaimer"])
