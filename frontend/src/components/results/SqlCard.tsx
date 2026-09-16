import type { SqlExecutionResult, SqlPayload } from "../../api/types";
import { SqlResultCard } from "./SqlResultCard";

interface SqlCardProps {
  payload: SqlPayload;
  result?: SqlExecutionResult;
  executing: boolean;
  onRun: () => void;
}

export function SqlCard({ payload, result, executing, onRun }: SqlCardProps) {
  return (
    <section className="result-card" aria-label="Generated SQL">
      <div className="card-heading">
        <h3>Generated SQL</h3>
        <span className="status-badge">Validated</span>
      </div>
      <pre><code>{payload.sql}</code></pre>
      <p className="metadata-line">
        Domains: {payload.selected_domains.join(", ") || "—"} · Tables:{" "}
        {payload.selected_tables.join(", ") || "—"}
      </p>
      <button className="primary-button" type="button" onClick={onRun} disabled={executing}>
        {executing ? "Running…" : "Run query"}
      </button>
      {result && <SqlResultCard result={result} />}
    </section>
  );
}
