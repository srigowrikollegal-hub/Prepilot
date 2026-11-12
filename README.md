# PrepPilot: An Agentic AI System for Personalised Placement Preparation

PrepPilot is an AI agent that prepares a student for a specific job. Given a resume and a job
description, it decides its own steps: it researches the company on the web, measures the skill match,
finds tutorials for the skill gaps, builds a day-by-day study plan (with a calendar file), writes a
preparation report, and then runs a mock interview that scores every answer.

Course: LLM & Agentic AI (BIS703B), CCA-2 project, K R Srigowri (1DT23IS064), DSATM.

---

## 1. How to run it on Windows (first time)

1. Install **Python 3.11 or newer** from https://www.python.org/downloads/
   On the first installer screen, tick **"Add python.exe to PATH"**.
2. Get a free **Gemini API key**: open https://aistudio.google.com, sign in, click
   **Get API key → Create API key**, and copy it.
3. Extract this zip, open the `PrepPilot` folder and **double-click `run_demo.bat`**.
   - The first run installs the libraries (2 to 4 minutes, needs internet).
   - It asks for your Gemini key once and saves it in a `.env` file on your laptop.
   - Your browser opens at http://localhost:8501.
4. Keep the black window open while using the app. Close it to stop.

From the second time onwards, double-clicking `run_demo.bat` starts the app in a few seconds.

## 1b. Run it online instead (if Windows Smart App Control blocks Python libraries)

1. Upload this folder's contents to a new GitHub repository named `PrepPilot`.
2. Sign in at https://share.streamlit.io with GitHub, click **Create app**, choose the repository,
   branch `main` and main file `app.py`.
3. Under **Advanced settings → Secrets**, add: `GEMINI_API_KEY = "your-key"`, then click **Deploy**.
4. Open the app link in Chrome on the laptop for the demo. Open it a few minutes early, because
   free apps go to sleep when unused.

## 2. Demo script (about 5 minutes)

1. **Introduce:** "PrepPilot is an agent, not a chatbot. I give it a goal and it chooses its own tools."
2. **Run Agent page:** upload your resume (or tick *Use the sample resume*), click
   *Load sample job description* (or paste a real one), then click **Run PrepPilot Agent**.
3. While it runs, point at the live trace: 🧠 reasoning → 🔧 tool call → 👁️ observation, repeated.
   Mention that it decides the order itself, recovers from tool errors and stops at a step limit.
4. **Results page:** skill match %, matched and missing skills, learning links, study plan,
   *Download calendar (.ics)* (open it to show the events), and the preparation report.
5. **Mock Interview page:** start the interview, answer two questions, show the score and feedback,
   then *End interview* to show the score chart.
6. **How It Works page:** explain the ReAct loop, the tool list, memory and the architecture diagram.

**Backup if the internet fails during the demo:** use **📂 Load last run** in the sidebar. It shows
the previous run's results without calling the API.

## 3. Project structure

```
PrepPilot/
├── app.py                 Streamlit web interface (4 pages)
├── agent/
│   ├── core.py            Agent loop (ReAct: reason → act → observe) and system prompt
│   ├── tools.py           9 tools + their JSON schemas
│   ├── llm.py             Gemini wrapper: model auto-selection, retries, fallback
│   └── interviewer.py     Mock-interview agent with structured JSON output
├── samples/               Sample resume and job description for testing
├── tests/test_tools.py    Offline tests for the deterministic tools
├── assets/architecture.png
├── outputs/               Generated study_plan.ics and prep_report.md
├── data/                  Long-term memory (memory.json) and last_run.json
├── requirements.txt
└── run_demo.bat           One-click launcher for Windows
```

## 4. Troubleshooting

| Problem | Fix |
|---|---|
| "Python was not found" | Install Python and tick "Add python.exe to PATH", then run again. |
| "Rate limit" messages | The free tier allows a limited number of requests per minute. The app waits and retries automatically. |
| Model not available | Choose another model in the sidebar, or leave it on *Auto*. |
| Wrong or expired key | Paste a new key in the sidebar and click *Save key on this laptop*. |
| Port already in use | Close the other PrepPilot window, then run `run_demo.bat` again. |

## 5. Run the tests

```
.venv\Scripts\python.exe tests\test_tools.py
```
