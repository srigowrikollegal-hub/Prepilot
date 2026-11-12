"""Mock interview agent: asks one question at a time, evaluates each answer and adapts."""
import json
import re

from google.genai import types

INTERVIEWER_PROMPT = """You are a fair but demanding interviewer for the {role} role at {company}.
Job description (shortened): {jd}
Candidate's skill gaps found earlier: {gaps}
Company insights found earlier: {insights}

Ask one question at a time. Mix technical questions on the job's skills, one coding/problem-solving
question described in words, and HR/behavioural questions. Probe the skill gaps. Keep each question
under 50 words. When the candidate answers, evaluate it honestly on a 0-10 scale."""

QUESTION_SCHEMA = {
    "type": "object",
    "properties": {
        "question": {"type": "string"},
        "category": {"type": "string", "enum": ["Technical", "Coding", "HR", "Company"]},
    },
    "required": ["question", "category"],
}

EVAL_SCHEMA = {
    "type": "object",
    "properties": {
        "score": {"type": "integer", "minimum": 0, "maximum": 10},
        "strengths": {"type": "string"},
        "improvements": {"type": "string"},
        "model_answer": {"type": "string"},
        "next_question": {"type": "string"},
        "next_category": {"type": "string", "enum": ["Technical", "Coding", "HR", "Company"]},
    },
    "required": ["score", "strengths", "improvements", "model_answer", "next_question", "next_category"],
}


def _parse(text):
    try:
        return json.loads(text)
    except Exception:
        m = re.search(r"\{.*\}", text or "", re.S)
        return json.loads(m.group(0)) if m else {}


class Interviewer:
    def __init__(self, llm, company, role, jd, gaps, insights):
        self.llm = llm
        self.system = INTERVIEWER_PROMPT.format(company=company or "the company", role=role or "software",
                                                jd=(jd or "")[:2500], gaps=", ".join(gaps or []) or "none recorded",
                                                insights=(insights or "")[:1500])
        self.history = []  # list of dicts: question, category, answer, evaluation

    def _ask(self, prompt, schema):
        cfg = types.GenerateContentConfig(system_instruction=self.system, temperature=0.6,
                                          response_mime_type="application/json", response_json_schema=schema)
        resp = self.llm.generate(prompt, cfg)
        return _parse(resp.text)

    def first_question(self):
        out = self._ask("Start the interview with your first question.", QUESTION_SCHEMA)
        return out.get("question", "Tell me about yourself."), out.get("category", "HR")

    def evaluate(self, question, category, answer):
        past = "\n".join(f"Q: {h['question']}" for h in self.history[-6:])
        prompt = (f"Questions already asked:\n{past}\n\nCurrent question ({category}): {question}\n"
                  f"Candidate's answer: {answer}\n\nEvaluate the answer and give the next question. "
                  "Do not repeat earlier questions.")
        ev = self._ask(prompt, EVAL_SCHEMA)
        ev["score"] = max(0, min(10, int(ev.get("score", 0))))
        self.history.append({"question": question, "category": category, "answer": answer, "evaluation": ev})
        return ev
