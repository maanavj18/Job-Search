from __future__ import annotations

import re

from rapidfuzz import fuzz

from app.draft.bank import match_answer

_DECLINE = ("decline", "do not wish", "don't wish", "dont wish", "prefer not", "not to self")
_YES_NO = re.compile(r"^(are|is|do|does|did|have|has|can|could|will|would|should|may)\b")
_ASKS_YOU = re.compile(r"\b(do|will|would|are|have) you\b")
_PROMPT = re.compile(
    r"^(describe|explain|tell|why|how|list|share|in what|in which|to what"
    r"|please (state|describe|explain|tell|share|list))\b"
)
_OPEN_QUESTION = re.compile(r"^(which|what|where|in which)\b")
_ACKNOWLEDGE = re.compile(r"\b(understand|acknowledge|aware|confirm|agree)\b")
_SHORT_LABEL = 40


def draft_fields(
    fields: list[dict],
    profile: dict,
    answers: list[dict],
    *,
    use_llm: bool = True,
) -> list[dict]:
    for field in fields:
        if field.get("type") == "file":
            _apply_resume(field, profile)
            continue
        if _apply_profile(field, profile):
            continue
        matched = match_answer(field.get("label", ""), answers)
        if matched and not field.get("value"):
            field.update(matched)
        _fit_options(field)
    if use_llm:
        from app.draft.llm import fill_gaps

        fill_gaps(fields, profile)
        for field in fields:
            _fit_options(field)
    return fields


def _fit_options(field: dict) -> None:
    options = [str(option.get("label") or "") for option in field.get("options") or []]
    value = str(field.get("value") or "").strip()
    if not options or not value or value in options:
        return
    best_label = ""
    best_score = 0
    for label in options:
        score = int(fuzz.token_set_ratio(value, label))
        if score > best_score:
            best_score = score
            best_label = label
    if best_label and best_score >= 90:
        field["value"] = best_label
        field["confidence"] = "check"
        field["notes"] = "Matched a saved answer to one of this form's options. Check it."
        return
    field["value"] = ""
    field["source"] = "blank"
    field["confidence"] = "blank"
    field["notes"] = "A saved answer did not match this form's options, so it was left blank."


def _apply_resume(field: dict, profile: dict) -> None:
    path = str(profile.get("resume_path") or "").strip()
    if path:
        field["value"] = path
        field["source"] = "profile"
        field["confidence"] = "high"
        field["skip_llm"] = True
    else:
        field["notes"] = "Add resume_path to profile/profile.yaml"
        field["skip_llm"] = True


def _apply_profile(field: dict, profile: dict) -> bool:
    label = _label(field.get("label", ""))
    eeo = _eeo_answer(label, field, profile)
    if eeo is not None:
        field["skip_llm"] = True
        if eeo:
            return _set(field, eeo, eeo, "decline", "high")
        field["notes"] = "No matching decline option. Left blank."
        field["confidence"] = "blank"
        return True

    if "sponsor" in label:
        if _yes_no(label) and re.search(r"\b(require|need)", label) and not _ACKNOWLEDGE.search(label):
            desired = "Yes" if profile.get("needs_sponsorship") else "No"
            return _set_choice(field, desired)
        field["skip_llm"] = True
        field["confidence"] = "blank"
        field["notes"] = "This sponsorship question is phrased unusually. Answer it yourself."
        return True

    if "authoriz" in label and "work" in label and _yes_no(label) and not _ACKNOWLEDGE.search(label):
        desired = "Yes" if profile.get("work_authorized", True) else "No"
        return _set_choice(field, desired)

    value, missing = _fact(label, profile)
    if value:
        return _set_choice(field, value)
    if missing:
        field["skip_llm"] = True
        field["notes"] = "Not in your profile, so it was left blank."
        return True
    return False


def _fact(label: str, profile: dict) -> tuple[str, bool]:
    address = profile.get("address") or {}
    month, year = _graduation_parts(str(profile.get("graduation") or ""))
    checks: list[tuple[bool, str, bool]] = [
        ("end date month" in label, month, True),
        ("end date year" in label or re.search(r"\b(end|graduation) year\b", label) is not None, year, True),
        (_asks_for(label, "discipline"), str(profile.get("major") or ""), True),
        (_asks_for(label, "preferred name", "preferred first name"), str(profile.get("first_name") or ""), False),
        (_asks_for(label, "first name"), str(profile.get("first_name") or ""), False),
        (_asks_for(label, "last name"), str(profile.get("last_name") or ""), False),
        (_asks_for(label, "email") and "send" not in label, str(profile.get("email") or ""), False),
        (_asks_for(label, "phone", "mobile"), str(profile.get("phone") or ""), False),
        (_wants_link(label, "linkedin"), str(profile.get("linkedin") or ""), True),
        (_wants_link(label, "github"), str(profile.get("github") or ""), True),
        (_wants_link(label, "website") or _wants_link(label, "portfolio"), str(profile.get("website") or ""), True),
        (_school(label), str(profile.get("school") or ""), False),
        (_asks_for(label, "degree") and "advanced" not in label, str(profile.get("degree") or ""), False),
        (_asks_for(label, "major", "field of study"), str(profile.get("major") or ""), False),
        (_asks_for(label, "graduation", "graduate"), str(profile.get("graduation") or ""), True),
        (_asks_for(label, "gpa"), str(profile.get("gpa") or ""), True),
        (_asks_for(label, "city"), str(address.get("city") or ""), True),
        (_asks_for(label, "state"), str(address.get("state") or ""), True),
        (_asks_for(label, "postal", "postal code", "zip", "zip code"), str(address.get("postal_code") or ""), True),
        (_asks_for(label, "country"), str(address.get("country") or ""), False),
        (_asks_for(label, "address") and "email" not in label, str(address.get("line1") or ""), True),
    ]
    for matched, value, blank_if_missing in checks:
        if matched:
            cleaned = value.strip()
            if cleaned:
                return cleaned, False
            if blank_if_missing:
                return "", True
    return "", False


def _graduation_parts(text: str) -> tuple[str, str]:
    months = (
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    )
    found_month = next((month for month in months if month.lower() in text.lower()), "")
    found_year = ""
    match = re.search(r"\b(?:19|20)\d{2}\b", text)
    if match:
        found_year = match.group(0)
    return found_month, found_year


def _yes_no(label: str) -> bool:
    if _OPEN_QUESTION.match(label):
        return False
    return _YES_NO.match(label) is not None or _ASKS_YOU.search(label) is not None


def _asks_for(label: str, *keywords: str) -> bool:
    """True when the label asks for the fact itself, not a question that mentions it."""
    if _YES_NO.match(label) or _PROMPT.match(label):
        return False
    short = len(label.strip(" *?:")) <= _SHORT_LABEL
    for keyword in keywords:
        if not _has_word(label, keyword):
            continue
        if short or re.search(rf"\byour\s+(?:\w+\s+)?{re.escape(keyword)}\b", label):
            return True
    return False


def _school(label: str) -> bool:
    if any(token in label for token in ("diploma", "gpa", "major", "degree", "high school")):
        return False
    return _asks_for(label, "school", "school name", "university", "college")


def _wants_link(label: str, keyword: str) -> bool:
    if keyword not in label or _YES_NO.match(label) or _PROMPT.match(label):
        return False
    if any(token in label for token in ("url", "link", "profile", "handle", "username")):
        return True
    return len(label) <= _SHORT_LABEL


def _has_word(label: str, word: str) -> bool:
    return re.search(rf"\b{re.escape(word)}\b", label) is not None


def _eeo_answer(label: str, field: dict, profile: dict) -> str | None:
    eeo = profile.get("eeo") or {}
    mapping = (
        ("gender", "gender"),
        ("race", "race"),
        ("ethnic", "race"),
        ("veteran", "veteran"),
        ("disability", "disability"),
    )
    for needle, key in mapping:
        if needle not in label:
            continue
        preference = str(eeo.get(key) or "decline").strip()
        if preference.lower() == "decline":
            return _decline_option(field) or ""
        return _matching_option(field, preference) or preference
    return None


def _decline_option(field: dict) -> str:
    for option in field.get("options") or []:
        text = str(option.get("label") or "").lower()
        if any(hint in text for hint in _DECLINE):
            return str(option["label"])
    return ""


def _set_choice(field: dict, desired: str) -> bool:
    chosen = _matching_option(field, desired) or desired
    if field.get("options") and _matching_option(field, desired) is None:
        field["notes"] = f"No option matched {desired}."
        field["confidence"] = "check"
        field["source"] = "profile"
        field["skip_llm"] = True
        return True
    return _set(field, chosen, chosen, "profile", "high")


def _matching_option(field: dict, desired: str) -> str | None:
    options = field.get("options") or []
    if not options:
        return None
    wanted = desired.strip().lower()
    labels = [
        (str(option.get("label") or ""), str(option.get("label") or "").strip().lower())
        for option in options
    ]
    for original, label in labels:
        if label == wanted:
            return original
    for original, label in labels:
        if re.search(rf"\b{re.escape(wanted)}\b", label):
            return original
    hint = _degree_hint(wanted)
    if hint:
        for original, label in labels:
            if hint in label:
                return original
    return None


def _degree_hint(text: str) -> str:
    if "bachelor" in text or re.search(r"\bbs\b", text):
        return "bachelor"
    if "master" in text or "mba" in text or re.search(r"\bms\b", text):
        return "master"
    if "ph.d" in text or "phd" in text or "doctor of philosophy" in text:
        return "philosophy"
    if "associate" in text:
        return "associate"
    if "high school" in text:
        return "high school"
    if "j.d" in text or "juris" in text:
        return "j.d"
    return ""


def _set(field: dict, value: str, stored: str, source: str, confidence: str) -> bool:
    field["value"] = stored
    field["source"] = source
    field["confidence"] = confidence
    field["skip_llm"] = True
    return True


def _label(text: str) -> str:
    return " ".join(text.lower().replace("e-mail", "email").split())
