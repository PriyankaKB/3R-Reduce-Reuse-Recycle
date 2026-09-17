// components/AgentCard.js
import React, { useState, useEffect } from "react";
import { callAgent } from "../api";

export default function AgentCard({ agent, imageGcsUri, onSaveEnv }) {
  const [response, setResponse] = useState(null);
  const [imageGcsUri, setImageGcsUri] = useState("");
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




--------------
import React, { useState, useEffect } from 'react';

export const AgentCard = () => {
  const [imageGcsUri, setImageGcsUri] = useState("");
  const [response, setResponse] = useState(null);
  const [statusMessage, setStatusMessage] = useState("");

  // 1. Fetch current environment variable value on mount
  useEffect(() => {
    fetch("/api/config")
      .then((res) => res.json())
      .then((data) => {
        setImageGcsUri(data.image_gcs_uri);
      })
      .catch((err) => console.error("Error loading config:", err));
  }, []);

  // 2. Synchronize the UI state to the Server's OS environment variables
  const handleSaveToEnvironment = async () => {
    try {
      const res = await fetch("/api/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ image_gcs_uri: imageGcsUri.trim() }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed to update config");
      
      setStatusMessage("✓ Server-side environment variable updated!");
      setTimeout(() => setStatusMessage(""), 4000);
    } catch (err) {
      alert("Error saving environment variable: " + err.message);
    }
  };

  const handleClick = async () => {
    if (!imageGcsUri.startsWith("gs://")) {
      alert("Please enter a valid Google Cloud Storage URI starting with 'gs://'");
      return;
    }

    // Automatically synchronize/save to environment before executing
    await handleSaveToEnvironment();

    const result = await callAgent(agent, "run", { 
      state: {     
        batch_id: "1",
        image_gcs_uri: imageGcsUri.trim(), // Sent dynamically
        material_category: "PAPER",
        target_bin_id: "NONE",
        robot_execution_matrix: "PENDING",
        hmi_telemetry_payload: "",
        bigquery_commit_success: false, 
      } 
    });
    setResponse(result);
  };

  return (
    <div style={{ padding: "20px", border: "1px solid #ccc", borderRadius: "8px" }}>
      <h3>Waste Segregation Agent Dashboard</h3>
      
      <div style={{ marginBottom: "15px" }}>
        <label htmlFor="gcs-uri" style={{ display: "block", marginBottom: "5px", fontWeight: "bold" }}>
          Target Image GCS URI:
        </label>
        <div style={{ display: "flex", gap: "10px" }}>
          <input
            id="gcs-uri"
            type="text"
            value={imageGcsUri}
            onChange={(e) => setImageGcsUri(e.target.value)}
            style={{
              flex: 1,
              padding: "10px",
              borderRadius: "4px",
              border: "1px solid #aaa",
              fontSize: "14px"
            }}
          />
          <button 
            onClick={handleSaveToEnvironment}
            style={{
              padding: "10px 15px",
              backgroundColor: "#34a853",
              color: "white",
              border: "none",
              borderRadius: "4px",
              cursor: "pointer",
              fontWeight: "bold"
            }}
          >
            Save to Env
          </button>
        </div>
        {statusMessage && <small style={{ color: "#34a853", display: "block", marginTop: "5px" }}>{statusMessage}</small>}
      </div>

      <button 
        onClick={handleClick}
        style={{
          width: "100%",
          padding: "12px",
          backgroundColor: "#1a73e8",
          color: "white",
          border: "none",
          borderRadius: "4px",
          cursor: "pointer",
          fontWeight: "bold",
          fontSize: "16px"
        }}
      >
        Run Segregation Flow
      </button>

      {response && (
        <div style={{ marginTop: "15px" }}>
          <h4>Response:</h4>
          <pre>{JSON.stringify(response, null, 2)}</pre>
        </div>
      )}
    </div>
  );
};

