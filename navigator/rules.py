"""Rule pack: plain-language summaries of the manual's requirements, with printed page references.

Summaries are written in the Navigator's own words, not quoted. `source` says where each rule comes from:
  "Manual" - the rule is stated in the manual (page given; check it against the current edition before relying on it)
  "Practice" - Navigator good practice, not from the manual.
A network that uses another rulebook should replace this file (same structure).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Rule:
    id: str
    topic: str
    summary: str
    page: int | None
    source: str = "Manual"
    severity: str = "info"  # info, warn, block

    @property
    def ref(self) -> str:
        return f"Manual p.{self.page}" if self.source == "Manual" and self.page else "Navigator practice"


R = Rule
RULES = [
    # name
    R("NAME-1", "Name", "Use the most prominent name the customer recognises (the DBA name). If that name does not suggest the business type that matches the MCC, add type information.", 3),
    R("NAME-2", "Name", "Decide first whether the party is the merchant, a payment facilitator or a marketplace; the name and location rules differ for each.", 3),
    R("NAME-3", "Name", "The name field holds 25 characters. Abbreviate without cutting off the identifying part of the name.", 5, severity="warn"),
    R("NAME-4", "Name", "Supplementary data added to the name must be static (the same on every transaction), not an order number or date that changes.", 5),
    R("NAME-5", "Name", "Airline, ancillary and ticket formats: the name sits in the first positions, one blank, then the identifier from position 13.", 6),
    R("NAME-6", "Name", "Payment facilitator transactions use the form PF*Sponsored merchant; billing-provider and bill-payment services use name*supplier or name*biller.", 6),
    R("NAME-7", "Name", "Tips collected as a separate transaction carry the word Tip in the name.", 7),
    # city and country
    R("CITY-1", "City", "The city field holds 13 characters and the city is spelled out, with limited exceptions.", 12, severity="warn"),
    R("CITY-2", "City", "Card-absent merchants put a customer service phone number, URL or email in the city field.", 12, severity="warn"),
    R("CITY-3", "City", "Transit MCCs 4111, 4112 and 4131 and travelling merchants have their own city-field allowances.", 13),
    # location
    R("LOC-1", "Location", "The acquirer assigns the location. For card-present it is where the transaction took place.", 8),
    R("LOC-2", "Location", "For card-absent it is the merchant's principal place of business.", 8),
    R("LOC-3", "Location", "A web checkout must show the country of the outlet on the checkout page itself, not only behind a hyperlink.", 9, severity="warn"),
    R("LOC-4", "Location", "An additional location needs more than a PO box, a payment processing site or a customer service centre. The manual's tests are: decisions made there on a permanent basis, sales tax assessed there, and governing law.", 10),
    R("LOC-5", "Location", "Due diligence on location should look at where the business is run, staffed and taxed. The manual lists the factors.", 11),
    R("LOC-6", "Location", "Payment facilitators, staged digital wallet operators and marketplaces have their own location rules, set out with worked examples.", 12),
    # mcc
    R("MCC-1", "MCC", "Assign the MCC that matches the primary business, judged by sales volume.", 15),
    R("MCC-2", "MCC", "Use a miscellaneous or 'not elsewhere classified' MCC only when no specific MCC fits.", 15),
    R("MCC-3", "MCC", "One MCC per outlet. An e-commerce site is a location of its own.", 15),
    R("MCC-4", "MCC", "Separate businesses on the same premises need their own MCC where they trade under a different name, in a distinct area or on a separate point of sale.", 16),
    R("MCC-5", "MCC", "For travel and entertainment use the merchant-specific MCC if one exists, otherwise the generic one.", 16),
    R("MCC-6", "MCC", "Direct marketing MCCs and wholesale club describe how the business sells, not what it sells.", 16),
    R("MCC-7", "MCC", "Non-fungible tokens take the MCC of the item they represent.", 16),
    # multiple
    R("MULTI-1", "Multiple MCCs", "Automated fuel dispensing must be set up under its own MCC, 5542.", 17),
    R("MULTI-2", "Multiple MCCs", "ATM cash is 6011 and manual cash disbursement is 6010. Quasi-cash and crypto (6051, 6012) need the special condition indicator on authorisation and the quasi-cash indicator in clearing. Money transfer is 4829.", 17),
    R("MULTI-3", "Multiple MCCs", "A merchant running different businesses in one location, or linked websites, uses a separate MCC for each.", 17),
    R("MULTI-4", "Multiple MCCs", "A payment facilitator is assigned an MCC per sponsored merchant.", 18),
    R("MULTI-5", "Multiple MCCs", "Gambling: card-present gambling transactions use 7995 and the rest uses the business MCC; for online gambling, card-absent, all transactions use 7995. In the US the lottery and gaming MCCs 7800 to 7802 apply.", 18),
    R("MULTI-6", "Multiple MCCs", "A high-brand-risk line of business needs its own MCC even when it is a small part of sales.", 18),
    R("MULTI-7", "Multiple MCCs", "Multiple MCCs may also be used where a merchant chooses to, as in the manual's examples one to six.", 19, severity="info"),
    # risk
    R("HBR-1", "High-brand-risk", "Card-absent merchants in 5122, 5912, 5962, 5966, 5967, 5993, 7273 and 7995 are high brand risk. Some regions apply this to non-domestic only for 5912 and 5993.", 17, severity="warn"),
    R("HBR-2", "High-brand-risk", "Cyber lockers (4816), skilled game wagering (5816) and cryptocurrency sale (6051) are high brand risk in certain circumstances.", 17, severity="warn"),
    # change
    R("CHG-1", "Change", "A new MCC or a change to the MCC list is requested through the network's MCC request form.", 107),
    # practice
    R("PR-1", "Practice", "Record the evidence behind the MCC (website, licence, invoice mix) and the date of the decision.", None, "Practice"),
    R("PR-2", "Practice", "Re-check the MCC when the merchant adds a product line, changes channel, or its sales mix moves.", None, "Practice"),
    R("PR-3", "Practice", "Where two MCCs are close, ask the merchant for the sales split rather than guessing.", None, "Practice"),
]
BY_ID = {r.id: r for r in RULES}


def get(rule_id: str) -> Rule:
    return BY_ID[rule_id]


def by_topic() -> dict[str, list[Rule]]:
    out: dict[str, list[Rule]] = {}
    for r in RULES:
        out.setdefault(r.topic, []).append(r)
    return out
