// api.js


const REACT_APP_ORCHESTRATOR_URL = process.env.REACT_APP_ORCHESTRATOR_URL || window._env_?.REACT_APP_ORCHESTRATOR_URL || "http://localhost:8084";

export async function callAgent(agent, endpoint, payload = {}) {
  const res = await fetch(`${REACT_APP_ORCHESTRATOR_URL}/${agent}/${endpoint}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return res.json();
}
