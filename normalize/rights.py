"""Scope permissions to the ingested material, not hypothetical market data."""
from quantgraph.collectors.common import uid


def rights_for(record):
    flag = record["commercial_use_flag"]
    values = {
        "permitted_with_attribution": ("ALLOWED", "ALLOWED", "ALLOWED", True, "ATTRIBUTION_REQUIRED"),
        "conditional_copyleft": ("CONDITIONAL", "CONDITIONAL", "CONDITIONAL", True, "REVIEW_REQUIRED"),
        "noncommercial_only": ("PROHIBITED", "CONDITIONAL", "CONDITIONAL", True, "NONCOMMERCIAL_ONLY"),
    }.get(flag, ("REVIEW_REQUIRED", "REVIEW_REQUIRED", "REVIEW_REQUIRED", None, "REVIEW_REQUIRED"))
    return dict(
        license=record["license"], license_id=uid("license", record["source_id"]+":"+record["license"]),
        commercial_use=values[0], redistribution_allowed=values[1], derivative_allowed=values[2],
        attribution_required=values[3], rights_status=values[4],
        raw_data_allowed="REVIEW_REQUIRED",
        rights_scope="Collected definitions/metadata only; excludes underlying market observations and upstream third-party rights.",
        terms_url=record["terms_url"],
    )


def commercial_allowed(record):
    return all(record.get(k) == "ALLOWED" for k in
               ("commercial_use", "redistribution_allowed", "derivative_allowed")) and record.get("attribution_required") is not None
