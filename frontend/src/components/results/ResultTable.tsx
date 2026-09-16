import type { ResultCell } from "../../api/types";
import { formatCell } from "../../utils/format";

interface ResultTableProps {
  columns: string[];
  rows: Array<Record<string, ResultCell>>;
  caption?: string;
}

export function ResultTable({ columns, rows, caption = "Query results" }: ResultTableProps) {
  return (
    <div className="table-scroll">
      <table>
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr>{columns.map((column) => <th key={column}>{column}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={index}>
              {columns.map((column) => <td key={column}>{formatCell(row[column] ?? null)}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
