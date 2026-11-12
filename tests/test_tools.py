"""Offline tests for the deterministic tools. Run with:  python tests/test_tools.py"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from agent.tools import ToolBox, declarations  # noqa: E402


def make_box():
    d = tempfile.mkdtemp()
    return ToolBox("Skills: Python, MySQL, Git. Projects in Flask.", "Need Java, SQL, Python", "Acme", "SE", 3,
                   d, os.path.join(d, "memory.json"), offline=True)


def test_skill_match():
    tb = make_box()
    r = tb.analyze_skill_match(["Java", "SQL", "Python", "JS", "OOPs"], ["Python", "MySQL", "Git"])
    assert r["match_percentage"] == 40, r
    assert "sql" in r["matched_skills"] and "python" in r["matched_skills"]
    assert set(r["missing_skills"]) == {"java", "javascript", "object oriented programming"}


def test_study_plan_calendar():
    tb = make_box()
    r = tb.create_study_plan([{"day": 1, "topic": "Java basics", "tasks": "Classes, objects"},
                              {"day": 2, "topic": "SQL", "tasks": "Joins; group by"}], start_date="2026-12-01")
    text = open(tb.state["files"]["study_plan.ics"], encoding="utf-8").read()
    assert r["days_planned"] == 2 and "DTSTART;VALUE=DATE:20261202" in text and text.count("BEGIN:VEVENT") == 2


def test_memory_and_errors():
    tb = make_box()
    tb.analyze_skill_match(["Java"], [])
    tb.remember_session()
    assert tb.recall_past_sessions()["past_sessions"][0]["company"] == "Acme"
    assert "error" in tb.call("unknown_tool", {})
    assert "error" in tb.call("web_search", {"query": "x"})  # offline mode returns an error, not a crash


def test_declarations():
    names = [d.name for d in declarations()]
    assert len(names) == 9 and "analyze_skill_match" in names


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
