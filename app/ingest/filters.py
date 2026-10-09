from __future__ import annotations

from app.ingest.readme import Role


def skip_reason(role: Role, profile: dict, filters: dict) -> str | None:
    if role.section not in set(filters.get("sections") or []):
        return "Outside your selected sections"
    if role.flags.get("closed"):
        return "Listing is marked closed"
    if role.flags.get("us_citizenship") and not profile.get("us_citizen", False):
        return "Requires U.S. citizenship"
    if role.flags.get("no_sponsorship") and profile.get("needs_sponsorship", False):
        return "Does not offer sponsorship"
    if role.flags.get("advanced_degree") and not profile.get("has_advanced_degree", False):
        return "Requires an advanced degree"
    max_age = filters.get("max_age_days")
    if max_age is not None and role.age_days is not None and role.age_days > int(max_age):
        return f"Older than {max_age} days"
    return None
