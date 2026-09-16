import type { SqlExecutionResult } from "../../api/types";
import { ChartView } from "./ChartView";
import { ResultTable } from "./ResultTable";

export function SqlResultCard({ result }: { result: SqlExecutionResult }) {
  return (
    <section className="nested-result" aria-label="SQL result">
      <h4>Query result</h4>
      <p>{result.summary}</p>
      <div className="result-meta">
        <span>{result.row_count} rows</span>
        <span>{result.execution_elapsed_ms.toFixed(1)} ms</span>
        {result.truncated && <strong className="warning">Results are truncated</strong>}
      </div>
      <ChartView chart={result.chart} rows={result.rows} />
      <ResultTable columns={result.columns} rows={result.rows} />
    </section>
  );
}
