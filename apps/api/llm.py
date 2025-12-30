import json
import os
from typing import Any, Dict, List

from openai import OpenAI

GROQ_BASE_URL = "https://api.groq.com/openai/v1"  # OpenAI-compatible :contentReference[oaicite:2]{index=2}

def _must_env(key: str) -> str:
    v = os.getenv(key)
    if not v:
        raise RuntimeError(f"Missing required env var: {key}")
    return v

def get_client() -> OpenAI:
    # REQUIRED
    api_key = _must_env("GROQ_API_KEY")
    return OpenAI(api_key=api_key, base_url=GROQ_BASE_URL)

def llm_model() -> str:
    # REQUIRED (set to a Groq-supported model in .env)
    return _must_env("XRAY_LLM_MODEL")

def _parse_strict_json(text: str) -> Dict[str, Any]:
    try:
        return json.loads(text)
    except Exception:
        raise RuntimeError(f"LLM did not return valid JSON. Raw output: {text[:800]}")

def generate_keywords(title: str, category: str) -> Dict[str, Any]:
    client = get_client()
    model = llm_model()

    prompt = (
        "You generate search keywords for competitor discovery.\n"
        f"Product title: {title}\n"
        f"Category: {category}\n\n"
        "Return STRICT JSON:\n"
        "{\n"
        '  "keywords": ["..."],\n'
        '  "reasoning": "..." \n'
        "}\n"
        "No markdown. No extra keys."
    )

    resp = client.responses.create(model=model, input=prompt)
    text = resp.output_text or ""
    obj = _parse_strict_json(text)

    keywords = obj.get("keywords")
    reasoning = obj.get("reasoning", "")
    if not isinstance(keywords, list) or not all(isinstance(x, str) for x in keywords):
        raise RuntimeError(f"Invalid keywords format from LLM. Raw: {text[:800]}")

    return {"keywords": keywords, "reasoning": reasoning, "raw_text": text, "prompt": prompt, "model": model}

def relevance_check(reference_title: str, reference_category: str, candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
    client = get_client()
    model = llm_model()

    payload = {
        "reference": {"title": reference_title, "category": reference_category},
        "candidates": [{"asin": c["asin"], "title": c["title"]} for c in candidates],
        "instructions": (
            "Mark true competitors only (same product type). "
            "Reject accessories/replacement parts/bundles.\n"
            "Return STRICT JSON:\n"
            "{\n"
            '  "evaluations": [{"asin":"...","is_competitor":true,"confidence":0.0}],\n'
            '  "reasoning": "..." \n'
            "}\n"
            "No markdown. No extra keys."
        ),
    }

    resp = client.responses.create(model=model, input=json.dumps(payload))
    text = resp.output_text or ""
    obj = _parse_strict_json(text)

    evals = obj.get("evaluations")
    reasoning = obj.get("reasoning", "")
    if not isinstance(evals, list):
        raise RuntimeError(f"Invalid evaluations format from LLM. Raw: {text[:800]}")

    return {"evaluations": evals, "reasoning": reasoning, "raw_text": text, "prompt": payload, "model": model}
