// apps/dashboard/src/App.tsx
import { useEffect, useMemo, useState } from "react";
import { fetchExecution, fetchExecutions, searchExecutions, runDemo, fetchDiff } from "./api";
import type { ExecutionListItem, Step } from "./api";
import "./index.css";

const topControlStyle: React.CSSProperties = {
  padding: "10px 12px",
  borderRadius: 10,
  border: "1px solid #2b2b2b",
  background: "#1a1a1a",
  color: "#f2f2f2",
  fontWeight: 600,
  cursor: "pointer",
};

const topSelectStyle: React.CSSProperties = {
  padding: "10px 12px",
  borderRadius: 10,
  border: "1px solid #2b2b2b",
  background: "#1a1a1a",
  color: "#f2f2f2",
  fontWeight: 600,
};

function downloadJson(filename: string, data: any) {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function fmtTime(ms: number) {
  const d = new Date(ms);
  return d.toLocaleString();
}

function JsonBox({ value }: { value: any }) {
  return (
    <pre
      style={{
        background: "#0b0b0b",
        color: "#eaeaea",
        padding: 12,
        borderRadius: 8,
        overflow: "auto",
        maxHeight: 280,
        border: "1px solid #2b2b2b",
      }}
    >
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}

function EvaluationsTable({ evaluations }: { evaluations: any[] }) {
  return (
    <div style={{ overflow: "auto", border: "1px solid #2b2b2b", borderRadius: 8 }}>
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead style={{ position: "sticky", top: 0, background: "#111" }}>
          <tr>
            <th style={{ textAlign: "left", padding: 10, color: "#f2f2f2" }}>ASIN</th>
            <th style={{ textAlign: "left", padding: 10, color: "#f2f2f2" }}>Title</th>
            <th style={{ textAlign: "right", padding: 10, color: "#f2f2f2" }}>Price</th>
            <th style={{ textAlign: "right", padding: 10, color: "#f2f2f2" }}>Rating</th>
            <th style={{ textAlign: "right", padding: 10, color: "#f2f2f2" }}>Reviews</th>
            <th style={{ textAlign: "center", padding: 10, color: "#f2f2f2" }}>Qualified</th>
          </tr>
        </thead>
        <tbody>
          {evaluations.map((e) => (
            <tr key={e.asin} style={{ borderTop: "1px solid #2b2b2b" }}>
              <td style={{ padding: 10, fontFamily: "monospace" }}>{e.asin}</td>
              <td style={{ padding: 10 }}>
                <div style={{ fontWeight: 600 }}>{e.title}</div>
                <div style={{ fontSize: 12, opacity: 0.85 }}>
                  {Object.entries(e.filter_results || {}).map(([k, v]: any) => (
                    <div key={k}>
                      <b>{k}</b>: {v.passed ? "✅" : "❌"} — {v.detail}
                    </div>
                  ))}
                  {"llm_is_competitor" in e && (
                    <div style={{ marginTop: 6 }}>
                      <b>LLM</b>: {e.llm_is_competitor ? "✅ competitor" : "❌ not competitor"}
                      {typeof e.llm_confidence === "number" ? ` • conf: ${e.llm_confidence}` : ""}
                    </div>
                  )}
                </div>
              </td>
              <td style={{ padding: 10, textAlign: "right" }}>{e.metrics?.price}</td>
              <td style={{ padding: 10, textAlign: "right" }}>{e.metrics?.rating}</td>
              <td style={{ padding: 10, textAlign: "right" }}>{e.metrics?.reviews}</td>
              <td style={{ padding: 10, textAlign: "center" }}>{e.qualified ? "✅" : "❌"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Human-friendly summaries for steps (default view). */
function StepSummary({ step }: { step: any }) {
  const name = step?.name;

  const cardStyle: React.CSSProperties = {
    padding: 12,
    borderRadius: 10,
    background: "#121212",
    border: "1px solid #2a2a2a",
    marginBottom: 12,
  };

  // keyword_generation
  if (name === "keyword_generation") {
    const kws: string[] = step?.output?.keywords ?? [];
    return (
      <div style={cardStyle}>
        <b>Summary</b>
        <div style={{ marginTop: 8, opacity: 0.9 }}>
          Generated <b>{kws.length}</b> search keywords using model{" "}
          <span style={{ fontFamily: "monospace" }}>{step?.output?.model ?? "unknown"}</span>.
        </div>
        {kws.length > 0 && (
          <div style={{ marginTop: 10 }}>
            <div style={{ fontSize: 12, opacity: 0.7, marginBottom: 6 }}>Top keywords</div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
              {kws.slice(0, 10).map((k: string) => (
                <span
                  key={k}
                  style={{
                    padding: "6px 10px",
                    borderRadius: 999,
                    border: "1px solid #2a2a2a",
                    background: "#0b0b0b",
                    fontFamily: "monospace",
                    fontSize: 12,
                  }}
                >
                  {k}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>
    );
  }

  // candidate_search
  if (name === "candidate_search") {
    const total = step?.output?.total_results;
    const fetched = step?.output?.candidates_fetched ?? step?.artifacts?.candidates?.length ?? 0;
    return (
      <div style={cardStyle}>
        <b>Summary</b>
        <div style={{ marginTop: 8, opacity: 0.9 }}>
          Search returned <b>{total ?? "?"}</b> total matches. Fetched <b>{fetched}</b> candidates for evaluation.
        </div>
      </div>
    );
  }

  // apply_filters
  if (name === "apply_filters") {
    const out = step?.output ?? {};
    const passed = out?.passed ?? out?.passed_count ?? out?.qualified ?? "?";
    const evaluated = step?.input?.candidates_count ?? step?.artifacts?.evaluations?.length ?? "?";
    const f = step?.artifacts?.filters_applied;
    return (
      <div style={cardStyle}>
        <b>Summary</b>
        <div style={{ marginTop: 8, opacity: 0.9 }}>
          Evaluated <b>{evaluated}</b> candidates and <b>{passed}</b> passed the business filters.
        </div>
        {f && (
          <div style={{ marginTop: 10, fontSize: 13, opacity: 0.85 }}>
            <div>
              <b>Filters:</b>
            </div>
            {Object.entries(f).map(([k, v]: any) => (
              <div key={k} style={{ marginTop: 4 }}>
                <span style={{ fontFamily: "monospace" }}>{k}</span>:{" "}
                <span style={{ opacity: 0.9 }}>{v?.rule ?? JSON.stringify(v)}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    );
  }

  // llm_relevance_evaluation
  if (name === "llm_relevance_evaluation") {
    const out = step?.output ?? {};
    const total = step?.input?.candidates_count ?? step?.artifacts?.evaluations?.length ?? "?";
    const confirmed = out?.confirmed_competitors ?? out?.confirmed ?? "?";
    return (
      <div style={cardStyle}>
        <b>Summary</b>
        <div style={{ marginTop: 8, opacity: 0.9 }}>
          LLM checked <b>{total}</b> candidates → confirmed <b>{confirmed}</b> competitors.
        </div>
      </div>
    );
  }

  // final_decision / final_decision_summary
  if (name === "final_decision" || name === "final_decision_summary") {
    const out = step?.output ?? {};
    const selectedAsin = out?.selected_asin ?? out?.selected_competitor?.asin;
    const selectedTitle = out?.selected_title ?? out?.selected_competitor?.title;
    const conf = out?.confidence;
    const afterLLM = step?.input?.after_llm ?? step?.input?.qualified_candidates;
    return (
      <div style={cardStyle}>
        <b>Summary</b>
        <div style={{ marginTop: 8, opacity: 0.9 }}>
          Final decision selected{" "}
          <span style={{ fontFamily: "monospace" }}>{selectedAsin ?? "N/A"}</span> —{" "}
          <b>{selectedTitle ?? "Unknown title"}</b>.
          {typeof conf === "number" ? ` (confidence: ${conf})` : ""}
        </div>
        {afterLLM !== undefined && (
          <div style={{ marginTop: 6, fontSize: 13, opacity: 0.85 }}>
            Confirmed competitors after LLM: <b>{afterLLM}</b>
          </div>
        )}
      </div>
    );
  }

  // demo_failed
  if (name === "demo_failed") {
    const err = step?.error ?? step?.output?.error ?? {};
    return (
      <div style={{ ...cardStyle, border: "1px solid #5a2a2a", background: "#1a0f0f" }}>
        <b>Summary</b>
        <div style={{ marginTop: 8, opacity: 0.9 }}>
          Demo run failed:{" "}
          <span style={{ fontFamily: "monospace" }}>
            {err?.type ?? "Error"}{err?.message ? ` — ${err.message}` : ""}
          </span>
        </div>
      </div>
    );
  }

  // default
  return (
    <div style={cardStyle}>
      <b>Summary</b>
      <div style={{ marginTop: 8, opacity: 0.9 }}>Step completed. See reasoning and JSON for details.</div>
    </div>
  );
}

type Tab = "executions" | "steps" | "detail";

export default function App() {
  const [executions, setExecutions] = useState<ExecutionListItem[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [steps, setSteps] = useState<Step[]>([]);
  const [selectedStepId, setSelectedStepId] = useState<string | null>(null);

  const [q, setQ] = useState("");

  const [compareId, setCompareId] = useState<string | null>(null);
  const [diffData, setDiffData] = useState<any>(null);

  const [running, setRunning] = useState(false);

  const [tab, setTab] = useState<Tab>("detail");

  // JSON toggle (NEW)
  const [showJson, setShowJson] = useState(false);

  async function refreshExecutions() {
    const xs = await fetchExecutions();
    setExecutions(xs);
    if (!selectedId && xs.length) setSelectedId(xs[0].execution_id);
  }

  async function runSearch(text: string) {
    setQ(text);

    if (!text.trim()) {
      await refreshExecutions();
      return;
    }

    const xs = await searchExecutions(text);
    setExecutions(xs);
    if (xs.length) setSelectedId(xs[0].execution_id);
  }

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const ex = params.get("execution");
    if (ex) setSelectedId(ex);
  }, []);

  useEffect(() => {
    refreshExecutions();
    const t = setInterval(refreshExecutions, 8000);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!selectedId) return;
    fetchExecution(selectedId).then((data) => {
      setSteps(data.steps || []);
      setSelectedStepId(data.steps?.[0]?.step_id ?? null);
      setShowJson(false); // reset on execution switch
    });
  }, [selectedId]);

  useEffect(() => {
    if (!selectedId || !compareId) {
      setDiffData(null);
      return;
    }
    if (compareId === selectedId) {
      setDiffData(null);
      return;
    }
    fetchDiff(selectedId, compareId)
      .then((d) => setDiffData(d))
      .catch(() => setDiffData({ error: "diff_failed" }));
  }, [selectedId, compareId]);

  const selectedStep = useMemo(
    () => steps.find((s) => s.step_id === selectedStepId) ?? null,
    [steps, selectedStepId]
  );

  // Reset JSON toggle when changing steps (so default is clean)
  useEffect(() => {
    setShowJson(false);
  }, [selectedStepId]);

  const TopBar = (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
      <h2 style={{ marginTop: 0, marginBottom: 0 }}>Decision Trail</h2>

      <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
        <select value={compareId ?? ""} onChange={(e) => setCompareId(e.target.value || null)} style={topSelectStyle}>
          <option value="">Compare with…</option>
          {executions
            .filter((x) => x.execution_id !== selectedId)
            .map((x) => (
              <option key={x.execution_id} value={x.execution_id}>
                {x.name} ({x.execution_id.slice(0, 6)}…)
              </option>
            ))}
        </select>

        <button
          onClick={async () => {
            try {
              setRunning(true);
              const r = await runDemo();
              const xs = await fetchExecutions();
              setExecutions(xs);
              setSelectedId(r.execution_id);
              setTab("detail");
            } finally {
              setRunning(false);
            }
          }}
          disabled={running}
          style={{
            ...topControlStyle,
            cursor: running ? "not-allowed" : "pointer",
            opacity: running ? 0.75 : 1,
          }}
        >
          {running ? "Running…" : "Run Demo (LLM)"}
        </button>

        <button
          onClick={() => {
            if (!selectedId) return;
            downloadJson(`execution-${selectedId}.json`, { execution_id: selectedId, steps });
          }}
          disabled={!selectedId}
          style={{
            ...topControlStyle,
            cursor: selectedId ? "pointer" : "not-allowed",
            opacity: selectedId ? 1 : 0.5,
          }}
        >
          Export JSON
        </button>

        <button
          disabled={!selectedId}
          onClick={async () => {
            if (!selectedId) return;
            const url = `${window.location.origin}/?execution=${selectedId}`;
            await navigator.clipboard.writeText(url);
            alert("Copied share link!");
          }}
          style={{
            ...topControlStyle,
            background: "#2a2a2a",
            cursor: selectedId ? "pointer" : "not-allowed",
            opacity: selectedId ? 1 : 0.5,
          }}
        >
          Copy Share Link
        </button>
      </div>
    </div>
  );

  const TabsBar = (
    <div style={{ display: "flex", gap: 8, marginTop: 12, marginBottom: 12, flexWrap: "wrap" }}>
      {(["executions", "steps", "detail"] as Tab[]).map((t) => (
        <button
          key={t}
          onClick={() => setTab(t)}
          style={{
            padding: "8px 12px",
            borderRadius: 10,
            border: "1px solid #2b2b2b",
            background: tab === t ? "#2a2a2a" : "#1a1a1a",
            color: "#f2f2f2",
            fontWeight: 700,
            textTransform: "capitalize",
            cursor: "pointer",
          }}
        >
          {t}
        </button>
      ))}
    </div>
  );

  const ExecutionsPanel = (
    <div style={{ border: "1px solid #2b2b2b", borderRadius: 12, padding: 12 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10 }}>
        <h3 style={{ marginTop: 0, marginBottom: 0 }}>Executions</h3>
        <button onClick={refreshExecutions} style={{ ...topControlStyle, padding: "6px 10px" }}>
          Refresh
        </button>
      </div>

      <input
        value={q}
        onChange={(e) => runSearch(e.target.value)}
        placeholder="Search executions, steps, candidates…"
        style={{
          width: "100%",
          padding: 10,
          borderRadius: 10,
          border: "1px solid #2b2b2b",
          marginTop: 12,
          marginBottom: 12,
          background: "#111",
          color: "#f2f2f2",
        }}
      />

      {executions.length === 0 && (
        <div style={{ opacity: 0.85, fontSize: 14 }}>
          No executions yet. Run the demo:
          <div style={{ fontFamily: "monospace", marginTop: 8 }}>python apps/demo/run_demo.py</div>
        </div>
      )}

      {executions.map((e) => (
        <div
          key={e.execution_id}
          onClick={() => {
            setSelectedId(e.execution_id);
            setTab("detail");
          }}
          style={{
            padding: 12,
            borderRadius: 10,
            border: e.execution_id === selectedId ? "2px solid #f2f2f2" : "1px solid #2b2b2b",
            marginBottom: 10,
            cursor: "pointer",
            background: e.execution_id === selectedId ? "#141414" : "transparent",
          }}
        >
          <div style={{ fontWeight: 700 }}>{e.name}</div>
          <div style={{ fontSize: 12, opacity: 0.85 }}>{fmtTime(e.created_at_ms)}</div>
          <div style={{ fontSize: 12, opacity: 0.85 }}>{e.execution_id.slice(0, 8)}…</div>
        </div>
      ))}
    </div>
  );

  const StepsPanel = (
    <div style={{ border: "1px solid #2b2b2b", borderRadius: 12, padding: 12 }}>
      <h3 style={{ marginTop: 0 }}>Steps</h3>
      {steps.map((s) => (
        <div
          key={s.step_id}
          onClick={() => {
            setSelectedStepId(s.step_id);
            setTab("detail");
          }}
          style={{
            padding: 10,
            borderRadius: 10,
            border: s.step_id === selectedStepId ? "2px solid #f2f2f2" : "1px solid #2b2b2b",
            marginBottom: 10,
            cursor: "pointer",
            background: s.step_id === selectedStepId ? "#141414" : "transparent",
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
            <b>{s.name}</b>
            <span>{s.status === "SUCCESS" ? "✅" : "❌"}</span>
          </div>
          <div style={{ fontSize: 12, opacity: 0.85 }}>{s.duration_ms} ms</div>
        </div>
      ))}
    </div>
  );

  const DetailPanel = (
    <div style={{ border: "1px solid #2b2b2b", borderRadius: 12, padding: 12 }}>
      {!selectedStep ? (
        <div>Select a step</div>
      ) : (
        <>
          <h3 style={{ marginTop: 0 }}>{selectedStep.name}</h3>

          {/*  Status line + Show/Hide JSON toggle */}
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12 }}>
            <div style={{ marginBottom: 8 }}>
              <b>Status:</b> {selectedStep.status} • <b>Duration:</b> {selectedStep.duration_ms} ms
            </div>

            <button
              onClick={() => setShowJson((v) => !v)}
              style={{
                padding: "8px 10px",
                borderRadius: 10,
                border: "1px solid #2b2b2b",
                background: "#1a1a1a",
                color: "#f2f2f2",
                fontWeight: 700,
                cursor: "pointer",
              }}
            >
              {showJson ? "Hide JSON" : "Show JSON"}
            </button>
          </div>

          {/*  Human summary always visible */}
          <StepSummary step={selectedStep} />

          {selectedStep.reasoning && (
            <div
              style={{
                marginBottom: 12,
                padding: 12,
                borderRadius: 10,
                background: "#151515",
                border: "1px solid #2b2b2b",
              }}
            >
              <b>Reasoning</b>
              <div style={{ opacity: 0.9 }}>{selectedStep.reasoning}</div>
            </div>
          )}

          {Array.isArray(selectedStep.artifacts?.evaluations) && (
            <>
              <h4>Candidate Evaluations</h4>
              <EvaluationsTable evaluations={selectedStep.artifacts.evaluations} />
            </>
          )}

          {/* JSON only when toggled on */}
          {showJson && (
            <>
              <h4 style={{ marginTop: 16 }}>Input (JSON)</h4>
              <JsonBox value={selectedStep.input} />

              <h4>Output (JSON)</h4>
              <JsonBox value={selectedStep.output} />

              <h4>Artifacts (JSON)</h4>
              <JsonBox value={selectedStep.artifacts} />

              {selectedStep.error && (
                <>
                  <h4>Error (JSON)</h4>
                  <JsonBox value={selectedStep.error} />
                </>
              )}
            </>
          )}
        </>
      )}
    </div>
  );

  return (
    <div style={{ height: "100vh", padding: 16, overflow: "hidden" }}>
      <div style={{ height: "100%", overflow: "auto" }}>
        {TopBar}
        {TabsBar}

        {/* Diff panel (shows in all tabs) */}
        {diffData && (
          <>
            <h3 style={{ marginTop: 16 }}>Diff</h3>
            <JsonBox value={diffData} />
          </>
        )}

        {tab === "executions" && <div style={{ marginTop: 12 }}>{ExecutionsPanel}</div>}
        {tab === "steps" && <div style={{ marginTop: 12 }}>{StepsPanel}</div>}
        {tab === "detail" && (
          <div style={{ marginTop: 12, display: "grid", gridTemplateColumns: "360px 1fr", gap: 16 }}>
            {StepsPanel}
            {DetailPanel}
          </div>
        )}
      </div>
    </div>
  );
}
