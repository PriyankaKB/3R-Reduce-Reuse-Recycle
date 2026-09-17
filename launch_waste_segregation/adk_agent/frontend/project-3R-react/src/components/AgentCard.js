// components/AgentCard.js
import React, { useState } from "react";
import { callAgent } from "../api";

export default function AgentCard({ agent }) {
  const [response, setResponse] = useState(null);

  const handleClick = async () => {
    const result = await callAgent(agent, "run", { 
    state: {     
    batch_id: "1",
    image_gcs_uri: "launch_waste_segregation\\adk_agent\\static\\images\\paper.jpg",
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
