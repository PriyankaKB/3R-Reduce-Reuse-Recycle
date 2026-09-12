// components/AgentCard.js
import React, { useState } from "react";
import { callAgent } from "../api";

export default function AgentCard({ agent }) {
  const [response, setResponse] = useState(null);

  const handleClick = async () => {
    const result = await callAgent(agent, "run", { state: "Test request" });
    setResponse(result);
  };

  return (
    <div style={{ border: "1px solid #ccc", padding: "1rem", margin: "1rem" }}>
      <h3>{agent}</h3>
      <button onClick={handleClick}>Call {agent}</button>
      {response && <pre>{JSON.stringify(response, null, 2)}</pre>}
    </div>
  );
}
