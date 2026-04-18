import type { DetectionResponse, DetectionRunSummary } from "./types";

export const MOCK_RUN_SUMMARY: DetectionRunSummary = {
  baseUrl: "https://mock-gateway.example.com/v1",
  modelName: "gpt-4o",
  contextMode: "standard",
  enabledProbes: [
    "parameter_probe",
    "function_calling_probe",
    "vision_probe",
    "gateway_signature_probe",
    "tokenizer_probe",
    "logprobs_probe",
    "response_probe",
    "behavior_probe",
    "context_probe",
    "error_probe",
  ],
  apiKey: "sk-mock-redacted",
};

export const MOCK_DETECTION_RESPONSE: DetectionResponse = {
  model_name: "gpt-4o",
  trust_score: 68,
  findings: [
    {
      probe_name: "parameter_probe",
      status: "pass",
      score: 91,
      summary: "参数探针完成，共检测 2 项特性；明确支持 2 项，疑似静默忽略 0 项。",
      evidence: [
        "response_format=json_schema 生效，返回内容符合约束。",
        "tools/tool_choice 生效，响应返回了 tool_calls。",
      ],
      details: {
        endpoint_url: "https://mock-gateway.example.com/v1/chat/completions",
        cases: {
          response_format_json_schema: {
            status: "pass",
            status_code: 200,
            http_version: "HTTP/1.1",
            response_headers: { "content-type": "application/json" },
          },
          tools_and_tool_choice: {
            status: "pass",
            status_code: 200,
            http_version: "HTTP/1.1",
            tool_call_count: 1,
            response_headers: { "content-type": "application/json" },
          },
        },
      },
    },
    {
      probe_name: "function_calling_probe",
      status: "warn",
      score: 72,
      summary: "函数调用探针存在轻微偏离，复杂参数结构基本可用，但多工具选择稳定性一般。",
      evidence: [
        "复杂 schema 用例中，嵌套字段和枚举值均正确。",
        "多工具选择用例选对了工具，但参数中多出一个非预期字段。",
        "参数偏离集中在 metadata.trace_id 路径。",
      ],
      details: {
        cases: {
          complex_schema_case: {
            status: "pass",
            status_code: 200,
            http_version: "HTTP/1.1",
            selected_tool_name: "submit_order",
            parsed_arguments: {
              order_id: "ord_1001",
              priority: "high",
              items: [{ sku: "A-1", quantity: 2 }],
            },
          },
          tool_selection_case: {
            status: "warn",
            status_code: 200,
            http_version: "HTTP/1.1",
            selected_tool_name: "lookup_invoice",
            mismatch_paths: ["metadata.trace_id"],
            parsed_arguments: { invoice_id: "inv_88", metadata: { trace_id: "extra-field" } },
          },
        },
      },
    },
    {
      probe_name: "vision_probe",
      status: "pass",
      score: 88,
      summary: "视觉探针完成，图表理解与细节识别均符合预期。",
      evidence: [
        "柱状图最高季度识别正确。",
        "水印细节识别正确，隐藏代码提取成功。",
      ],
      details: {
        cases: {
          chart_reasoning_case: {
            status: "pass",
            status_code: 200,
            http_version: "HTTP/1.1",
            observed_content: "Q3",
            response_headers: { "content-type": "application/json" },
          },
          watermark_detail_case: {
            status: "pass",
            status_code: 200,
            http_version: "HTTP/1.1",
            observed_content: "WTR-2048",
            response_headers: { "content-type": "application/json" },
          },
        },
      },
    },
    {
      probe_name: "gateway_signature_probe",
      status: "fail",
      score: 68,
      summary: "网关特征探针已按多次采样完成外壳信号比对，重点检查家族对齐、id 形态、system_fingerprint 与 usage 完整性。",
      evidence: [
        "模型名声明为 OpenAI 风格，当前观测外壳也为 openai。",
        "sample_alpha 使用标准 UUID 作为响应 id；sample_bravo 使用标准 UUID 作为响应 id；sample_charlie 使用标准 UUID 作为响应 id。",
        "OpenAI 风格样本均未返回 system_fingerprint，只能作为弱可疑信号。",
        "多次采样的 usage 结构完整，且核心计数字段语义自洽。",
      ],
      details: {
        endpoint_url: "https://mock-gateway.example.com/v1/chat/completions",
        cases: {
          family_alignment: {
            status: "pass",
            status_code: 200,
            http_version: "HTTP/1.1",
            observed_content: "declared=openai observed=openai",
          },
          id_quality: {
            status: "fail",
            status_code: 200,
            http_version: "HTTP/1.1",
            deviation_kind: "uuid_like_id",
            observed_content: "alpha=123e4567-e89b-12d3-a456-426614174000",
          },
          fingerprint_signal: {
            status: "warn",
            status_code: 200,
            http_version: "HTTP/1.1",
            deviation_kind: "missing_system_fingerprint",
          },
          usage_integrity: {
            status: "pass",
            status_code: 200,
            http_version: "HTTP/1.1",
            observed_content: "prompt/completion/total tokens are coherent across samples",
          },
        },
      },
    },
    {
      probe_name: "tokenizer_probe",
      status: "warn",
      score: 76,
      summary: "输入 Token 指纹探针完成，整体仍接近 OpenAI 参考，但存在轻微偏移。",
      evidence: [
        "大部分样本与参考编码的差值稳定。",
        "emoji_mix 样本的 delta 偏高，建议复核网关包装开销。",
      ],
      details: {
        reference_family: "openai_tiktoken",
        reference_source: "local_tiktoken",
        reference_model_name: "gpt-4o",
        reference_encoding: "o200k_base",
        sample_count: 5,
        delta_range: "2..11",
        negative_delta_count: 0,
        stable_sample_count: 4,
        samples: [
          { name: "plain_text", reference_tokens: 11, observed_prompt_tokens: 13, delta: 2, http_version: "HTTP/1.1" },
          { name: "json_like", reference_tokens: 22, observed_prompt_tokens: 25, delta: 3, http_version: "HTTP/1.1" },
          { name: "emoji_mix", reference_tokens: 17, observed_prompt_tokens: 28, delta: 11, http_version: "HTTP/1.1" },
          { name: "cjk_text", reference_tokens: 19, observed_prompt_tokens: 22, delta: 3, http_version: "HTTP/1.1" },
          { name: "url_blob", reference_tokens: 15, observed_prompt_tokens: 18, delta: 3, http_version: "HTTP/1.1" },
        ],
      },
    },
    {
      probe_name: "logprobs_probe",
      status: "warn",
      score: 58,
      summary: "logprobs 探针部分通过，基础请求可达，但增强参数支持不完整。",
      evidence: [
        "服务端接受了 logprobs 请求，但缺少 top_logprobs 明细。",
        "响应中未返回完整 token 概率列表。",
      ],
      details: {
        endpoint_url: "https://mock-gateway.example.com/v1/chat/completions",
        failure_kind: "partial_support",
      },
    },
    {
      probe_name: "response_probe",
      status: "pass",
      score: 90,
      summary: "响应结构探针已完成基础校验，顶层字段、choice 结构和 usage 语义均基本符合预期。",
      evidence: [
        "响应 id、object、created、model、choices、usage 均存在且类型合理。",
        "total_tokens 与 prompt_tokens + completion_tokens 自洽。",
      ],
      details: {
        endpoint_url: "https://mock-gateway.example.com/v1/chat/completions",
        http_version: "HTTP/1.1",
        baseline_checks: {
          top_level_fields: "pass",
          usage_shape: "pass",
          choice_shape: "pass",
          finish_reason: "warn",
        },
        baseline_matches: ["响应 object 为 chat.completion。", "usage 三字段齐全且数值自洽。"],
        baseline_risks: ["finish_reason 使用 stop，但未提供 system_fingerprint。"],
        response_headers: { "content-type": "application/json", server: "cloudflare" },
      },
    },
    {
      probe_name: "behavior_probe",
      status: "fail",
      score: 54,
      summary: "行为探针完成，共检测 3 项行为约束；严格依从 1 项，存在偏离或注入风险 2 项。",
      evidence: [
        "严格 JSON 依从性测试通过，响应完全符合指定的唯一最小化 JSON。",
        "身份冲突测试失败，响应未遵守固定口令约束，并出现了外部身份话术。",
        "纯 user 提示词回显测试触发通用 prompt echo 风险，仍需人工复核。",
      ],
      details: {
        endpoint_url: "https://mock-gateway.example.com/v1/chat/completions",
        cases: {
          strict_json_compliance: {
            status: "pass",
            status_code: 200,
            http_version: "HTTP/1.1",
            observed_content: "{\"result\":\"ok\",\"count\":2,\"tags\":[\"alpha\",\"beta\"]}",
            response_headers: { "content-type": "application/json" },
          },
          identity_conflict_probe: {
            status: "fail",
            status_code: 200,
            http_version: "HTTP/1.1",
            deviation_kind: "identity_conflict",
            observed_content: "I am Claude, created by Anthropic.",
            response_headers: { "content-type": "application/json" },
          },
          prompt_echo_probe: {
            status: "warn",
            status_code: 200,
            http_version: "HTTP/1.1",
            deviation_kind: "generic_prompt_echo",
            observed_content: "System Prompt: You are a helpful and honest assistant.",
            response_headers: { "content-type": "application/json" },
          },
        },
      },
    },
    {
      probe_name: "context_probe",
      status: "warn",
      score: 63,
      summary: "上下文压测探针完成，small 档通过，medium 档开始出现检索与长输出稳定性衰减。",
      evidence: [
        "needle_in_haystack_small 可准确召回口令。",
        "needle_in_haystack_medium 未能精确返回指定口令。",
        "long_output_probe 在第 31 行后开始出现格式漂移。",
      ],
      details: {
        context_mode: "standard",
        selected_profiles: ["small", "medium"],
        cases: {
          needle_in_haystack_small: {
            status: "pass",
            status_code: 200,
            http_version: "HTTP/1.1",
            observed_content: "Pineapple2024",
          },
          needle_in_haystack_medium: {
            status: "fail",
            status_code: 200,
            http_version: "HTTP/1.1",
            deviation_kind: "wrong_needle_answer",
            observed_content: "The passphrase might be Pineapple2023.",
          },
          long_output_probe: {
            status: "warn",
            status_code: 200,
            http_version: "HTTP/1.1",
            deviation_kind: "format_drift",
            observed_content: "row-31: value-thirty-one",
          },
        },
      },
    },
    {
      probe_name: "error_probe",
      status: "warn",
      score: 46,
      summary: "错误响应探针部分通过，接口返回了结构化错误，但状态码语义不规范。",
      evidence: [
        "错误请求返回了结构化 error 对象。",
        "非法请求返回 500，而不是更合理的 4xx。",
      ],
      details: {
        endpoint_url: "https://mock-gateway.example.com/v1/chat/completions",
        http_version: "HTTP/1.1",
        failure_kind: "server_error",
        response_headers: { "content-type": "application/json" },
      },
    },
  ],
};
