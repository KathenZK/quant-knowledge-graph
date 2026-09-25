"""Definition admission, separate from profitability and executable semantics."""
BLOCKING_ISSUES = {
    "DEGENERATE_FEATURE", "DUPLICATE_SOURCE_ABBREVIATION", "LATEX_UNBALANCED",
    "RAW_FORMULA_PARSE_ERROR", "OPERATOR_ARITY_REVIEW", "OPERATOR_SIGNATURE_UNRESOLVED",
    "FUTURE_REFERENCE", "DEFINITION_SECTION_JOIN_MISSING",
}


def admission(record, issues):
    reasons = []
    if not record["high_quality_eligible"]:
        reasons.append("NOT_PRIMARY_CONCRETE_DEFINITION")
    if not record["primary_source"]:
        reasons.append("SECONDARY_TRANSCRIPTION")
    if record["record_kind"] != "signal":
        reasons.append("NOT_SIGNAL")
    if not record["raw_definition"]:
        reasons.append("MISSING_DEFINITION")
    reasons += sorted(set(issues) & BLOCKING_ISSUES)
    return not reasons, reasons
