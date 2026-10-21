"""Disambiguation probes: questions that separate MCCs which are easily confused.

Each probe is built from the tests in the manual's MCC definitions (the definition page of each MCC is shown with the
probe). Which probes appear depends on which MCCs are among the candidates. The wording of the questions is the
Navigator's own. If an answer points to an MCC, that MCC is moved to the top and the reason is recorded.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Probe:
    id: str
    title: str
    codes: frozenset
    question: str
    options: tuple  # (label, mcc or "" for no change)
    basis: str


def P(id, title, codes, question, options, basis):
    return Probe(id, title, frozenset(codes.split()), question, tuple(options), basis)


PROBES = [
    P("food-perishable", "Grocery or something else?", "5411 5499 5311 5399 5300",
      "What share of the monthly sales is perishable food (fresh produce, dairy, meat, bakery, frozen)?",
      [("45% or more", "5411"), ("Under 45%, mostly packaged and other food", "5499"), ("Under 45%, mixed general goods", "5399"), ("Warehouse club with membership", "5300")],
      "The grocery MCC 5411 is defined with a perishables test of 45% of monthly sales."),
    P("fuel-afd", "Fuel: attended or self-service?", "5541 5542",
      "Is fuel dispensed by the cardholder at an automated pump (pay at the pump)?",
      [("Yes, cardholder-activated pump", "5542"), ("No, an attendant serves", "5541")],
      "Automated fuel dispensing must use 5542 as a separate MCC even where the site also has an attended forecourt or shop."),
    P("digital-goods", "Digital goods or software?", "5734 5817 7372 5816 5815 4899 5968",
      "How does the customer receive what they buy?",
      [("App or add-on delivered electronically", "5817"), ("Game or media downloaded or streamed once-off", "5815"), ("Streaming or content subscription", "4899"),
       ("Custom software or IT services built for a client", "7372"), ("Software on a disc or boxed in a shop", "5734"), ("Skill-based game with wagers", "5816")],
      "Applications delivered electronically are 5817; custom development is 7372; boxed software is 5734."),
    P("recurring-billing", "Recurring billing", "5968",
      "Is the business mainly a subscription or membership of something that already has its own MCC (for example gym, magazine, insurance)?",
      [("Yes, the underlying service has its own MCC", ""), ("No, the main business is selling the subscription box or continuity plan", "5968")],
      "5968 is for direct marketers whose product is the continuity or subscription plan; other recurring billers use their business MCC."),
    P("online-high-volume", "Very large online merchant", "5818 5817 5815 5816",
      "Does the merchant process 25 million or more transactions in a year, or meet the regional PCI DSS Level 1 test for large digital goods merchants?",
      [("Yes", "5818"), ("No", "")],
      "5818 is limited to large digital goods merchants; the manual gives the threshold and a different European test."),
    P("rental-vs-lodging", "Rental or lodging?", "6513 7011 7032 7033",
      "What is the typical length of stay or rental?",
      [("Under one month, short-stay accommodation", "7011"), ("One month or more, a lease", "6513")],
      "Real estate agent and manager rentals (6513) cover rentals of a month or longer; shorter stays are lodging (7011)."),
    P("transport-people", "Transport of people", "4121 4131 4722 4111 4789 4511",
      "How does the business carry people?",
      [("Ride-hailing or taxi on demand", "4121"), ("Scheduled bus route", "4131"), ("Charter bus or organised tour", "4722"), ("Commuter rail, ferry or local transit", "4111"), ("Airline selling its own flights", "4511")],
      "Taxi and ride-share are 4121; scheduled bus lines 4131; charter and tour buses 4722."),
    P("recreation", "Recreation: sport, club or amusement?", "7993 7994 7992 7997 7941 7999",
      "What does the customer mostly pay for?",
      [("Video game arcade or indoor playground", "7994"), ("Golf course", "7992"), ("Gym or sports club membership", "7997"), ("Commercial sports team or promoter", "7941"), ("Other recreation service", "7999")],
      "7993 is for video game supplies, 7994 for arcades and indoor playgrounds; clubs and gyms are in 7997."),
    P("charity", "Charity or direct marketer?", "8398 5966 8661 8641",
      "Is the merchant a registered charitable or social service organisation?",
      [("Yes", "8398"), ("No, it is a commercial outbound telemarketer", "5966")],
      "5966 (outbound telemarketing) excludes charities."),
    P("hardware", "Home improvement: contractor or public?", "5211 5200 5251 5231",
      "Who is the main customer?",
      [("Contractors, bulk building material", "5211"), ("General public, home and garden", "5200")],
      "5211 is contractor-oriented; 5200 is for the general public."),
    P("airport", "Airport tenant", "4582",
      "Is the merchant a shop or restaurant that is located in an airport?",
      [("Yes, it sells goods or food", ""), ("No, it operates the airport itself", "4582")],
      "Airport tenants use the MCC for their own business; 4582 is for the airport operator."),
    P("courier", "Courier or government post?", "4215 9402",
      "Is it a government postal service?",
      [("Yes", "9402"), ("No, a private courier or freight forwarder", "4215")],
      "9402 is government postal service; private couriers are 4215."),
    P("cash", "Cash, quasi-cash, or funds?", "6010 6011 6012 6051 6540 4829",
      "What does the customer receive?",
      [("Cash at an ATM", "6011"), ("Cash over the counter at a bank", "6010"), ("Goods that behave like cash (crypto, foreign currency, money orders)", "6051"),
       ("Merchandise or services from a financial institution", "6012"), ("Money sent to another person", "4829"), ("A stored value card or wallet top-up", "6540")],
      "Cash and quasi-cash MCCs need special handling in authorisation and clearing; money transfer is 4829. 6540 is not for staged digital wallet operators."),
    P("gambling", "Gambling", "7995 7800 7801 7802 9406",
      "Where is the gaming?",
      [("US government-owned lottery (registered)", "7800"), ("US government-licensed online gambling (registered)", "7801"), ("US government-licensed horse or dog racing wagers (registered)", "7802"), ("Government-owned lottery outside the US", "9406"), ("Casino, betting or fantasy sports with wagers", "7995")],
      "7800 to 7802 apply in the US; outside the US government lotteries are 9406 and other gambling is 7995."),
    P("marketplace", "Marketplace or merchant?", "5262 5399",
      "Does the business sell on behalf of other sellers on its platform?",
      [("Yes, and it is registered as a marketplace", "5262"), ("No, it sells its own goods", "")],
      "5262 is for marketplaces and they must be registered with the network."),
    P("auto-vehicle", "Vehicle dealer", "5521 5511 5599 5551 5571",
      "What does the dealer sell?",
      [("New and used cars from a franchise", "5511"), ("Used cars only", "5521"), ("Boats", "5551"), ("Motorcycles", "5571"), ("Other vehicles", "5599")],
      "5511 covers new and used; 5521 is used only."),
    P("restaurant", "Restaurant, fast food or bar?", "5812 5814 5813 5811",
      "How is the food served?",
      [("Table service", "5812"), ("Counter or quick service", "5814"), ("Mostly alcohol, bar or nightclub", "5813"), ("Caterer", "5811")],
      "5812 is eating places, 5814 fast food, 5813 drinking places, 5811 caterers."),
    P("beauty", "Salon, spa or other personal service", "7230 7298 7297 7299",
      "What is the main service?",
      [("Hair, barber or nails", "7230"), ("Health or beauty spa", "7298"), ("Massage parlour", "7297"), ("Other personal service", "7299")],
      "7230 is beauty and barber shops, 7298 spas, 7297 massage parlours."),
    P("general-store", "General merchandise", "5311 5399 5310 5331 5300",
      "What kind of store is it?",
      [("Department store", "5311"), ("Discount store", "5310"), ("Variety store", "5331"), ("Wholesale club", "5300"), ("Other general merchandise", "5399")],
      "Different MCCs for department, discount, variety and club formats."),
    P("direct-mkt", "How does it sell? (direct marketing)", "5964 5965 5966 5967 5969 5968",
      "What is the main sales channel?",
      [("Catalog", "5964"), ("A mix of catalog and other direct marketing", "5965"), ("Outbound telemarketing", "5966"), ("Inbound telemarketing", "5967"), ("Other direct marketing", "5969")],
      "The direct marketing MCCs describe how the business sells."),
    P("travel-pkg", "Travel agency or tour operator", "4722 5962 4723",
      "Does the merchant sell travel packages?",
      [("Yes, as a travel agency or tour operator (Germany-only package tour MCC is 4723)", "4722"), ("Yes, sold by telemarketing, mail or TV ads (direct marketing)", "5962")],
      "4722 travel agencies; 5962 is the direct-marketing travel-related arrangement MCC."),
    P("te-generic", "Travel and lodging: named or generic?", "4511 7512 7011",
      "Is this an airline, car rental or hotel brand listed in the manual's named list?",
      [("Yes, use the named MCC", ""), ("No, use the generic MCC", "")],
      "Use the merchant-specific MCC if there is one, otherwise the generic one."),
    P("medical", "Health practitioner", "8011 8021 8031 8041 8042 8043 8049 8050 8062 8099",
      "What kind of practitioner?",
      [("Doctor or physician", "8011"), ("Dentist or orthodontist", "8021"), ("Osteopath", "8031"), ("Chiropractor", "8041"), ("Optometrist or ophthalmologist", "8042"), ("Optician", "8043"), ("Hospital", "8062"), ("Other health practitioner", "8099")],
      "Different health MCCs by practitioner type."),
    P("telecom", "Telecom or media", "4814 4816 4899 4812 4821",
      "What does the customer pay for?",
      [("Voice, data or prepaid minutes from an operator", "4814"), ("Phone equipment sales", "4812"), ("Internet or network services", "4816"), ("Cable, satellite or streaming subscriptions", "4899")],
      "Telecom MCCs separate operators, equipment, and network or media services."),
    P("construction", "Contractor type", "1520 1711 1731 1740 1750 1761 1771 1799",
      "What trade does the contractor do?",
      [("General or building contractor", "1520"), ("Plumbing, heating, air conditioning", "1711"), ("Electrical", "1731"), ("Masonry, tile, plaster", "1740"), ("Carpentry", "1750"), ("Roofing, siding", "1761"), ("Concrete", "1771"), ("Special trade", "1799")],
      "Contractors are split by trade."),
    P("education", "School or training", "8211 8220 8241 8244 8249 8299 7911",
      "What is taught?",
      [("Primary or secondary school", "8211"), ("College or university", "8220"), ("Correspondence school", "8241"), ("Business or secretarial school", "8244"), ("Trade or vocational school", "8249"), ("Other classes and instruction", "8299"), ("Dance", "7911")],
      "Education MCCs are split by type of school."),
]


def applicable(candidate_codes: list[str]) -> list[Probe]:
    codes = set(candidate_codes)
    return [p for p in PROBES if p.codes & codes]
