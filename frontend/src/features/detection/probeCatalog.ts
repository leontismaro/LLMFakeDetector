export interface ProbeOption {
  id: string;
  label: string;
  description: string;
  groupId: ProbeGroupId;
}

export type ProbeGroupId = "protocol" | "specialized" | "token" | "behavior" | "context";

export interface ProbeGroup {
  id: ProbeGroupId;
  label: string;
  description: string;
}

export const PROBE_GROUPS: ProbeGroup[] = [
  {
    id: "protocol",
    label: "协议层",
    description: "检查参数兼容、响应结构、错误语义与网关外壳特征。",
  },
  {
    id: "specialized",
    label: "专属能力层",
    description: "检查函数调用与视觉能力等高阶功能支持情况。",
  },
  {
    id: "token",
    label: "Token 指纹层",
    description: "检查输入 token 计数与官方参考基线之间的偏差模式。",
  },
  {
    id: "behavior",
    label: "行为层",
    description: "检查格式依从、身份冲突与提示词回显风险。",
  },
  {
    id: "context",
    label: "能力压测层",
    description: "检查长上下文检索与长输出稳定性。",
  },
];

export const PROBE_OPTIONS: ProbeOption[] = [
  {
    id: "parameter_probe",
    label: "参数兼容性探针",
    description: "检查 json_schema、tools 等关键参数是否真实支持。",
    groupId: "protocol",
  },
  {
    id: "function_calling_probe",
    label: "函数调用探针",
    description: "检查复杂工具选择与参数结构是否符合声明能力。",
    groupId: "specialized",
  },
  {
    id: "vision_probe",
    label: "视觉能力探针",
    description: "检查图表理解与细节识别等多模态能力。",
    groupId: "specialized",
  },
  {
    id: "gateway_signature_probe",
    label: "网关特征探针",
    description: "检查响应外壳、ID、指纹与 usage 结构是否像成熟网关。",
    groupId: "protocol",
  },
  {
    id: "tokenizer_probe",
    label: "输入 Token 指纹探针",
    description: "对比 prompt_tokens 与官方参考 tokenizer 的差异模式。",
    groupId: "token",
  },
  {
    id: "logprobs_probe",
    label: "Logprobs 探针",
    description: "检查 logprobs 与 top_logprobs 等概率信息能力。",
    groupId: "protocol",
  },
  {
    id: "response_probe",
    label: "响应结构探针",
    description: "检查返回体结构、字段形态与基线匹配程度。",
    groupId: "protocol",
  },
  {
    id: "behavior_probe",
    label: "行为一致性探针",
    description: "检查格式依从、身份冲突与提示词回显风险。",
    groupId: "behavior",
  },
  {
    id: "context_probe",
    label: "上下文压测探针",
    description: "检查长上下文检索与长输出稳定性。",
    groupId: "context",
  },
  {
    id: "error_probe",
    label: "错误响应探针",
    description: "检查非法请求时的错误结构与状态码语义。",
    groupId: "protocol",
  },
];

const PROBE_LABELS = new Map(PROBE_OPTIONS.map((option) => [option.id, option.label]));
const PROBE_OPTIONS_MAP = new Map(PROBE_OPTIONS.map((option) => [option.id, option]));

export function getProbeLabel(probeName: string): string {
  return PROBE_LABELS.get(probeName) ?? probeName;
}

export function getProbeOption(probeName: string): ProbeOption | undefined {
  return PROBE_OPTIONS_MAP.get(probeName);
}
