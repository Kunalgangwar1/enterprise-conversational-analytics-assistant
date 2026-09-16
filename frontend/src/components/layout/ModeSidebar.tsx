import type { ChatMode, Permission, ToolFeatureFlags } from "../../api/types";

const MODES: ReadonlyArray<{
  key: ChatMode;
  label: string;
  flag?: keyof ToolFeatureFlags;
  permission?: Permission;
}> = [
  { key: "auto", label: "Auto" },
  { key: "sql", label: "Data Intelligence", flag: "sql", permission: "sql.generate" },
  { key: "group_access", label: "Group Access", flag: "group_access", permission: "group_access.read_self" },
  { key: "data_discovery", label: "Data Discovery", flag: "data_discovery", permission: "data_discovery.read" },
  { key: "knowledge_catalog", label: "Knowledge Catalog", flag: "knowledge_catalog", permission: "knowledge_catalog.read" },
  { key: "semantica", label: "Semantica", flag: "semantica", permission: "semantica.read" },
  { key: "data_quality", label: "Data Quality", flag: "data_quality", permission: "data_quality.read" },
];

interface ModeSidebarProps {
  selectedMode: ChatMode;
  tools: ToolFeatureFlags;
  permissions: ReadonlySet<Permission>;
  onSelect: (mode: ChatMode) => void;
  onReset: () => void;
}

export function ModeSidebar({ selectedMode, tools, permissions, onSelect, onReset }: ModeSidebarProps) {
  return (
    <aside className="mode-sidebar" aria-label="Assistant modes">
      <nav>
        <p className="sidebar-label">Modes</p>
        {MODES.map((mode) => {
          const enabled = mode.flag === undefined || tools[mode.flag];
          const authorized = mode.permission === undefined || permissions.has(mode.permission);
          if (!authorized) return null;
          return (
            <button
              className={`mode-button ${selectedMode === mode.key ? "mode-button--active" : ""}`}
              disabled={!enabled}
              key={mode.key}
              onClick={() => onSelect(mode.key)}
              type="button"
              aria-pressed={selectedMode === mode.key}
              title={enabled ? mode.label : `${mode.label} is not enabled`}
            >
              <span aria-hidden="true" className="mode-mark" />
              {mode.label}
            </button>
          );
        })}
      </nav>
      <button className="secondary-button new-chat" onClick={onReset} type="button">
        New chat
      </button>
    </aside>
  );
}
