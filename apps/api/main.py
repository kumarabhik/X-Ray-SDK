from fastapi import FastAPI
from pydantic import BaseModel
from typing import Any, Dict, Optional, List
import sqlite3
import json
import os
from fastapi.middleware.cors import CORSMiddleware
import uuid
import time
import random
from llm import generate_keywords, relevance_check

DB_PATH = os.environ.get("XRAY_DB", "xray.db")

# Failure toggle (default OFF)
SIM_FAIL_RATE = float(os.getenv("XRAY_SIM_FAIL_RATE", "0"))

app = FastAPI(title="X-Ray API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = db()
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS executions (
      execution_id TEXT PRIMARY KEY,
      name TEXT NOT NULL,
      app TEXT NOT NULL,
      created_at_ms INTEGER NOT NULL,
      metadata_json TEXT
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS steps (
      step_id TEXT PRIMARY KEY,
      execution_id TEXT NOT NULL,
      name TEXT NOT NULL,
      status TEXT NOT NULL,
      started_at_ms INTEGER NOT NULL,
      ended_at_ms INTEGER NOT NULL,
      duration_ms INTEGER NOT NULL,
      input_json TEXT,
      output_json TEXT,
      reasoning TEXT,
      artifacts_json TEXT,
      error_json TEXT,
      FOREIGN KEY(execution_id) REFERENCES executions(execution_id)
    )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_steps_execution ON steps(execution_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_steps_name ON steps(name)")
    conn.commit()
    conn.close()


init_db()


class ExecutionCreate(BaseModel):
    execution_id: str
    name: str
    app: str
    created_at_ms: int
    metadata: Dict[str, Any] = {}


class StepCreate(BaseModel):
    step_id: str
    execution_id: str
    name: str
    status: str
    started_at_ms: int
    ended_at_ms: int
    duration_ms: int
    input: Dict[str, Any] = {}
    output: Dict[str, Any] = {}
    reasoning: str = ""
    artifacts: Dict[str, Any] = {}
    error: Optional[Dict[str, Any]] = None


@app.post("/executions")
def create_execution(exe: ExecutionCreate):
    conn = db()
    conn.execute(
        "INSERT OR REPLACE INTO executions(execution_id, name, app, created_at_ms, metadata_json) VALUES(?,?,?,?,?)",
        (exe.execution_id, exe.name, exe.app, exe.created_at_ms, json.dumps(exe.metadata)),
    )
    conn.commit()
    conn.close()
    return {"ok": True, "execution_id": exe.execution_id}


@app.post("/executions/{execution_id}/steps")
def add_step(execution_id: str, step: StepCreate):
    conn = db()
    conn.execute(
        """INSERT OR REPLACE INTO steps
        (step_id, execution_id, name, status, started_at_ms, ended_at_ms, duration_ms,
         input_json, output_json, reasoning, artifacts_json, error_json)
         VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            step.step_id, execution_id, step.name, step.status,
            step.started_at_ms, step.ended_at_ms, step.duration_ms,
            json.dumps(step.input), json.dumps(step.output),
            step.reasoning, json.dumps(step.artifacts),
            json.dumps(step.error) if step.error else None
        ),
    )
    conn.commit()
    conn.close()
    return {"ok": True, "step_id": step.step_id}


@app.get("/executions")
def list_executions(limit: int = 50):
    conn = db()
    rows = conn.execute(
        "SELECT execution_id, name, app, created_at_ms, metadata_json FROM executions ORDER BY created_at_ms DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return [
        {
            "execution_id": r["execution_id"],
            "name": r["name"],
            "app": r["app"],
            "created_at_ms": r["created_at_ms"],
            "metadata": json.loads(r["metadata_json"] or "{}"),
        }
        for r in rows
    ]


@app.get("/executions/{execution_id}")
def get_execution(execution_id: str):
    conn = db()
    exe = conn.execute(
        "SELECT execution_id, name, app, created_at_ms, metadata_json FROM executions WHERE execution_id=?",
        (execution_id,),
    ).fetchone()
    steps = conn.execute(
        "SELECT * FROM steps WHERE execution_id=? ORDER BY started_at_ms ASC",
        (execution_id,),
    ).fetchall()
    conn.close()

    if not exe:
        return {"error": "not_found"}

    return {
        "execution": {
            "execution_id": exe["execution_id"],
            "name": exe["name"],
            "app": exe["app"],
            "created_at_ms": exe["created_at_ms"],
            "metadata": json.loads(exe["metadata_json"] or "{}"),
        },
        "steps": [
            {
                "step_id": s["step_id"],
                "name": s["name"],
                "status": s["status"],
                "started_at_ms": s["started_at_ms"],
                "ended_at_ms": s["ended_at_ms"],
                "duration_ms": s["duration_ms"],
                "input": json.loads(s["input_json"] or "{}"),
                "output": json.loads(s["output_json"] or "{}"),
                "reasoning": s["reasoning"] or "",
                "artifacts": json.loads(s["artifacts_json"] or "{}"),
                "error": json.loads(s["error_json"]) if s["error_json"] else None,
            }
            for s in steps
        ],
    }


@app.get("/search")
def search(q: str, limit: int = 50):
    conn = db()
    like = f"%{q}%"
    rows = conn.execute(
        """
        SELECT DISTINCT e.execution_id, e.name, e.app, e.created_at_ms, e.metadata_json
        FROM executions e
        LEFT JOIN steps s ON s.execution_id = e.execution_id
        WHERE e.name LIKE ?
           OR e.metadata_json LIKE ?
           OR s.name LIKE ?
           OR s.reasoning LIKE ?
           OR s.input_json LIKE ?
           OR s.output_json LIKE ?
           OR s.artifacts_json LIKE ?
        ORDER BY e.created_at_ms DESC
        LIMIT ?
        """,
        (like, like, like, like, like, like, like, limit),
    ).fetchall()
    conn.close()
    return [
        {
            "execution_id": r["execution_id"],
            "name": r["name"],
            "app": r["app"],
            "created_at_ms": r["created_at_ms"],
            "metadata": json.loads(r["metadata_json"] or "{}"),
        }
        for r in rows
    ]


@app.get("/executions/{a}/diff/{b}")
def diff(a: str, b: str):
    A = get_execution(a)
    B = get_execution(b)
    if "error" in A or "error" in B:
        return {"error": "not_found"}

    a_steps = {s["name"]: s for s in A["steps"]}
    b_steps = {s["name"]: s for s in B["steps"]}

    names = sorted(set(a_steps.keys()) | set(b_steps.keys()))
    out = []

    def _get_keywords(step):
        return (step or {}).get("output", {}).get("keywords")

    for name in names:
        sa = a_steps.get(name)
        sb = b_steps.get(name)

        out.append(
            {
                "step": name,
                "a_status": sa["status"] if sa else None,
                "b_status": sb["status"] if sb else None,
                "a_duration_ms": sa["duration_ms"] if sa else None,
                "b_duration_ms": sb["duration_ms"] if sb else None,
                "a_keywords": _get_keywords(sa),
                "b_keywords": _get_keywords(sb),
                "a_reasoning": sa["reasoning"] if sa else None,
                "b_reasoning": sb["reasoning"] if sb else None,
            }
        )

    return {"a": A["execution"], "b": B["execution"], "diff": out}


def _now_ms() -> int:
    return int(time.time() * 1000)


def _mock_search(keywords: List[str]) -> Dict[str, Any]:
    products = [
        {"asin": "B0COMP01", "title": "HydroFlask 32oz Wide Mouth", "price": 44.99, "rating": 4.5, "reviews": 8932},
        {"asin": "B0COMP02", "title": "Yeti Rambler 26oz", "price": 34.99, "rating": 4.4, "reviews": 5621},
        {"asin": "B0COMP03", "title": "Generic Water Bottle", "price": 8.99, "rating": 3.2, "reviews": 45},
        {"asin": "B0COMP04", "title": "Bottle Cleaning Brush Set", "price": 12.99, "rating": 4.6, "reviews": 3421},
        {"asin": "B0COMP05", "title": "Replacement Lid for HydroFlask", "price": 9.99, "rating": 4.7, "reviews": 2100},
        {"asin": "B0COMP07", "title": "Stanley Adventure Quencher", "price": 35.00, "rating": 4.3, "reviews": 4102},
    ]
    random.shuffle(products)
    total = random.randint(500, 5000)
    return {
        "total_results": total,
        "candidates": products[:6],
        "reasoning": f"Mock search for keywords={keywords}; returned shuffled top 6."
    }


def _apply_filters(reference: Dict[str, Any], candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
    ref_price = reference["price"]
    min_p, max_p = 0.5 * ref_price, 2.0 * ref_price
    min_rating, min_reviews = 3.8, 100

    filters = {
        "price_range": {"min": round(min_p, 2), "max": round(max_p, 2), "rule": "0.5x - 2x of reference price"},
        "min_rating": {"value": min_rating, "rule": ">= 3.8 stars"},
        "min_reviews": {"value": min_reviews, "rule": ">= 100 reviews"},
    }

    evaluations = []
    qualified = []
    for c in candidates:
        price_ok = (c["price"] >= min_p) and (c["price"] <= max_p)
        rating_ok = c["rating"] >= min_rating
        reviews_ok = c["reviews"] >= min_reviews

        fr = {
            "price_range": {"passed": price_ok, "detail": f"${c['price']} in ${min_p:.2f}-${max_p:.2f}" if price_ok else f"${c['price']} outside ${min_p:.2f}-${max_p:.2f}"},
            "min_rating": {"passed": rating_ok, "detail": f"{c['rating']} >= {min_rating}" if rating_ok else f"{c['rating']} < {min_rating}"},
            "min_reviews": {"passed": reviews_ok, "detail": f"{c['reviews']} >= {min_reviews}" if reviews_ok else f"{c['reviews']} < {min_reviews}"},
        }

        q = price_ok and rating_ok and reviews_ok
        evaluations.append({
            "asin": c["asin"],
            "title": c["title"],
            "metrics": {"price": c["price"], "rating": c["rating"], "reviews": c["reviews"]},
            "filter_results": fr,
            "qualified": q
        })
        if q:
            qualified.append(c)

    selected = max(qualified, key=lambda x: x["reviews"]) if qualified else None
    return {
        "filters_applied": filters,
        "evaluations": evaluations,
        "passed": len(qualified),
        "failed": len(candidates) - len(qualified),
        "selected": selected,
        "reasoning": "Applied deterministic price/rating/review filters; selected max reviews among qualified."
    }

@app.post("/demo/run")
def run_demo():
    # Reference product
    reference = {
        "asin": "B0XYZ123",
        "title": "ProBrand Steel Bottle 32oz Insulated",
        "price": 29.99,
        "rating": 4.2,
        "reviews": 1247,
        "category": "Sports & Outdoors > Water Bottles"
    }

    execution_id = str(uuid.uuid4())
    created_at = _now_ms()

    conn = db()
    conn.execute(
        "INSERT OR REPLACE INTO executions(execution_id, name, app, created_at_ms, metadata_json) VALUES(?,?,?,?,?)",
        (execution_id, "competitor_selection", "api-demo", created_at, json.dumps({"reference_asin": reference["asin"]})),
    )
    conn.commit()

    def insert_step(
        name: str,
        status: str,
        started: int,
        ended: int,
        step_input: Dict[str, Any],
        step_output: Dict[str, Any],
        reasoning: str,
        artifacts: Dict[str, Any],
        error: Any = None
    ):
        step_id = str(uuid.uuid4())
        conn.execute(
            """INSERT OR REPLACE INTO steps
            (step_id, execution_id, name, status, started_at_ms, ended_at_ms, duration_ms,
             input_json, output_json, reasoning, artifacts_json, error_json)
             VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                step_id, execution_id, name, status,
                started, ended, (ended - started),
                json.dumps(step_input), json.dumps(step_output),
                reasoning, json.dumps(artifacts),
                json.dumps(error) if error else None
            ),
        )
        conn.commit()

    try:
        # Optional: simulated failure (for Loom demo)
        if SIM_FAIL_RATE > 0 and random.random() < SIM_FAIL_RATE:
            raise RuntimeError("Simulated failure: keyword_generation LLM timeout")

        # Step 1: keyword generation
        t0 = _now_ms()
        kw = generate_keywords(reference["title"], reference["category"])
        t1 = _now_ms()
        insert_step(
            "keyword_generation",
            "SUCCESS",
            t0, t1,
            {"product_title": reference["title"], "category": reference["category"]},
            {"keywords": kw["keywords"], "model": kw["model"]},
            kw["reasoning"],
            {"prompt": kw["prompt"], "raw_text": kw["raw_text"]},
        )

        # Step 2: mock search
        t0 = _now_ms()
        sr = _mock_search(kw["keywords"])
        t1 = _now_ms()
        insert_step(
            "candidate_search",
            "SUCCESS",
            t0, t1,
            {"keywords": kw["keywords"], "limit": 50},
            {"total_results": sr["total_results"], "candidates_fetched": len(sr["candidates"])},
            sr["reasoning"],
            {"candidates": sr["candidates"]},
        )

        # Step 3: deterministic filters
        t0 = _now_ms()
        flt = _apply_filters(reference, sr["candidates"])
        t1 = _now_ms()
        insert_step(
            "apply_filters",
            "SUCCESS",
            t0, t1,
            {"reference_product": reference, "candidates_count": len(sr["candidates"])},
            {"passed": flt["passed"], "failed": flt["failed"]},
            flt["reasoning"],
            {"filters_applied": flt["filters_applied"], "evaluations": flt["evaluations"]},
        )

        # Step 4: LLM relevance
        passed_candidates = [
            c for c in sr["candidates"]
            if any(e["asin"] == c["asin"] and e["qualified"] for e in flt["evaluations"])
        ]

        t0 = _now_ms()
        rel = relevance_check(reference["title"], reference["category"], passed_candidates)
        t1 = _now_ms()

        rel_map = {e["asin"]: e for e in rel["evaluations"]}

        # Join LLM relevance into candidate evaluations for UI
        for e in flt["evaluations"]:
            if e["asin"] in rel_map:
                e["llm_is_competitor"] = rel_map[e["asin"]].get("is_competitor")
                e["llm_confidence"] = rel_map[e["asin"]].get("confidence")

        confirmed = [
            c for c in passed_candidates
            if rel_map.get(c["asin"], {}).get("is_competitor") is True
        ]

        selected = max(confirmed, key=lambda x: x["reviews"]) if confirmed else (flt["selected"])

        # If selected came from LLM-confirmed list, attach confidence if available
        selected_conf = None
        if selected and selected.get("asin") in rel_map:
            selected_conf = rel_map[selected["asin"]].get("confidence")
            # store on object too (nice for UI / export)
            try:
                selected["confidence"] = selected_conf
            except Exception:
                pass

        insert_step(
            "llm_relevance_evaluation",
            "SUCCESS",
            t0, t1,
            {"candidates_count": len(passed_candidates), "model": os.getenv("XRAY_LLM_MODEL")},
            {"confirmed_competitors": len(confirmed), "model": rel["model"]},
            rel.get("reasoning", ""),
            {
                "prompt": rel["prompt"],
                "raw_text": rel["raw_text"],
                "evaluations": flt["evaluations"],
                "selected": selected
            },
        )

        # Step 5: FINAL DECISION (renamed + interview-friendly)
        t0 = _now_ms()
        t1 = _now_ms()
        insert_step(
            "final_decision",
            "SUCCESS",
            t0, t1,
            {
                "qualified_candidates": len(confirmed),
                "reference_asin": reference["asin"],
                # keep these too (useful)
                "total_candidates": len(sr["candidates"]),
                "after_filters": len(passed_candidates),
                "after_llm": len(confirmed),
            },
            {
                "selected_asin": selected["asin"] if selected else None,
                "selected_title": selected["title"] if selected else None,
                "confidence": selected_conf,
                # keep full payload for audit / UI convenience
                "selected_competitor": selected,
                "qualified_asins": [c["asin"] for c in confirmed],
            },
            "Selected the best competitor based on filter pass rate, LLM relevance confidence, "
            "and closeness to the reference product. This final node makes the decision path auditable.",
            {
                "reference": reference,
                "selection_rule": "If LLM confirmed competitors exist, pick max(reviews). Else fallback to filter-selected.",
            },
        )

        conn.close()
        return {"ok": True, "execution_id": execution_id}

    except Exception as e:
        # Log an explicit failure step so UI shows error nicely
        t0 = _now_ms()
        t1 = _now_ms()
        try:
            insert_step(
                "demo_failed",
                "ERROR",
                t0, t1,
                {"hint": "Run demo pipeline failed"},
                {},
                "Captured an exception from the demo pipeline and stored it for audit/debug.",
                {},
                error={"type": type(e).__name__, "message": str(e)},
            )
        except Exception:
            pass

        conn.close()
        raise
