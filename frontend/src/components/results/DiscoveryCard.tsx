import type { DiscoveryPayload } from "../../api/types";

export function DiscoveryCard({ payload }: { payload: DiscoveryPayload }) {
  if (payload.matches.length === 0) return <p>No registered datasets matched this request.</p>;
  return (
    <section className="discovery-grid" aria-label="Dataset matches">
      {payload.matches.map((match) => (
        <article className="discovery-card" key={`${match.repository}:${match.dataset}`}>
          <h3>{match.dataset}</h3>
          <p>{match.description}</p>
          <dl>
            <div><dt>Repository</dt><dd>{match.repository}</dd></div>
            <div><dt>Domain</dt><dd>{match.domain}</dd></div>
            <div><dt>Table</dt><dd>{match.table}</dd></div>
            <div><dt>Matched</dt><dd>{match.matched_fields.join(", ")}</dd></div>
          </dl>
        </article>
      ))}
    </section>
  );
}
