"""The PrepPilot agent loop: plan, act with tools, observe, repeat (ReAct style)."""
import json
import time

from google.genai import types

from .tools import declarations

SYSTEM_PROMPT = """You are PrepPilot, an autonomous placement-preparation agent for engineering students.
Your goal: prepare the candidate for the target job as well as possible, using your tools.

Work in this order, deciding the details yourself:
1. Read the job description and the resume. Recall past sessions to personalise your advice.
2. Research the company with web_search (hiring process, interview rounds, values, technology stack).
   Fetch a page only if a search snippet is not enough. Do at most 3 searches.
3. Extract short skill names from the job and from the resume, then call analyze_skill_match.
   Never estimate the match yourself.
4. For the most important missing skills (at most 3), call find_learning_resources.
5. Call create_study_plan with exactly the number of days available. Put the weakest skills first,
   include aptitude, coding practice and one revision/mock-interview day, and reuse resource URLs you found.
6. Call save_prep_report with a Markdown report containing: company insights (with source links),
   skill match summary, skill gaps and why they matter, the study plan, 8 likely interview questions
   (technical and HR) tailored to this company and resume, and 3 tips.
7. Finish with a 3-4 sentence summary for the candidate.

Rules: before each tool call, write one short sentence explaining what you are doing and why.
If a tool returns an error, adapt (for example, change the query) instead of stopping.
Never invent facts about the company; rely on search results and say when information was not found."""


def build_task(company, role):
    return (f"Prepare me for the {role or 'software'} role at {company or 'the target company'}. "
            "Use your tools to read my inputs, research the company, measure my skill match, "
            "find resources, plan my preparation and save a report.")


def _summarise(result, limit=600):
    text = json.dumps(result, ensure_ascii=False)
    return text if len(text) <= limit else text[:limit] + " ..."


def run_agent(llm, toolbox, task, on_event, max_steps=16):
    """Run the agent until it gives a final answer or reaches max_steps. Returns the trace."""
    trace = []

    def emit(ev):
        ev["time"] = round(time.time(), 2)
        trace.append(ev)
        on_event(ev)

    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        tools=[types.Tool(function_declarations=declarations())],
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        temperature=0.3,
    )
    contents = [types.Content(role="user", parts=[types.Part.from_text(text=task)])]
    emit({"type": "goal", "text": task, "model": llm.model})

    for step in range(1, max_steps + 1):
        resp = llm.generate(contents, config)
        cand = resp.candidates[0] if resp.candidates else None
        if cand is None or cand.content is None or not cand.content.parts:
            emit({"type": "error", "step": step, "text": "The model returned an empty response."})
            break
        contents.append(cand.content)  # keeps thought signatures intact for Gemini 3 models

        thoughts = [p.text for p in cand.content.parts if getattr(p, "text", None) and not getattr(p, "thought", False)]
        calls = [p.function_call for p in cand.content.parts if getattr(p, "function_call", None)]
        if not calls:
            emit({"type": "final", "step": step, "text": "\n".join(thoughts).strip()})
            return trace
        if thoughts:
            emit({"type": "thought", "step": step, "text": "\n".join(thoughts).strip()})

        reply_parts = []
        for fc in calls:
            args = dict(fc.args or {})
            emit({"type": "action", "step": step, "tool": fc.name, "args": args})
            t0 = time.time()
            result = toolbox.call(fc.name, args)
            emit({"type": "observation", "step": step, "tool": fc.name, "summary": _summarise(result),
                  "ok": "error" not in result, "secs": round(time.time() - t0, 2)})
            reply_parts.append(types.Part(function_response=types.FunctionResponse(
                id=fc.id, name=fc.name, response={"result": result})))
        contents.append(types.Content(role="user", parts=reply_parts))

    emit({"type": "final", "step": max_steps,
          "text": "I reached the step limit. The results gathered so far are shown in the Results tab."})
    return trace
