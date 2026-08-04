from __future__ import annotations

from pathlib import Path

CATEGORIES = {
    "offering_memorandum": ("offering memorandum", "investment offering", "executive summary", "om"),
    "rent_roll": ("rent roll", "tenant", "suite", "lease expiration"),
    "t12_operating_statement": ("t-12", "t12", "trailing twelve", "operating statement"),
    "historical_operating_statement": ("historical operations", "income statement"),
    "commercial_lease": ("lease agreement", "landlord", "tenant", "premises"),
    "lease_amendment": ("lease amendment", "amendment to lease"),
    "debt_quote": ("debt quote", "loan quote"),
    "loan_term_sheet": ("loan term sheet", "indicative terms"),
    "purchase_and_sale_agreement": ("purchase and sale agreement", "purchase agreement"),
    "letter_of_intent": ("letter of intent", "non-binding loi"),
    "capital_expenditure_budget": ("capital budget", "capex"),
    "property_condition_report": ("property condition", "physical needs assessment"),
    "environmental_report": ("phase i environmental", "environmental site assessment"),
    "appraisal": ("appraisal report", "market value"),
}


def classify(filename: str, text: str = "") -> tuple[str, float]:
    haystack = f"{Path(filename).stem} {text[:20000]}".lower().replace("_", " ").replace("-", " ")
    scores = {category: sum(2 if phrase in haystack else 0 for phrase in phrases) for category, phrases in CATEGORIES.items()}
    category, score = max(scores.items(), key=lambda item: item[1])
    return (category, min(0.98, 0.55 + score * 0.08)) if score else ("unknown", 0.2)

