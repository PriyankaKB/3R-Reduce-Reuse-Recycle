// api.js

const ORCHESTRATOR_URL = process.env.ORCHESTRATOR_URL || window._env_?.ORCHESTRATOR_URL || "http://localhost:8084";

export async function callAgent(agent, endpoint, payload = {}) {
  const res = await fetch(`${ORCHESTRATOR_URL}/${agent}/${endpoint}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return res.json();
}
