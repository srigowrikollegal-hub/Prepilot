"""PrepPilot: an agentic AI assistant for placement preparation (Streamlit app)."""
import io
import json
import os
import time
from collections import Counter

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from agent.core import build_task, run_agent
from agent.interviewer import Interviewer
from agent.llm import LLM, PREFERRED_MODELS
from agent.tools import TOOL_SCHEMAS, ToolBox

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "outputs")
DATA = os.path.join(BASE, "data")
MEMORY = os.path.join(DATA, "memory.json")
LAST_RUN = os.path.join(DATA, "last_run.json")
os.makedirs(OUT, exist_ok=True)
os.makedirs(DATA, exist_ok=True)
load_dotenv(os.path.join(BASE, ".env"))

st.set_page_config(page_title="PrepPilot", page_icon="🧭", layout="wide")
st.markdown("""
<style>
.chip{display:inline-block;padding:3px 10px;margin:3px;border-radius:14px;font-size:0.86rem;font-weight:600}
.ok{background:#dff5ea;color:#11663f;border:1px solid #9fdcbd}
.miss{background:#fde7e3;color:#a2321a;border:1px solid #f4b3a5}
.small{color:#6b6b6b;font-size:0.85rem}
</style>""", unsafe_allow_html=True)

ss = st.session_state
for k, v in {"run": None, "interview": None, "jd_text": "", "company": "", "role": ""}.items():
    ss.setdefault(k, v)


def read_text(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def resume_from_upload(upload):
    if upload is None:
        return ""
    data = upload.getvalue()
    if upload.name.lower().endswith(".pdf"):
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        return "\n".join((p.extract_text() or "") for p in reader.pages)
    return data.decode("utf-8", errors="ignore")


def render_event(ev, box):
    t = ev["type"]
    if t == "goal":
        box.markdown(f"🎯 **Goal:** {ev['text']}  \n<span class='small'>Model: {ev.get('model','')}</span>",
                     unsafe_allow_html=True)
    elif t == "thought":
        box.markdown(f"🧠 **Step {ev['step']} · Reasoning:** {ev['text']}")
    elif t == "action":
        args = json.dumps(ev["args"], ensure_ascii=False)
        args = args if len(args) < 220 else args[:220] + " ...}"
        box.markdown(f"🔧 **Action:** `{ev['tool']}` {args}")
    elif t == "observation":
        icon = "👁️" if ev.get("ok", True) else "⚠️"
        box.caption(f"{icon} Observation from {ev['tool']} ({ev.get('secs', 0)} s): {ev['summary'][:400]}")
    elif t == "final":
        box.success(f"✅ **Final answer:** {ev['text']}")
    elif t == "error":
        box.error(ev["text"])
    elif t == "log":
        box.info(ev["text"])


# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.header("⚙️ Settings")
    env_key = os.getenv("GEMINI_API_KEY", "")
    if not env_key:
        try:  # Streamlit Community Cloud keeps the key in the app's Secrets
            env_key = str(st.secrets.get("GEMINI_API_KEY", ""))
        except Exception:
            env_key = ""
    ON_LAPTOP = os.name == "nt"
    key_in = st.text_input("Gemini API key", type="password", value="",
                           placeholder="Loaded automatically" if env_key else "Paste your key here")
    api_key = key_in.strip() or env_key
    if ON_LAPTOP and key_in.strip() and st.button("Save key on this laptop (.env)"):
        with open(os.path.join(BASE, ".env"), "w", encoding="utf-8") as f:
            f.write(f"GEMINI_API_KEY={key_in.strip()}\n")
        st.success("Saved. It will load automatically next time.")
    st.caption("✅ Key ready" if api_key else "❌ No key yet: get one free at aistudio.google.com")
    model_choice = st.selectbox("Model", ["Auto (recommended)"] + PREFERRED_MODELS)
    prep_days = st.slider("Days until the interview", 3, 14, 7)
    max_steps = st.slider("Maximum agent steps", 8, 24, 16)
    st.divider()
    st.subheader("🗂️ Memory")
    if os.path.exists(MEMORY):
        mem = json.load(open(MEMORY, encoding="utf-8"))
        for m in reversed(mem[-5:]):
            st.caption(f"{m['date']} · {m['company']} · {m['role']} · match {m.get('match_percentage')}%")
        if st.button("Clear memory"):
            os.remove(MEMORY)
            st.rerun()
    else:
        st.caption("No past sessions yet.")
    if os.path.exists(LAST_RUN) and st.button("📂 Load last run (works offline)"):
        ss.run = json.load(open(LAST_RUN, encoding="utf-8"))
        go_to(PAGES[1])
        st.rerun()

st.title("🧭 PrepPilot")
st.markdown("An **agentic AI** assistant that researches a company, measures your skill match, plans your "
            "preparation and interviews you, choosing its own steps and tools.")

PAGES = ["🚀 Run Agent", "📊 Results", "🎤 Mock Interview", "🧠 How It Works"]
if "page_picker" not in ss:
    ss.page_picker = PAGES[0]
picked = st.segmented_control("Section", PAGES, key="page_picker", label_visibility="collapsed")
page = picked or ss.get("page", PAGES[0])
ss.page = page


def go_to(name):
    ss.page = name
    ss.page_picker = name


# ---------------------------------------------------------------- run tab
if page == PAGES[0]:
    c1, c2 = st.columns([1, 1.4], gap="large")
    with c1:
        st.subheader("1 · Your resume")
        upload = st.file_uploader("Upload resume (PDF or TXT)", type=["pdf", "txt"])
        use_sample_resume = st.checkbox("Use the sample resume instead", value=upload is None)
        resume_text = read_text(os.path.join(BASE, "samples", "sample_resume.txt")) if use_sample_resume \
            else resume_from_upload(upload)
        if resume_text:
            with st.expander("Preview resume text"):
                st.text(resume_text[:2500])
    with c2:
        st.subheader("2 · Target job")
        if st.button("Load sample job description"):
            ss.company, ss.role = "Infosys", "Systems Engineer"
            ss.jd_text = read_text(os.path.join(BASE, "samples", "sample_job_description.txt"))
        company = st.text_input("Company", key="company")
        role = st.text_input("Role", key="role")
        jd_text = st.text_area("Job description", key="jd_text", height=230,
                               placeholder="Paste the job description here")

    st.subheader("3 · Let the agent work")
    go = st.button("▶ Run PrepPilot Agent", type="primary", width="stretch")
    if go:
        missing = [n for n, v in [("API key", api_key), ("resume", resume_text), ("company", company),
                                  ("job description", jd_text)] if not v]
        if missing:
            st.error("Please provide: " + ", ".join(missing))
        else:
            tb = ToolBox(resume_text, jd_text, company, role, prep_days, OUT, MEMORY)
            with st.status("PrepPilot is working...", expanded=True) as status:
                box = st.container()
                try:
                    llm = LLM(api_key, None if model_choice.startswith("Auto") else model_choice,
                              log=lambda m: render_event({"type": "log", "text": m}, box))
                    t0 = time.time()
                    trace = run_agent(llm, tb, build_task(company, role), lambda ev: render_event(ev, box), max_steps)
                    secs = round(time.time() - t0, 1)
                    status.update(label=f"Done in {secs} s · {len([e for e in trace if e['type'] == 'action'])} tool calls", state="complete", expanded=True)
                    tb.remember_session()
                    ss.run = {"trace": trace, "state": tb.state, "company": company, "role": role,
                              "jd": jd_text, "secs": secs, "model": llm.model}
                    with open(LAST_RUN, "w", encoding="utf-8") as f:
                        json.dump(ss.run, f, indent=2, ensure_ascii=False)
                    ss.interview = None
                except Exception as exc:
                    status.update(label="Stopped with an error", state="error")
                    st.error(f"{type(exc).__name__}: {exc}")
            if ss.run:
                st.success("Finished. See the results, then try the mock interview.")
                st.button("📊 Open results", type="primary", on_click=go_to, args=(PAGES[1],))
    elif ss.run:
        with st.expander("Agent trace of the last run", expanded=False):
            for ev in ss.run["trace"]:
                render_event(ev, st)

# ---------------------------------------------------------------- results tab
if page == PAGES[1]:
    run = ss.run
    if not run:
        st.info("Run the agent first, or load the last run from the sidebar.")
    else:
        state = run["state"]
        match = state.get("match") or {}
        actions = [e for e in run["trace"] if e["type"] == "action"]
        steps = max([e.get("step", 0) for e in run["trace"]] or [0])
        st.subheader(f"{run['role']} at {run['company']}")
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Skill match", f"{match.get('match_percentage', 0)}%")
        m2.metric("Matched skills", len(match.get("matched_skills", [])))
        m3.metric("Skill gaps", len(match.get("missing_skills", [])))
        m4.metric("Tool calls", len(actions))
        m5.metric("Time taken", f"{run.get('secs', 0)} s")
        st.progress(min(100, match.get("match_percentage", 0)) / 100)
        st.markdown("**Matched:** " + "".join(f"<span class='chip ok'>{s}</span>" for s in match.get("matched_skills", [])),
                    unsafe_allow_html=True)
        st.markdown("**Missing:** " + "".join(f"<span class='chip miss'>{s}</span>" for s in match.get("missing_skills", [])),
                    unsafe_allow_html=True)

        left, right = st.columns([1.3, 1], gap="large")
        with left:
            st.markdown("#### 📅 Study plan")
            if state.get("plan"):
                df = pd.DataFrame(state["plan"])[["day", "date", "topic", "tasks", "resource_url"]]
                st.dataframe(df, hide_index=True, width="stretch",
                             column_config={"resource_url": st.column_config.LinkColumn("resource")})
                ics = state["files"].get("study_plan.ics")
                if ics and os.path.exists(ics):
                    st.download_button("⬇ Download calendar (.ics)", open(ics, "rb").read(), "study_plan.ics")
        with right:
            st.markdown("#### 🎓 Learning resources")
            for skill, items in state.get("resources", {}).items():
                st.markdown(f"**{skill}**")
                for it in items:
                    st.markdown(f"- [{it['title'][:70]}]({it['url']}) <span class='small'>{it.get('type','')}</span>",
                                unsafe_allow_html=True)
            st.markdown("#### 🛠️ Tool usage")
            if actions:
                counts = Counter(a["tool"] for a in actions)
                st.bar_chart(pd.DataFrame({"calls": counts}).sort_values("calls"), horizontal=True)

        st.markdown("#### 📝 Preparation report")
        if state.get("report"):
            with st.container(border=True):
                st.markdown(state["report"])
            st.download_button("⬇ Download report (.md)", state["report"], "prep_report.md")
        if state.get("sources"):
            with st.expander("Sources the agent used"):
                for s in state["sources"]:
                    st.markdown(f"- [{s['title'] or s['url']}]({s['url']})")
        st.download_button("⬇ Download agent trace (.json)", json.dumps(run["trace"], indent=2), "agent_trace.json")
        st.caption(f"Model used: {run.get('model')} · Steps: {steps}")

# ---------------------------------------------------------------- interview tab
if page == PAGES[2]:
    run = ss.run
    if not run:
        st.info("Run the agent first so the interviewer knows the company, role and your skill gaps.")
    elif not api_key:
        st.warning("Add your Gemini API key in the sidebar.")
    else:
        iv = ss.interview
        if iv is None:
            st.markdown(f"The interviewer will ask questions for **{run['role']} at {run['company']}**, "
                        "focusing on your skill gaps, and score every answer.")
            if st.button("🎤 Start mock interview", type="primary"):
                llm = LLM(api_key, run.get("model"))
                gaps = (run["state"].get("match") or {}).get("missing_skills", [])
                agent = Interviewer(llm, run["company"], run["role"], run["jd"], gaps, run["state"].get("report", ""))
                q, cat = agent.first_question()
                ss.interview = {"agent": agent, "q": q, "cat": cat, "done": False}
                st.rerun()
        else:
            agent = iv["agent"]
            for i, h in enumerate(agent.history, 1):
                with st.chat_message("assistant", avatar="🧑‍💼"):
                    st.markdown(f"**Q{i} · {h['category']}:** {h['question']}")
                with st.chat_message("user"):
                    st.markdown(h["answer"])
                ev = h["evaluation"]
                with st.chat_message("assistant", avatar="📋"):
                    st.markdown(f"**Score: {ev['score']}/10**  \n✅ {ev['strengths']}  \n🔧 {ev['improvements']}")
                    with st.expander("A stronger answer"):
                        st.markdown(ev["model_answer"])
            scores = [h["evaluation"]["score"] for h in agent.history]
            if not iv["done"]:
                with st.chat_message("assistant", avatar="🧑‍💼"):
                    st.markdown(f"**Q{len(agent.history) + 1} · {iv['cat']}:** {iv['q']}")
                ans = st.chat_input("Type your answer and press Enter")
                cols = st.columns(2)
                if cols[0].button("End interview and see summary"):
                    iv["done"] = True
                    st.rerun()
                if ans:
                    with st.spinner("Evaluating your answer..."):
                        ev = agent.evaluate(iv["q"], iv["cat"], ans)
                    iv["q"], iv["cat"] = ev["next_question"], ev["next_category"]
                    st.rerun()
            if scores:
                st.markdown("#### 📈 Your scores")
                st.line_chart(pd.DataFrame({"score": scores}, index=range(1, len(scores) + 1)))
            if iv["done"] and scores:
                avg = sum(scores) / len(scores)
                st.success(f"Interview finished: {len(scores)} questions, average score {avg:.1f}/10.")
                if st.button("Start a new interview"):
                    ss.interview = None
                    st.rerun()

# ---------------------------------------------------------------- how tab
if page == PAGES[3]:
    st.markdown("""
**PrepPilot is an agent, not a chatbot.** It is given a goal and decides for itself which tools to use
and in what order, following the *Reason → Act → Observe* loop:

1. **Reason:** the Gemini model reads the goal and everything it has learned so far, and decides the next step.
2. **Act:** it calls one of its tools (web search, skill matcher, planner and so on).
3. **Observe:** the tool's result is added to its working memory, and the loop repeats until the goal is met.

It also has **long-term memory** (past sessions saved on this laptop), **guardrails** (step limit,
retries, tool errors fed back to the model) and a second agent, the **interviewer**, that adapts its
questions to your skill gaps.
""")
    st.markdown("#### Tools available to the agent")
    st.table(pd.DataFrame([{"Tool": n, "What it does": d} for n, (d, _) in TOOL_SCHEMAS.items()]))
    arch = os.path.join(BASE, "assets", "architecture.png")
    if os.path.exists(arch):
        st.image(arch, caption="System architecture")
