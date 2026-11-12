"""Tools that the PrepPilot agent can call. Each tool returns plain JSON-serialisable data."""
import datetime as dt
import json
import os
import re
import uuid

import requests
from bs4 import BeautifulSoup

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/126.0 Safari/537.36"}

# Common abbreviations so that "JS" in a job description matches "JavaScript" in a resume.
SYNONYMS = {
    "js": "javascript", "ts": "typescript", "py": "python", "ml": "machine learning",
    "dl": "deep learning", "ai": "artificial intelligence", "nlp": "natural language processing",
    "dsa": "data structures and algorithms", "data structures": "data structures and algorithms",
    "algorithms": "data structures and algorithms", "oop": "object oriented programming",
    "oops": "object oriented programming", "object-oriented programming": "object oriented programming",
    "dbms": "database management systems", "databases": "database management systems",
    "os": "operating systems", "cn": "computer networks", "networking": "computer networks",
    "k8s": "kubernetes", "postgres": "postgresql", "node": "node.js", "nodejs": "node.js",
    "react.js": "react", "reactjs": "react", "c sharp": "c#", "cpp": "c++", "gcp": "google cloud",
    "aws cloud": "aws", "amazon web services": "aws", "rest": "rest api", "restful apis": "rest api",
    "rest apis": "rest api", "git/github": "git", "github": "git", "sklearn": "scikit-learn",
    "communication skills": "communication", "ci/cd": "ci cd", "llms": "large language models",
    "llm": "large language models", "genai": "generative ai", "gen ai": "generative ai",
}
# A skill on the left is satisfied by any skill on the right.
IMPLIED_BY = {
    "sql": ["mysql", "postgresql", "oracle", "sqlite", "sql server", "database management systems"],
    "database management systems": ["mysql", "postgresql", "mongodb", "sql"],
    "java": ["spring boot"],
    "javascript": ["react", "node.js", "typescript"],
    "machine learning": ["scikit-learn", "deep learning", "tensorflow", "pytorch"],
    "cloud": ["aws", "azure", "google cloud"],
}


def norm(skill):
    s = re.sub(r"\s+", " ", str(skill).strip().lower())
    s = s.strip(" .,;:")
    return SYNONYMS.get(s, s)


def _contains_word(text, phrase):
    return re.search(r"(?<![a-z0-9+#])" + re.escape(phrase) + r"(?![a-z0-9+#])", text) is not None


class ToolBox:
    """Holds the inputs, the shared state the UI reads, and the tool functions."""

    def __init__(self, resume_text, jd_text, company, role, prep_days, outputs_dir, memory_path, offline=False):
        self.resume_text = resume_text or ""
        self.jd_text = jd_text or ""
        self.company = company or ""
        self.role = role or ""
        self.prep_days = int(prep_days)
        self.outputs_dir = outputs_dir
        self.memory_path = memory_path
        self.offline = offline
        os.makedirs(outputs_dir, exist_ok=True)
        self.state = {"company": self.company, "role": self.role, "match": None, "resources": {},
                      "plan": [], "report": "", "sources": [], "files": {}}

    # ------------------------------------------------------------- tool: inputs
    def read_resume(self):
        if not self.resume_text.strip():
            return {"error": "No resume was provided."}
        return {"resume_text": self.resume_text[:8000], "characters": len(self.resume_text)}

    def read_job_description(self):
        return {"company": self.company, "role": self.role, "job_description": self.jd_text[:8000],
                "days_available_for_preparation": self.prep_days,
                "today": dt.date.today().isoformat()}

    # --------------------------------------------------------------- tool: web
    def web_search(self, query, max_results=5):
        if self.offline:
            return {"error": "Web search is disabled in offline mode."}
        from ddgs import DDGS
        max_results = max(1, min(int(max_results or 5), 8))
        rows = DDGS().text(query, max_results=max_results)
        out = []
        for r in rows or []:
            url = r.get("href") or r.get("url") or ""
            out.append({"title": r.get("title", ""), "url": url, "snippet": (r.get("body") or "")[:300]})
            if url and url not in [s["url"] for s in self.state["sources"]]:
                self.state["sources"].append({"title": r.get("title", ""), "url": url})
        return {"query": query, "results": out}

    def fetch_webpage(self, url):
        if self.offline:
            return {"error": "Web access is disabled in offline mode."}
        resp = requests.get(url, headers=UA, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "noscript", "svg"]):
            tag.decompose()
        text = re.sub(r"\s+", " ", soup.get_text(" ")).strip()
        title = soup.title.get_text(strip=True) if soup.title else url
        if url not in [s["url"] for s in self.state["sources"]]:
            self.state["sources"].append({"title": title, "url": url})
        return {"url": url, "title": title, "text": text[:5000]}

    # ------------------------------------------------------- tool: skill match
    def analyze_skill_match(self, required_skills, resume_skills):
        """Deterministic comparison of job skills against resume skills."""
        req = []
        for s in required_skills or []:
            n = norm(s)
            if n and n not in req:
                req.append(n)
        have = {norm(s) for s in (resume_skills or []) if norm(s)}
        resume_lower = self.resume_text.lower()
        matched, missing = [], []
        for skill in req:
            ok = skill in have
            ok = ok or any(skill in h or h in skill for h in have if len(h) > 3 and len(skill) > 3)
            ok = ok or any(i in have for i in IMPLIED_BY.get(skill, []))
            ok = ok or (len(skill) > 2 and _contains_word(resume_lower, skill))
            (matched if ok else missing).append(skill)
        pct = round(100 * len(matched) / len(req)) if req else 0
        result = {"match_percentage": pct, "matched_skills": matched, "missing_skills": missing,
                  "required_count": len(req)}
        self.state["match"] = result
        return result

    # ---------------------------------------------------- tool: learning links
    def find_learning_resources(self, skill, max_results=3):
        if self.offline:
            return {"error": "Web search is disabled in offline mode."}
        from ddgs import DDGS
        max_results = max(1, min(int(max_results or 3), 5))
        found = []
        try:
            for r in DDGS().videos(f"{skill} tutorial for beginners", max_results=max_results) or []:
                url = r.get("content") or r.get("embed_url") or r.get("url") or r.get("href")
                if url:
                    found.append({"title": r.get("title", ""), "url": url, "type": "video",
                                  "source": r.get("publisher") or r.get("uploader") or "",
                                  "duration": r.get("duration", "")})
        except Exception:
            pass
        if len(found) < max_results:
            for r in DDGS().text(f"{skill} tutorial for beginners", max_results=max_results) or []:
                url = r.get("href") or r.get("url")
                if url:
                    found.append({"title": r.get("title", ""), "url": url, "type": "article", "source": "", "duration": ""})
        found = found[:max_results]
        self.state["resources"][skill] = found
        return {"skill": skill, "resources": found}

    # ------------------------------------------------------- tool: study plan
    def create_study_plan(self, days, start_date=None):
        """Save a day-by-day plan and an .ics calendar file the user can import."""
        try:
            start = dt.date.fromisoformat(start_date) if start_date else dt.date.today() + dt.timedelta(days=1)
        except ValueError:
            start = dt.date.today() + dt.timedelta(days=1)
        clean = []
        for i, d in enumerate(days or [], 1):
            day_no = int(d.get("day", i))
            clean.append({"day": day_no, "date": (start + dt.timedelta(days=day_no - 1)).isoformat(),
                          "topic": str(d.get("topic", "")), "tasks": str(d.get("tasks", "")),
                          "resource_url": str(d.get("resource_url", "") or "")})
        lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//PrepPilot//Study Plan//EN", "CALSCALE:GREGORIAN"]
        stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        for d in clean:
            day = dt.date.fromisoformat(d["date"])
            desc = (d["tasks"] + (" Resource: " + d["resource_url"] if d["resource_url"] else "")).replace("\n", " ")
            desc = desc.replace(",", "\\,").replace(";", "\\;")
            lines += ["BEGIN:VEVENT", f"UID:{uuid.uuid4()}@preppilot", f"DTSTAMP:{stamp}",
                      f"DTSTART;VALUE=DATE:{day.strftime('%Y%m%d')}",
                      f"DTEND;VALUE=DATE:{(day + dt.timedelta(days=1)).strftime('%Y%m%d')}",
                      f"SUMMARY:Prep Day {d['day']}: {d['topic']}".replace(",", "\\,"),
                      f"DESCRIPTION:{desc}", "END:VEVENT"]
        lines.append("END:VCALENDAR")
        path = os.path.join(self.outputs_dir, "study_plan.ics")
        with open(path, "w", encoding="utf-8", newline="\r\n") as f:
            f.write("\n".join(lines) + "\n")
        self.state["plan"] = clean
        self.state["files"]["study_plan.ics"] = path
        return {"saved_calendar_file": os.path.basename(path), "days_planned": len(clean),
                "first_day": clean[0]["date"] if clean else None}

    # ------------------------------------------------------ tool: save report
    def save_prep_report(self, markdown):
        path = os.path.join(self.outputs_dir, "prep_report.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(markdown)
        self.state["report"] = markdown
        self.state["files"]["prep_report.md"] = path
        return {"saved_file": os.path.basename(path), "characters": len(markdown)}

    # ------------------------------------------------------------ tool: memory
    def recall_past_sessions(self):
        if not os.path.exists(self.memory_path):
            return {"past_sessions": [], "note": "No earlier sessions found."}
        with open(self.memory_path, encoding="utf-8") as f:
            data = json.load(f)
        return {"past_sessions": data[-5:]}

    def remember_session(self):
        """Called by the app (not the model) after a run, to give the agent long-term memory."""
        m = self.state.get("match") or {}
        entry = {"date": dt.date.today().isoformat(), "company": self.company, "role": self.role,
                 "match_percentage": m.get("match_percentage"), "missing_skills": m.get("missing_skills", [])}
        data = []
        if os.path.exists(self.memory_path):
            try:
                with open(self.memory_path, encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = []
        data.append(entry)
        os.makedirs(os.path.dirname(self.memory_path), exist_ok=True)
        with open(self.memory_path, "w", encoding="utf-8") as f:
            json.dump(data[-20:], f, indent=2)

    # ------------------------------------------------------------ dispatching
    def call(self, name, args):
        fn = getattr(self, name, None)
        if name not in TOOL_SCHEMAS or fn is None:
            return {"error": f"Unknown tool '{name}'."}
        try:
            return fn(**(args or {}))
        except Exception as exc:  # errors go back to the model so it can adapt
            return {"error": f"{type(exc).__name__}: {exc}"[:500]}


STR = {"type": "string"}
TOOL_SCHEMAS = {
    "read_resume": ("Read the candidate's resume text.", {"type": "object", "properties": {}}),
    "read_job_description": ("Read the target company, role, job description, today's date and the number of "
                             "days available for preparation.", {"type": "object", "properties": {}}),
    "recall_past_sessions": ("Recall earlier preparation sessions (companies, match scores, skill gaps) from "
                             "long-term memory.", {"type": "object", "properties": {}}),
    "web_search": ("Search the web. Use it to research the company, its hiring process, interview rounds, "
                   "values and technology stack.",
                   {"type": "object", "properties": {"query": STR, "max_results": {"type": "integer"}},
                    "required": ["query"]}),
    "fetch_webpage": ("Download a web page and return its readable text.",
                      {"type": "object", "properties": {"url": STR}, "required": ["url"]}),
    "analyze_skill_match": ("Compare the skills required by the job with the skills in the resume. Returns the "
                            "match percentage, matched skills and missing skills. Always use this tool to compute "
                            "the match instead of estimating it.",
                            {"type": "object", "properties": {
                                "required_skills": {"type": "array", "items": STR,
                                                    "description": "Short skill names required by the job."},
                                "resume_skills": {"type": "array", "items": STR,
                                                  "description": "Short skill names found in the resume."}},
                             "required": ["required_skills", "resume_skills"]}),
    "find_learning_resources": ("Find beginner-friendly video tutorials or articles for one skill.",
                                {"type": "object", "properties": {"skill": STR, "max_results": {"type": "integer"}},
                                 "required": ["skill"]}),
    "create_study_plan": ("Save a day-by-day study plan and create a calendar (.ics) file. Each day needs a "
                          "topic, concrete tasks and, where possible, a resource URL found earlier.",
                          {"type": "object", "properties": {
                              "days": {"type": "array", "items": {"type": "object", "properties": {
                                  "day": {"type": "integer"}, "topic": STR, "tasks": STR, "resource_url": STR},
                                  "required": ["day", "topic", "tasks"]}},
                              "start_date": {"type": "string", "description": "YYYY-MM-DD; defaults to tomorrow."}},
                           "required": ["days"]}),
    "save_prep_report": ("Save the final preparation report as Markdown.",
                         {"type": "object", "properties": {"markdown": STR}, "required": ["markdown"]}),
}


def declarations():
    from google.genai import types
    return [types.FunctionDeclaration(name=n, description=d, parameters_json_schema=s)
            for n, (d, s) in TOOL_SCHEMAS.items()]
