export type ProbeStatus = "pass" | "warn" | "fail" | "skip";

export interface DetectionRequest {
  base_url: string;
  api_key?: string;
  model_name: string;
  enabled_probes: string[];
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
