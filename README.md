# LLM Fake Detector

用于核验上游 LLM API 真伪的单仓项目骨架，包含：

- `backend/`：探针编排、检测接口、结果聚合
- `frontend/`：检测页、报告页、结果展示
- `fixtures/`：长文本、图片、提示词等测试素材
- `tests/`：后端探针与前端页面测试
- `docs/`：项目背景与架构说明

当前阶段先完成目录结构和模块边界，后续再逐步实现真实探针与报告能力。

## 本地启动

推荐直接使用根目录脚本同时启动前后端：

```bash
bash "./scripts/dev.sh"
```

启动前请先确保：

```bash
".venv/bin/pip" install -e "./backend"
cd "./frontend" && npm install
```

默认地址：

- 前端：`http://127.0.0.1:5173`
- 后端：`http://127.0.0.1:8000`

如需改端口，可在启动前设置环境变量：

```bash
BACKEND_PORT=8010 FRONTEND_PORT=5174 bash "scripts/dev.sh"
```
