export type ProbeStatus = "pass" | "warn" | "fail" | "skip";
export type ContextMode = "light" | "standard" | "heavy";

export interface ReferenceOptions {
  anthropic_api_key?: string;
  gemini_api_key?: string;
}

export interface DetectionRequest {
  base_url: string;
  api_key?: string;
  model_name: string;
  enabled_probes: string[];
  context_mode: ContextMode;
  reference_options?: ReferenceOptions;
}

export interface ProbeFinding {
  probe_name: string;
  status: ProbeStatus;
  score: number;
  summary: string;
  evidence: string[];
  details?: Record<string, unknown>;
}

export interface DetectionResponse {
  model_name: string;
  trust_score: number;
  findings: ProbeFinding[];
}

export interface DetectionRunSummary {
  baseUrl: string;
  modelName: string;
  contextMode: ContextMode;
  enabledProbes: string[];
  apiKey?: string;
  anthropicApiKey?: string;
  geminiApiKey?: string;
}
