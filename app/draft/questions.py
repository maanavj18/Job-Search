from __future__ import annotations

TYPE_MAP = {
    "input_text": "text",
    "textarea": "textarea",
    "input_file": "file",
    "multi_value_single_select": "select",
    "multi_value_multi_select": "multi",
}


def empty_field(
    *,
    key: str,
    label: str,
    field_type: str = "text",
    required: bool = False,
    options: list[dict] | None = None,
) -> dict:
    return {
        "key": key,
        "label": label.strip(),
        "type": field_type,
        "required": required,
        "options": options or [],
        "value": "",
        "source": "blank",
        "confidence": "blank",
        "notes": "",
        "skip_llm": False,
    }


_MONTHS = [
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
]
_DEGREES = [
    "High School",
    "Associate's Degree",
    "Bachelor's Degree",
    "Master's Degree",
    "Engineer's Degree",
    "Doctor of Medicine (M.D.)",
    "Doctor of Philosophy (Ph.D.)",
    "Doctor of Law (J.D.)",
    "Other",
]


def greenhouse_fields(payload: dict) -> list[dict]:
    fields: list[dict] = []
    fields.extend(_questions(payload.get("questions") or []))
    education = str(payload.get("education") or "")
    if education.startswith("education_"):
        _insert_education(fields, required=education.endswith("required"))
    fields.extend(_questions(payload.get("location_questions") or []))
    for block in payload.get("compliance") or []:
        if isinstance(block, dict):
            fields.extend(_questions(block.get("questions") or []))
    demographic = payload.get("demographic_questions") or {}
    if isinstance(demographic, dict):
        fields.extend(_questions(demographic.get("questions") or []))
    return _dedupe(fields)


def _insert_education(fields: list[dict], *, required: bool) -> None:
    degree_options = [{"value": label, "label": label} for label in _DEGREES]
    month_options = [{"value": label, "label": label} for label in _MONTHS]
    extra = [
        empty_field(key="school--0", label="School", field_type="select", required=required),
        empty_field(
            key="degree--0",
            label="Degree",
            field_type="select",
            required=required,
            options=degree_options,
        ),
        empty_field(key="discipline--0", label="Discipline", field_type="select", required=required),
        empty_field(
            key="end-month--0",
            label="End date month",
            field_type="select",
            required=required,
            options=month_options,
        ),
        empty_field(key="end-year--0", label="End date year", field_type="text", required=required),
    ]
    index = next((i for i, field in enumerate(fields) if field["key"] == "resume"), len(fields) - 1)
    fields[index + 1 : index + 1] = extra


def _questions(items: list) -> list[dict]:
    fields: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or "").strip()
        parts = item.get("fields") or []
        if not label or not parts:
            continue
        part = parts[0]
        name = str(part.get("name") or label)
        field_type = TYPE_MAP.get(str(part.get("type") or ""), "text")
        options = [
            {"value": str(option.get("value", "")), "label": str(option.get("label", ""))}
            for option in (part.get("values") or [])
            if option.get("label")
        ]
        fields.append(
            empty_field(
                key=name,
                label=label,
                field_type=field_type,
                required=bool(item.get("required")),
                options=options,
            )
        )
    return fields


def _dedupe(fields: list[dict]) -> list[dict]:
    seen: set[str] = set()
    unique: list[dict] = []
    for field in fields:
        marker = field["key"] or field["label"]
        if marker in seen:
            continue
        seen.add(marker)
        unique.append(field)
    return unique


def standard_fields() -> list[dict]:
    labels = [
        ("first_name", "First Name", "text", True),
        ("last_name", "Last Name", "text", True),
        ("email", "Email", "text", True),
        ("phone", "Phone", "text", True),
        ("resume", "Resume", "file", True),
        ("linkedin", "LinkedIn Profile", "text", False),
        ("website", "Website", "text", False),
    ]
    return [
        empty_field(key=key, label=label, field_type=kind, required=required)
        for key, label, kind, required in labels
    ]
