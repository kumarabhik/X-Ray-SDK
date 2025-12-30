# X-Ray-SDK: Decision Transparency for Multi-Step Systems

X-Ray-SDK is a lightweight **decision observability system** for debugging multi-step, non-deterministic pipelines such as LLM workflows, ranking systems, and rule-based decision engines.

Traditional logging and tracing answer *what happened*.  
X-Ray answers **why a particular decision was made**.

This repository contains:
- a reusable **X-Ray SDK**
- a **FastAPI backend** for storing decision traces
- a **dashboard UI** for visualizing decision trails
- a **demo application** that showcases the system end-to-end

---

## 🔍 Problem This Solves

Modern systems often involve pipelines like:

1. Generate keywords using an LLM
2. Retrieve candidates from a search system
3. Apply deterministic business filters
4. Use an LLM to make subjective relevance judgments
5. Rank and select a final output

When the final output is wrong, debugging is difficult because:
- decisions are spread across multiple steps
- LLM behavior is non-deterministic
- logs don’t capture *reasoning*

X-Ray makes every decision step **explicit, inspectable, and debuggable**.

---

## 🧠 Core Idea

An **Execution** represents one complete decision run.  
Each **Step** records:
- input
- output
- reasoning (why the step did what it did)
- artifacts (detailed data for deep inspection)
- timing and status

This creates a **decision trail** that can be replayed and compared across runs.

---

## 🧩 Project Structure
```
.
├── apps/
│   ├── api/                       # FastAPI backend
│   │   ├── main.py                # API endpoints (executions, steps, diff, demo)
│   │   └── llm.py                 # LLM adapter (mock / real)
│   │
│   └── dashboard/                 # Decision Trail Dashboard UI
│
├── packages/
│   └── xray_sdk/                  # Reusable X-Ray SDK
│       └── xray_sdk/
│           └── client.py          # SDK client (execution + step capture)
│
├── run_demo.py                    # Demo pipeline using the X-Ray SDK
├── README.md
└── .gitignore
```
---

## 🧱 Components

### 1. X-Ray SDK (`packages/xray_sdk`)

A lightweight wrapper developers integrate into their code.

Key features:
- `start_execution()` to begin a decision run
- `step()` context manager to capture each decision step
- captures input, output, reasoning, artifacts, errors
- automatic secret redaction
- fail-open behavior (never breaks the host app)
- local buffering if the backend is unavailable

Example usage:

```python
execution_id = XRAY.start_execution("competitor_selection")

with XRAY.step(execution_id, "keyword_generation", input={...}) as s:
    ...
    s.output({...})
    s.reason("Why these keywords were chosen")
2. Backend API (apps/api)
A FastAPI service that stores executions and steps.

Key endpoints:

POST /executions – create an execution

POST /executions/{id}/steps – record a decision step

GET /executions – list recent runs

GET /executions/{id} – fetch full decision trail

GET /executions/{a}/diff/{b} – compare two runs

POST /demo/run – generate a demo execution

Storage uses SQLite for simplicity (event-style decision storage).

3. Dashboard UI (apps/dashboard)
The dashboard visualizes the complete decision trail:

step-by-step timeline with status and duration

human-readable summaries and reasoning

per-candidate pass/fail explanations

toggle to inspect raw JSON

compare two executions to identify drift

export/share decision traces

The UI is designed for debugging usability, not just aesthetics.

4. Demo Application (run_demo.py)
A small, self-contained demo pipeline that simulates:

Keyword generation (LLM-like, non-deterministic)

Candidate search (mock API)

Deterministic business filtering

LLM-based relevance evaluation

Final selection

The demo exists purely to showcase X-Ray — all data is mocked.

🚀 Running Locally
Backend
bash
Copy code
cd apps/api
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
Dashboard
bash
Copy code
cd apps/dashboard
npm install
npm run dev
Demo
You can either:

click Run Demo in the dashboard
or

bash
Copy code
python run_demo.py
Then open the dashboard in your browser and inspect the generated execution.

🧪 Example Debugging Questions X-Ray Answers
Why did this candidate fail the price filter?

Did the LLM remove a valid competitor?

Which step caused the final output to change?

Why did run B behave differently from run A?

Was the issue deterministic or LLM-driven?

⚖️ Design Trade-offs
SQLite instead of a distributed DB: sufficient for demo + keeps focus on system design

Flexible JSON schemas: avoids premature schema lock-in

Human-readable + raw JSON views: supports both engineers and non-technical users

Fail-open SDK: observability should never break production systems

🔮 Future Improvements
With more time, this could be extended to:

support streaming steps

integrate with real search / ML systems

add role-based access and permissions

store traces in a scalable event store

add metrics and alerting on decision anomalies



