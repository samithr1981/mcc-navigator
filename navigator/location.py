"""Location determination: which location and country go on a merchant's transactions, with the rule behind each step."""
from __future__ import annotations

from dataclasses import dataclass, field

from . import rules

ENTITY = ["Merchant", "Payment facilitator", "Staged digital wallet operator (SDWO)", "Marketplace"]


@dataclass
class LocationAnswer:
    entity: str = "Merchant"
    card_present: bool = True
    txn_place: str = ""              # where the sale happens (card-present)
    principal_place: str = ""        # principal place of business
    extra_site_name: str = ""
    extra_decisions: bool = False    # decisions taken on a permanent basis
    extra_sales_tax: bool = False
    extra_law: bool = False
    extra_only_weak: bool = False    # only a PO box, payment processing site, or customer-service centre
    travel_or_lodging: bool = False
    checkout_shows_country: bool = True
    eea: bool = False


@dataclass
class LocationResult:
    location: str
    steps: list = field(default_factory=list)   # (level, text, ref)


def determine(a: LocationAnswer) -> LocationResult:
    st = []
    if a.entity != "Merchant":
        st.append(("warn", f"{a.entity}: the manual gives its own location rules with worked examples. Settle who the merchant of record is first, then use the sponsored merchant's or seller's location where the rules say so.", rules.get("LOC-6").ref + "; " + rules.get("NAME-2").ref))
    if a.card_present:
        loc = a.txn_place or "(enter where the transaction takes place)"
        st.append(("ok", f"Card-present: the location is where the transaction took place: {loc}.", rules.get("LOC-1").ref))
    else:
        loc = a.principal_place or "(enter the principal place of business)"
        st.append(("ok", f"Card-absent: the location is the principal place of business: {loc}.", rules.get("LOC-2").ref))
        if not a.checkout_shows_country:
            st.append(("block", "The checkout page must show the country of the outlet on the page itself. A link to a separate page is not enough.", rules.get("LOC-3").ref))
        else:
            st.append(("ok", "Checkout shows the outlet country.", rules.get("LOC-3").ref))
    if a.extra_site_name:
        met = [a.extra_decisions, a.extra_sales_tax, a.extra_law]
        if a.extra_only_weak and not any(met):
            st.append(("block", f"'{a.extra_site_name}' is only a PO box, payment processing site or customer-service centre. That is not enough to count as a location.", rules.get("LOC-4").ref))
        else:
            n = sum(met)
            lvl = "ok" if n >= 2 else "warn"
            st.append((lvl, f"'{a.extra_site_name}' meets {n} of 3 tests (permanent decision-making, sales tax assessed, governing law). Read the manual's tests and worked examples to decide whether it is an additional location, and keep the evidence.", rules.get("LOC-4").ref + "; " + rules.get("LOC-5").ref))
    if a.travel_or_lodging:
        st.append(("info", "Travel and lodging have exceptions to the location rule; check that section for the correct country and city.", rules.get("LOC-1").ref))
    if a.eea:
        st.append(("info", "EEA merchants: check the aggregation rule for the location.", rules.get("LOC-5").ref))
    return LocationResult(loc, st)
