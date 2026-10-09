from __future__ import annotations

import json
import os

import httpx


def fill_gaps(fields: list[dict], profile: dict) -> None:
    pending = [
        field
        for field in fields
        if not field.get("value")
        and not field.get("skip_llm")
        and field.get("type") != "file"
    ]
    if not pending:
        return
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        for field in pending:
            field["source"] = "blank"
            field["confidence"] = "blank"
            field["notes"] = "No model key set. Answer this in review."
        return
    payload = {
        "model": os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": (
                    "You fill job application fields using only the profile JSON. "
                    "If a fact is missing, return null. Never invent GPA, sponsorship, "
                    "citizenship, graduation dates, demographics, or work history. "
                    'Return {"answers":[{"key":"...","value":null}]}.'
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "profile": public_profile(profile),
                        "questions": [
                            {
                                "key": field["key"],
                                "label": field["label"],
                                "options": [option["label"] for option in field.get("options") or []],
                            }
                            for field in pending
                        ],
                    }
                ),
            },
        ],
    }
    base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    try:
        response = httpx.post(
            f"{base}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
            timeout=60,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        parsed = json.loads(content)
    except (httpx.HTTPError, KeyError, json.JSONDecodeError, TypeError) as exc:
        for field in pending:
            field["notes"] = f"Model call failed ({exc}). Left blank."
        return
    by_key = {str(item.get("key")): item.get("value") for item in parsed.get("answers") or []}
    for field in pending:
        value = by_key.get(field["key"])
        if value is None or str(value).strip() == "":
            field["notes"] = "Model left this blank because the fact was not in your profile."
            continue
        text = str(value).strip()
        option_labels = [option["label"] for option in field.get("options") or []]
        if option_labels and text not in option_labels:
            field["notes"] = "Model answer was not one of the options. Left blank."
            continue
        field["value"] = text
        field["source"] = "llm"
        field["confidence"] = "check"
        field["notes"] = "Drafted by the model. Check it before you submit."


def public_profile(profile: dict) -> dict:
    cleaned: dict = {}
    for key, value in profile.items():
        if key in {"resume_path", "eeo"} or value in ("", None, [], {}):
            continue
        cleaned[key] = value
    return cleaned
