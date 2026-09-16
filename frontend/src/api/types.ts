export type ChatMode =
  | "auto"
  | "sql"
  | "group_access"
  | "data_discovery"
  | "knowledge_catalog"
  | "semantica"
  | "data_quality";

export type SqlStrategy = "auto" | "standard" | "advanced" | "forecasting";

export interface UiFeatureFlags {
  follow_up_questions_show: boolean;
  context_button: boolean;
  chat_latency_badge: boolean;
  knowledge_graph_tools_show: boolean;
}

export interface ToolFeatureFlags {
  sql: boolean;
  forecasting: boolean;
  group_access: boolean;
  data_discovery: boolean;
  knowledge_catalog: boolean;
  semantica: boolean;
  data_quality: boolean;
}

export interface ModeWelcome {
  mode: ChatMode;
  display_name: string;
  description: string;
  welcome_message: string;
}

export interface ChatCitation {
  id: string;
  title: string;
  section: string | null;
  source_path: string;
}

export interface DatasetMatch {
  dataset: string;
  repository: string;
  table: string;
  domain: string;
  description: string;
  matched_fields: string[];
  score: number;
}

export interface SqlPayload {
  sql: string;
  status: "ready_to_execute";
  selected_domains: string[];
  selected_tables: string[];
}

export interface RagPayload {
  retrieval_method: string | null;
  citations: ChatCitation[];
}

export interface DiscoveryPayload {
  matches: DatasetMatch[];
}

export interface TablePayload {
  columns: string[];
  rows: Array<Array<string | number | boolean | null>>;
}

export interface DeltaPayload {
  label: string;
  value: number;
  unit: string;
  direction: "up" | "down" | "neutral" | null;
}

export interface AdvancedPayload {
  table: TablePayload;
  deltas: DeltaPayload[];
}

export interface ForecastMetric {
  mae: number;
  rmse: number;
  smape: number;
}

export interface HistoricalPoint {
  period: string;
  value: number;
}

export interface ForecastPoint {
  period: string;
  predicted: number;
  lower_bound: number;
  upper_bound: number;
}

export interface ForecastPayload {
  metric_label: string;
  frequency: "day" | "week" | "month";
  horizon_periods: number;
  selected_model: string;
  backtest_metrics: ForecastMetric;
  historical_points: HistoricalPoint[];
  forecast_points: ForecastPoint[];
  summary: string;
  summary_source: string;
  chart: {
    chart_type: "line";
    x_axis: string;
    series: string[];
    title: string;
  };
  warnings: string[];
}

interface ChatResponseBase {
  message_id: string;
  selected_mode: ChatMode;
  route: string;
  content: string;
  follow_up_questions: string[];
  latency_ms: number;
}

export type ChatResponse =
  | (ChatResponseBase & { response_type: "message"; payload: null })
  | (ChatResponseBase & { response_type: "sql"; payload: SqlPayload })
  | (ChatResponseBase & { response_type: "data_discovery"; payload: DiscoveryPayload })
  | (ChatResponseBase & {
      response_type: "knowledge_catalog" | "data_quality" | "semantica";
      payload: RagPayload;
    })
  | (ChatResponseBase & { response_type: "advanced"; payload: AdvancedPayload })
  | (ChatResponseBase & { response_type: "forecast"; payload: ForecastPayload });

export type ResultCell = string | number | boolean | null;

export interface ChartMetadata {
  chart_type: "table" | "bar" | "line" | "scatter" | string;
  x_axis: string | null;
  y_axes: string[];
  title: string;
  selection_rule: string;
}

export interface SqlExecutionResult {
  columns: string[];
  rows: Array<Record<string, ResultCell>>;
  row_count: number;
  truncated: boolean;
  execution_elapsed_ms: number;
  summary: string;
  summary_source: string;
  chart: ChartMetadata;
}

export interface ApiErrorEnvelope {
  error: { code: string; message: string };
}
