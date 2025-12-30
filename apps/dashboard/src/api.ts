import axios from "axios";

export const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000";

export type ExecutionListItem = {
  execution_id: string;
  name: string;
  app: string;
  created_at_ms: number;
  metadata: Record<string, any>;
};

export type Step = {
  step_id: string;
  name: string;
  status: "SUCCESS" | "ERROR";
  duration_ms: number;
  input: Record<string, any>;
  output: Record<string, any>;
  reasoning: string;
  artifacts: Record<string, any>;
  error?: Record<string, any> | null;
};

export async function fetchExecutions(): Promise<ExecutionListItem[]> {
  const res = await axios.get(`${API_BASE}/executions`);
  return res.data;
}

export async function fetchExecution(executionId: string): Promise<{ execution: any; steps: Step[] }> {
  const res = await axios.get(`${API_BASE}/executions/${executionId}`);
  return res.data;
}

export async function searchExecutions(q: string): Promise<ExecutionListItem[]> {
  const res = await axios.get(`${API_BASE}/search`, { params: { q } });
  return res.data;
}
export async function fetchDiff(a: string, b: string) {
  const res = await axios.get(`${API_BASE}/executions/${a}/diff/${b}`);
  return res.data;
}
export async function runDemo(): Promise<{ ok: boolean; execution_id: string }> {
  const res = await axios.post(`${API_BASE}/demo/run`);
  return res.data;
}
