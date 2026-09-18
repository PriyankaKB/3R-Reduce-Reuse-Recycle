// components/AgentCard.js
import React, { useState, useEffect } from "react";
import { callAgent } from "../api";

export default function AgentCard({ agent, imageGcsUri, onSaveEnv }) {
  const [response, setResponse] = useState(null);
  const [statusMessage, setStatusMessage] = useState("");

  const handleClick = async () => {
    const result = await callAgent(agent, "run", { 
    state: {     
    batch_id: "1",
    image_gcs_uri: imageGcsUri.trim(),
    material_category: "PAPER",
    target_bin_id: "NONE",
    robot_execution_matrix: "PENDING",
    hmi_telemetry_payload: "",
    bigquery_commit_success: false, } 
  });
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

