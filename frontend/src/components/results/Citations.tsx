import type { ChatCitation } from "../../api/types";
import { safeSourcePath } from "../../utils/format";

export function Citations({ citations }: { citations: ChatCitation[] }) {
  if (citations.length === 0) return null;
  return (
    <section className="citations" aria-label="Citations">
      <h3>Sources</h3>
      <ol>
        {citations.map((citation) => (
          <li key={citation.id}>
            <strong>{citation.title}</strong>
            {citation.section && <span> · {citation.section}</span>}
            <small>{safeSourcePath(citation.source_path)}</small>
          </li>
        ))}
      </ol>
    </section>
  );
}
