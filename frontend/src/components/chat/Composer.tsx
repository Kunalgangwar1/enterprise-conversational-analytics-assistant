import { type KeyboardEvent, useState } from "react";

interface ComposerProps {
  disabled: boolean;
  contextEnabled: boolean;
  onSend: (message: string, context?: string) => Promise<boolean>;
}

export function Composer({ disabled, contextEnabled, onSend }: ComposerProps) {
  const [message, setMessage] = useState("");
  const [context, setContext] = useState("");
  const [showContext, setShowContext] = useState(false);

  const submit = async () => {
    if (!message.trim() || disabled) return;
    const succeeded = await onSend(message, context);
    if (succeeded) {
      setMessage("");
      setContext("");
      setShowContext(false);
    }
  };

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void submit();
    }
  };

  return (
    <section className="composer" aria-label="Message composer">
      {contextEnabled && (
        <div className="context-area">
          <button
            className="text-button"
            type="button"
            aria-expanded={showContext}
            onClick={() => setShowContext((visible) => !visible)}
          >
            {showContext ? "Remove context" : "Add context"}
          </button>
          {showContext && (
            <label>
              <span>Context for this turn only</span>
              <textarea
                aria-label="Context for this turn only"
                maxLength={8000}
                rows={3}
                value={context}
                onChange={(event) => setContext(event.target.value)}
              />
            </label>
          )}
        </div>
      )}
      <div className="composer-row">
        <label className="sr-only" htmlFor="chat-message">
          Message
        </label>
        <textarea
          id="chat-message"
          placeholder="Ask about governed enterprise data…"
          rows={2}
          maxLength={4000}
          value={message}
          disabled={disabled}
          onChange={(event) => setMessage(event.target.value)}
          onKeyDown={onKeyDown}
        />
        <button
          className="primary-button"
          type="button"
          onClick={() => void submit()}
          disabled={disabled || !message.trim()}
        >
          {disabled ? "Working…" : "Send"}
        </button>
      </div>
      <p className="composer-hint">Enter to send · Shift+Enter for a new line</p>
    </section>
  );
}
