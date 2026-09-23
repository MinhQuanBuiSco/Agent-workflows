ACCEPT_LAW = {"delaware", "california", "new york"}

US_STATES = {
    "alabama",
    "alaska",
    "arizona",
    "arkansas",
    "california",
    "colorado",
    "connecticut",
    "delaware",
    "district of columbia",
    "florida",
    "georgia",
    "hawaii",
    "idaho",
    "illinois",
    "indiana",
    "iowa",
    "kansas",
    "kentucky",
    "louisiana",
    "maine",
    "maryland",
    "massachusetts",
    "michigan",
    "minnesota",
    "mississippi",
    "missouri",
    "montana",
    "nebraska",
    "nevada",
    "new hampshire",
    "new jersey",
    "new mexico",
    "new york",
    "north carolina",
    "north dakota",
    "ohio",
    "oklahoma",
    "oregon",
    "pennsylvania",
    "rhode island",
    "south carolina",
    "south dakota",
    "tennessee",
    "texas",
    "utah",
    "vermont",
    "virginia",
    "washington",
    "west virginia",
    "wisconsin",
    "wyoming",
}


def _years(fields: dict) -> float | None:
    raw = fields.get("years")
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def rule_mutuality(fields: dict) -> tuple[str, str]:
    mutual = fields.get("mutual")
    favors_us = fields.get("favors_us")
    if mutual is True:
        return "accept", "Obligations bind both parties."
    if mutual is False and favors_us is True:
        return (
            "fallback",
            "One-way, and only the counterparty is bound. Confirm that is intentional.",
        )
    if mutual is False and favors_us is False:
        return "reject", "One-way against Acme. This playbook rejects an NDA that binds only Acme."
    return "reject", "The extraction does not establish that the NDA is mutual."


def rule_purpose(fields: dict) -> tuple[str, str]:
    if fields.get("limited_to_purpose") is True:
        return "accept", "Use is limited to the stated purpose."
    return "reject", "Use is not limited to the stated purpose."


def rule_term(fields: dict) -> tuple[str, str]:
    if fields.get("perpetual") is True:
        return "reject", "Confidentiality does not expire. This playbook rejects a perpetual term."
    years = _years(fields)
    if years is None:
        return "reject", "No usable term length was extracted."
    if years > 5:
        return "reject", f"{years:g} years is longer than the five-year ceiling."
    if years >= 4:
        return "fallback", f"{years:g} years is outside the two-to-three-year accept band."
    if years >= 2:
        return "accept", f"{years:g} years is inside the two-to-three-year accept band."
    if years >= 0:
        return (
            "fallback",
            f"{years:g} years is shorter than the two-year standard. Counsel should glance at it.",
        )
    return "reject", "The extracted term is not a usable period."


def rule_residuals(fields: dict) -> tuple[str, str]:
    if fields.get("has_residual") is True:
        return "reject", "The contract lets a party use information retained in unaided memory."
    return "accept", "The quoted text does not grant a residual right."


def rule_return_destroy(fields: dict) -> tuple[str, str]:
    has_return = fields.get("has_return_or_destroy") is True
    archive = fields.get("archive_copy") is True
    if has_return and archive:
        return "fallback", "Return or destruction is required, but an archival copy may be kept."
    if has_return:
        return "accept", "Copies must be returned or destroyed, and nothing may be retained."
    return "reject", "The contract does not require return or destruction."


def rule_compelled_notice(fields: dict) -> tuple[str, str]:
    if fields.get("must_notify") is True:
        return (
            "accept",
            "Notice is required before a compelled disclosure, where the law allows it.",
        )
    return "reject", "The compelled-disclosure language does not require prior notice."


def rule_non_solicit(fields: dict) -> tuple[str, str]:
    scope = str(fields.get("scope") or "").strip().lower()
    if scope == "broad":
        return "reject", "A broad employee non-solicit does not belong in this NDA."
    if scope == "narrow":
        return "fallback", "A narrow non-solicit is present and still needs a glance."
    return "fallback", "A non-solicit is present, but its scope is unclear."


def rule_governing_law(fields: dict) -> tuple[str, str]:
    raw = str(fields.get("jurisdiction") or "").strip().lower()
    if not raw:
        return "fallback", "No governing law was extracted from the quote."
    if any(name in raw for name in ACCEPT_LAW):
        return "accept", f"Governing law ({fields.get('jurisdiction')}) is on the accept list."
    if any(name in raw for name in US_STATES) or raw in {"usa", "u.s.", "us", "united states"}:
        return (
            "fallback",
            f"{fields.get('jurisdiction')} is a US forum outside the three accepted states.",
        )
    return "reject", f"{fields.get('jurisdiction')} is outside the United States."


def rule_ai_training(fields: dict) -> tuple[str, str]:
    if fields.get("grants_training") is True:
        return "reject", "The contract grants a right to train models on confidential information."
    return "accept", "The quoted text does not grant a model-training right."


def rule_personal_data(fields: dict) -> tuple[str, str]:
    excludes = fields.get("excludes_personal_data") is True
    requires_dpa = fields.get("requires_dpa") is True
    if excludes or requires_dpa:
        return (
            "accept",
            "Personal data is excluded, or a data processing addendum is required first.",
        )
    return "reject", "Personal data is neither excluded nor gated on a data processing addendum."


RULES = {
    "mutuality": rule_mutuality,
    "purpose": rule_purpose,
    "term": rule_term,
    "residuals": rule_residuals,
    "return_destroy": rule_return_destroy,
    "compelled_notice": rule_compelled_notice,
    "non_solicit": rule_non_solicit,
    "governing_law": rule_governing_law,
    "ai_training": rule_ai_training,
    "personal_data": rule_personal_data,
}


def adjudicate(rule_id: str, fields: dict) -> tuple[str, str]:
    try:
        rule = RULES[rule_id]
    except KeyError as exc:
        raise KeyError(f"No playbook rule named {rule_id}") from exc
    return rule(fields)
