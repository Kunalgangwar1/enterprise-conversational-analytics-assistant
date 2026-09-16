import { useEffect, useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { getModeWelcome, selectMode } from "./api/chat";
import { ApiError } from "./api/client";
import { getToolFeatureFlags, getUiFeatureFlags } from "./api/features";
import type {
  ChatMode,
  ModeWelcome,
  SqlStrategy,
  ToolFeatureFlags,
  UiFeatureFlags,
} from "./api/types";
import { Composer } from "./components/chat/Composer";
import { Transcript } from "./components/chat/Transcript";
import { ModeSidebar } from "./components/layout/ModeSidebar";
import { useChat } from "./hooks/useChat";

const EMPTY_UI_FLAGS: UiFeatureFlags = {
  follow_up_questions_show: false,
  context_button: false,
  chat_latency_badge: false,
  knowledge_graph_tools_show: false,
};

const EMPTY_TOOL_FLAGS: ToolFeatureFlags = {
  sql: false,
  forecasting: false,
  group_access: false,
  data_discovery: false,
  knowledge_catalog: false,
  semantica: false,
  data_quality: false,
};

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "The application could not load.";
}

export function ChatPage() {
  const [selectedMode, setSelectedMode] = useState<ChatMode>("auto");
  const [sqlStrategy, setSqlStrategy] = useState<SqlStrategy>("auto");
  const [uiFlags, setUiFlags] = useState(EMPTY_UI_FLAGS);
  const [toolFlags, setToolFlags] = useState(EMPTY_TOOL_FLAGS);
  const [welcome, setWelcome] = useState<ModeWelcome | null>(null);
  const [startupError, setStartupError] = useState<string | null>(null);
  const { messages, isSending, send, runSql, reset } = useChat(selectedMode, sqlStrategy);

  const loadWelcome = async (mode: ChatMode) => {
    const result = await getModeWelcome(mode);
    setWelcome(result);
  };

  useEffect(() => {
    const controller = new AbortController();
    void Promise.all([
      getUiFeatureFlags(controller.signal),
      getToolFeatureFlags(controller.signal),
      getModeWelcome("auto", controller.signal),
    ])
      .then(([ui, tools, initialWelcome]) => {
        setUiFlags(ui);
        setToolFlags(tools);
        setWelcome(initialWelcome);
      })
      .catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === "AbortError")) {
          setStartupError(errorMessage(error));
        }
      });
    return () => controller.abort();
  }, []);

  const changeMode = async (mode: ChatMode) => {
    setStartupError(null);
    try {
      await selectMode(mode);
      setSelectedMode(mode);
      setSqlStrategy("auto");
      await loadWelcome(mode);
    } catch (error) {
      setStartupError(errorMessage(error));
    }
  };

  const resetConversation = async () => {
    if (await reset()) await loadWelcome(selectedMode);
  };

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="brand-mark" aria-hidden="true">EA</div>
        <div>
          <p className="eyebrow">Enterprise analytics</p>
          <h1>Conversational Assistant</h1>
        </div>
        <span className="environment-badge">Synthetic data workspace</span>
      </header>
      <div className="app-body">
        <ModeSidebar
          selectedMode={selectedMode}
          tools={toolFlags}
          onSelect={(mode) => void changeMode(mode)}
          onReset={() => void resetConversation()}
        />
        <main className="chat-workspace">
          <section className="workspace-header">
            <div>
              <p className="eyebrow">Current mode</p>
              <h2>{welcome?.display_name ?? "Loading workspace…"}</h2>
              <p>{welcome?.description}</p>
            </div>
            {selectedMode === "sql" && (
              <label className="strategy-select">
                <span>Analysis strategy</span>
                <select
                  aria-label="Analysis strategy"
                  value={sqlStrategy}
                  onChange={(event) => setSqlStrategy(event.target.value as SqlStrategy)}
                >
                  <option value="auto">Auto</option>
                  <option value="standard">Standard</option>
                  <option value="advanced">Advanced</option>
                  <option value="forecasting" disabled={!toolFlags.forecasting}>Forecasting</option>
                </select>
              </label>
            )}
          </section>
          {startupError && <div className="startup-error" role="alert">{startupError}</div>}
          <section className="conversation-panel">
            {messages.length === 0 && welcome && (
              <div className="welcome-card">
                <p className="eyebrow">Welcome</p>
                <h3>{welcome.display_name}</h3>
                <p>{welcome.welcome_message}</p>
              </div>
            )}
            <Transcript
              messages={messages}
              flags={uiFlags}
              onRunSql={(id) => void runSql(id)}
              onFollowUp={(question) => void send(question)}
            />
          </section>
          <Composer
            disabled={isSending}
            contextEnabled={uiFlags.context_button}
            onSend={send}
          />
        </main>
      </div>
    </div>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<ChatPage />} />
      <Route path="*" element={<Navigate replace to="/" />} />
    </Routes>
  );
}
