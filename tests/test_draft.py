import json
from pathlib import Path

from app.draft.bank import match_answer
from app.draft.profile_map import draft_fields
from app.draft.questions import greenhouse_fields

FIXTURE = Path(__file__).parent / "fixtures" / "greenhouse_questions.json"


def _profile():
    return {
        "first_name": "Alex",
        "last_name": "Example",
        "email": "alex.example@email.com",
        "phone": "555",
        "school": "The Ohio State University",
        "degree": "Bachelor of Science",
        "major": "Computer Science",
        "graduation": "May 2027",
        "gpa": "",
        "work_authorized": True,
        "needs_sponsorship": False,
        "us_citizen": True,
        "resume_path": "",
        "eeo": {"gender": "decline", "race": "decline", "veteran": "decline", "disability": "decline"},
        "address": {},
    }


def test_exact_and_fuzzy_answer_bank_do_not_cross_questions():
    answers = [
        {"question": "Will you now or in the future require sponsorship?", "answer": "No"},
        {"question": "What is your favorite programming language?", "answer": "Python"},
    ]
    sponsorship = match_answer(
        "Will you now or in the future require visa sponsorship for employment?",
        answers,
    )
    assert sponsorship is not None
    assert sponsorship["value"] == "No"
    language = match_answer("What is your favorite programming language?", answers)
    assert language["value"] == "Python"
    assert language["confidence"] == "high"
    unrelated = match_answer("Are you authorized to work in the United States?", answers)
    assert unrelated is None


def test_education_block_uses_degree_and_graduation():
    fields = greenhouse_fields(
        {
            "education": "education_required",
            "questions": [
                {
                    "label": "Resume/CV",
                    "required": True,
                    "fields": [{"name": "resume", "type": "input_file", "values": []}],
                }
            ],
        }
    )
    profile = _profile()
    profile["degree"] = "Bachelor of Science"
    profile["major"] = "Computer Science"
    profile["graduation"] = "May 2027"
    draft_fields(fields, profile, [], use_llm=False)
    by_label = {field["label"]: field for field in fields}
    assert by_label["School"]["value"] == "The Ohio State University"
    assert by_label["Degree"]["value"] == "Bachelor's Degree"
    assert by_label["Discipline"]["value"] == "Computer Science"
    assert by_label["End date month"]["value"] == "May"
    assert by_label["End date year"]["value"] == "2027"


def test_profile_draft_leaves_unknown_and_gpa_blank():
    fields = greenhouse_fields(json.loads(FIXTURE.read_text(encoding="utf-8")))
    draft_fields(fields, _profile(), [], use_llm=False)
    by_label = {field["label"]: field for field in fields}
    assert by_label["First Name"]["value"] == "Alex"
    assert by_label["Email"]["value"] == "alex.example@email.com"
    assert by_label["Will you now or in the future require sponsorship?"]["value"] == "No"
    assert by_label["Gender"]["value"] == "Decline To Self Identify"
    assert by_label["GPA"]["value"] == ""
    assert by_label["GPA"]["skip_llm"] is True
    assert by_label["Why do you want to work here?"]["value"] == ""
    assert by_label["Resume/CV"]["notes"]


def test_saved_answer_is_dropped_when_it_is_not_an_option():
    fields = [
        {
            "key": "source",
            "label": "How did you hear about Anduril?",
            "type": "select",
            "required": True,
            "options": [
                {"value": "1", "label": "Indeed"},
                {"value": "2", "label": "LinkedIn"},
            ],
            "value": "",
            "source": "blank",
            "confidence": "blank",
            "notes": "",
            "skip_llm": False,
        }
    ]
    answers = [{"question": "How did you hear about this job?", "answer": "Online job listing"}]
    draft_fields(fields, _profile(), answers, use_llm=False)
    assert fields[0]["value"] == ""
    assert "options" in fields[0]["notes"]
