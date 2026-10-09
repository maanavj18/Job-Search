from __future__ import annotations

import os
from pathlib import Path

import yaml

from app.paths import repo_root


def load_env(root: Path | None = None) -> None:
    path = (root or repo_root()) / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _read_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a YAML mapping")
    return data


def load_sources(root: Path | None = None) -> list[dict]:
    data = _read_yaml((root or repo_root()) / "config" / "sources.yaml")
    sources = data.get("sources") or []
    if not isinstance(sources, list):
        raise ValueError("config/sources.yaml: sources must be a list")
    return sources


def load_filters(root: Path | None = None) -> dict:
    data = _read_yaml((root or repo_root()) / "config" / "filters.yaml")
    sections = data.get("sections") or ["software-engineering"]
    return {
        "sections": list(sections),
        "max_age_days": data.get("max_age_days"),
    }


def load_profile(root: Path | None = None) -> tuple[dict, bool]:
    base = root or repo_root()
    path = base / "profile" / "profile.yaml"
    using_example = not path.exists()
    if using_example:
        path = base / "profile" / "profile.example.yaml"
    profile = _read_yaml(path)
    profile.setdefault("eeo", {})
    profile.setdefault("address", {})
    return profile, using_example


def load_answers(root: Path | None = None) -> list[dict]:
    base = root or repo_root()
    path = base / "profile" / "answers.yaml"
    if not path.exists():
        path = base / "profile" / "answers.example.yaml"
    data = _read_yaml(path)
    answers = data.get("answers") or []
    return [item for item in answers if isinstance(item, dict) and item.get("question")]


def answers_file(root: Path | None = None) -> Path:
    return (root or repo_root()) / "profile" / "answers.yaml"


def save_answers(answers: list[dict], root: Path | None = None) -> None:
    path = answers_file(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump({"answers": answers}, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def upsert_answer(question: str, answer: str, root: Path | None = None) -> None:
    question = " ".join(question.split()).strip()
    answer = answer.strip()
    if not question or not answer:
        return
    answers = []
    path = answers_file(root)
    if path.exists():
        answers = load_answers_from(path)
    else:
        example = (root or repo_root()) / "profile" / "answers.example.yaml"
        if example.exists():
            answers = load_answers_from(example)
    replaced = False
    for item in answers:
        if _norm(item.get("question", "")) == _norm(question):
            item["question"] = question
            item["answer"] = answer
            replaced = True
            break
    if not replaced:
        answers.append({"question": question, "answer": answer})
    save_answers(answers, root)


def load_answers_from(path: Path) -> list[dict]:
    data = _read_yaml(path)
    answers = data.get("answers") or []
    return [dict(item) for item in answers if isinstance(item, dict)]


def _norm(text: str) -> str:
    return " ".join(text.lower().split())
