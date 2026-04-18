# 项目约束

## 通用

- 始终使用中文简体回复。
- 修改代码前先阅读现有实现，保持目录结构清晰，遵循 KISS、YAGNI、DRY、SOLID。
- 搜索文件或文本时优先使用 `rg`。

## Python 虚拟环境

- 本项目 Python 虚拟环境固定为 `"/home/qin/projects/LLMFakeDetector/.venv"`。
- 所有与本项目相关的 Python 命令必须优先使用该虚拟环境中的可执行文件，不要默认使用系统 Python。
- 优先使用：
  - `"/home/qin/projects/LLMFakeDetector/.venv/bin/python"`
  - `"/home/qin/projects/LLMFakeDetector/.venv/bin/pip"`
- 运行测试、脚本、类型检查、启动后端服务时，默认都应基于该虚拟环境。
- 如果虚拟环境缺失或损坏，先提示并修复环境，再继续执行 Python 相关任务。

## 后端约束

- 当前后端以 `OpenAI-compatible` API 检测为 MVP 范围。
- 探针能力按模块拆分到 `backend/app/modules/detection/probes/`，不要把多类检测逻辑堆进一个文件。
- 新增检测能力时，优先复用统一适配器与共享结果结构，避免重复实现请求和解析逻辑。

