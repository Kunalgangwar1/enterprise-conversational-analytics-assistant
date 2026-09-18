import { lazy, Suspense, useEffect, useRef } from "react";

import type { UiFeatureFlags } from "../../api/types";
import type { TranscriptItem } from "../../state/chat";
import { Citations } from "../results/Citations";
import { DiscoveryCard } from "../results/DiscoveryCard";
import { ResultTable } from "../results/ResultTable";
import { SqlCard } from "../results/SqlCard";

const ForecastCard = lazy(() => import("../results/ForecastCard"));

interface TranscriptProps {
  messages: TranscriptItem[];
  flags: UiFeatureFlags;
  onRunSql: (messageId: string) => void;
  onFollowUp: (question: string) => void;
}

export function Transcript({ messages, flags, onRunSql, onFollowUp }: TranscriptProps) {
  const endRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "nearest" });
  }, [messages]);
  return (
    <div className="transcript" aria-live="polite" aria-label="Conversation">
      {messages.map((item) => {
        if (item.kind === "user") {
          return <article className="message message--user" key={item.id}>{item.content}</article>;
        }
        if (item.kind === "pending") {
          return <article className="message message--pending" key={item.id}>Analyzing request…</article>;
        }
        if (item.kind === "error") {
          return <article className="message message--error" role="alert" key={item.id}>{item.content}</article>;
        }
        const { response } = item;
        return (
          <article className="message message--assistant" key={item.id}>
            <div className="assistant-heading">
              <span>Enterprise assistant</span>
              {flags.chat_latency_badge && <small>{response.latency_ms.toFixed(0)} ms</small>}
            </div>
            <p>{response.content}</p>
            {response.response_type === "sql" && (
              <SqlCard
                payload={response.payload}
                result={item.sqlResult}
                executing={Boolean(item.executingSql)}
                onRun={() => onRunSql(item.id)}
              />
            )}
            {response.response_type === "forecast" && (
              <Suspense fallback={<p role="status">Loading forecast visualization…</p>}>
                <ForecastCard forecast={response.payload} />
              </Suspense>
            )}
            {response.response_type === "data_discovery" && (
              <DiscoveryCard payload={response.payload} />
            )}
            {(response.response_type === "knowledge_catalog" ||
              response.response_type === "data_quality" ||
              response.response_type === "semantica") && (
              <Citations citations={response.payload.citations} />
            )}
            {response.response_type === "advanced" && response.payload.table.columns.length > 0 && (
              <ResultTable
                caption="Advanced analytical result"
                columns={response.payload.table.columns}
                rows={response.payload.table.rows.map((row) =>
                  Object.fromEntries(response.payload.table.columns.map((column, index) => [column, row[index]])),
                )}
              />
            )}
            {flags.follow_up_questions_show && response.follow_up_questions.length > 0 && (
              <div className="follow-ups" aria-label="Follow-up questions">
                {response.follow_up_questions.map((question) => (
                  <button type="button" key={question} onClick={() => onFollowUp(question)}>
                    {question}
                  </button>
                ))}
              </div>
            )}
          </article>
        );
      })}
      <div ref={endRef} />
    </div>
  );
}
