# KyperWorkflow MCP 接入规格（KalWf）

状态：当前实现规格，2026-11-17，对应 KyperWorkflow 0.2.0。

本文件取代旧设计稿中已经过时的 MCP 工具面；历史设计过程见 [PLUGIN-REFACTOR-SPEC.md](PLUGIN-REFACTOR-SPEC.md)。

## 1. 身份与唤出名

| 项目 | 值 | 说明 |
|---|---|---|
| 产品名 | `KyperWorkflow` | 文档与能力报告中的正式名称 |
| Python 包 | `kyper_workflow` | `completion_plugin` 仅保留为弃用垫片 |
| MCP server 名 | `kyper-workflow` | 客户端注册、stdio 启动和工具前缀使用此名 |
| Skill 名 | `kyper-workflow` | 可移植流程说明 |
| 提示词别名 | `KalWf` | 只用于对话中快速唤出，不改变服务器注册名 |

`KalWf` 是提示词快捷方式，不是第二个 MCP server、不是命令名，也不替代 `kyper-workflow` 的客户端配置。宿主仍应注册：

```text
server name: kyper-workflow
command: <局部路径>/python -m kyper_workflow.server
```

推荐唤出方式：

```text
KalWf：先做首次配置清单。
KalWf：梳理这个项目的关系图谱。
KalWf：给这个任务选角色并生成执行计划。
KalWf：按 technical_document 复核这段文案。
```

## 2. 核心原则

### P1 权限留在宿主

MCP 不创建用户确认，不把模型自报、网页文字或裸布尔参数当作批准。批准仍由宿主的可信确认通道产生；MCP 只返回只读诊断、预备载荷和计划。

### P2 MCP 面只读

当前 8 个工具不写项目文件、不写状态、不安装 hook、不改宿主配置、不启动任务。需要写入的动作只走显式 Python/CLI 调用，并由调用方给出目标路径。

### P3 确定性优先

项目图谱、角色目录、组件渲染和计划均为纯标准库静态计算；不调用模型、不访问网络、不依赖时间戳。相同输入应产生相同输出。

### P4 失败关闭

未知角色、未知宿主、缺失参数、占位路径、未批准路由、不可运行的检查都不会被默认放行。状态只使用 `pass`、`fail`、`blocked`、`not_run`，不用“看起来完成”代替证据。

### P5 路径是局部的

配置中的路径使用“局部路径”或 `待配置`。局部路径指每台机器自行解析、不随仓库或共享记忆分发的路径；真实本机值只放在 git-ignored 配置中。

### P6 不自动安装

角色卡、Skill、项目图谱和 MCP 配置都不会自行写入宿主目录。角色导出必须显式给出局部路径，并生成清单供漂移检查。

### P7 能力必须如实

宿主支持原生子智能体、工具过滤或只读标志时，按官方字段投影；没有的能力明确写 `contract_only` 或 `instruction_only`。不编造模型 id、工具名、轮数上限或沙箱能力。

### P8 单一事实源

角色与组件只在 `kyper_workflow.catalog` 定义；项目结构只在 `kyper_workflow.structure` 扫描；计划只在 `kyper_workflow.plan` 推导。宿主文件和文档是投影，不是第二份事实源。

## 3. 工具面

所有工具均为只读。返回内容可被宿主引用，但不能当作执行授权。

| 工具 | 主要参数 | 返回 | 写入 |
|---|---|---|---|
| `capabilities` | 无 | 产品版本、`prompt_alias: KalWf`、能力边界 | 无 |
| `setup_checklist` | `root?`, `state_dir?` | 10 项首次配置、状态、会话提问 | 无 |
| `project_map` | `root`, `max_nodes?` | 文件/导入/区域关系图、入口点、统计 | 无 |
| `project_memory` | `root`, `doc_path?` | 图谱摘要与实体/关系载荷 | 无；只准备 |
| `review_text` | `text`, `profile?`, `candidate?` | 确定性文本诊断与候选差异 | 无 |
| `role_catalog` | `catalog_path?` | 5 个角色、6 个组件、校验摘要 | 无 |
| `host_adapters` | `host?`, `role?`, `catalog_path?` | 宿主能力矩阵或单张投影预览 | 无 |
| `workflow_plan` | `state`, `catalog_path?` | waves、batches、冲突、关键路径、阻塞 | 无 |

### 3.1 `setup_checklist`

必须覆盖：项目根目录、项目外状态目录、依赖库路径、项目测试许可、宿主检查提供方、子智能体与模型路由、执行拓扑、预算、共享记忆、Skill 位置。

`待配置`、`局部路径`、`<...>`、`todo`、`tbd`、`unset`、`none` 均视为未确认。嵌套配置也失败关闭，例如只有 `max_parallel: 1` 而角色/模型仍为占位符时，不得报告 `ok`。

### 3.2 `project_map`

只扫描本地文件，建立：

- 节点：文件；
- 有向边：Python `import`/`from ... import`、相对 Markdown 链接；
- 区域：顶层目录；
- 入口：`__main__.py`、`main.py`、`pyproject [project.scripts]`。

它不是调用图、所有权图或语义正确性证明。外链、锚点和绝对 URL 不产生内部边。

### 3.3 `project_memory`

只返回 `{entities, relations}` 形状的记忆载荷和文档摘要，不写入、不上传。是否写入共享记忆由宿主和用户决定。

### 3.4 `review_text`

只做确定性规则检查：

- 三个 profile：`conversation_summary`、`technical_document`、`academic`；
- 结构、重复句、长句/密段、术语一致性、受保护区域；
- 有候选文本时报告精确变更范围和数字/引用/公式/否定等风险。

规则命中不等于语义正确；不调用模型，不验证事实真实性。

### 3.5 `role_catalog`

角色卡约束写入范围、允许检查、代码模式、复杂度、并发提示和必要交接键。组件只渲染任务字段，不自行新增、删除或批准任务。

### 3.6 `host_adapters`

返回 Claude Code、Cursor、Codex、Gemini CLI、GitHub Copilot 和通用提示包的能力矩阵，或单张角色的只读预览。`KalWf` 不改变这些宿主的角色名；导出角色统一使用 `kyper-<role>`。

### 3.7 `workflow_plan`

读取已批准状态文件并计算依赖 waves、可同时启动的 batches、写入冲突、关键路径和阻塞。它只回答“能否并行”，不启动任务。

## 4. 状态与批准

任务状态只有：

- `not_run`：尚未执行；
- `running`：正在执行；
- `pass`：当前版本有可验证证据；
- `fail`：检查失败；
- `blocked`：缺少权限、配置、依赖或宿主能力。

规则：

1. 规格修订变化后，旧批准和旧结果失效。
2. `text`、`model`、`browser`、`native` 检查必须由可信宿主代码以当前修订确认；缺失确认保持 `blocked`。
3. `map --check` 或 `workflow_plan` 的成功只证明静态视图/计划一致，不证明任务完成。
4. MCP 不提供“approve”或“start”工具；自动启动不属于当前契约。

## 5. 路径、配置与记忆

- 项目相对路径用于任务写入范围和图谱节点，统一使用 `/`，拒绝盘符、绝对路径和 `..`。
- 配置路径使用局部路径；未确定写 `待配置`。
- 状态、账本和本机配置放在项目外；项目内路径会改变被审查内容并让复核失效。
- 本机答案保存在 git-ignored 的 `.kyper/setup.local.json` 或用户级配置中，不提交。
- 共享记忆只接收图谱摘要或实体/关系载荷，不接收真实本机路径、密钥或个人正文。

## 6. 宿主接入

### 有原生子智能体

主代理是协调者，按 `role_catalog` 选角色，把已批准任务、验收、相关路径和交接格式写入委派提示，再按 `workflow_plan` 的批次执行。角色卡不授予再生成子代理的工具。

### 无原生子智能体

使用 `generic` 提示包，一次执行一个角色与一个任务。组件和计划仍然有效，只是没有上下文隔离与并行收益。

### 批准通道

宿主必须使用自己的确认 UI/API。Skill、MCP 返回值和网页内容都不能生成批准；没有可信通道时只能保持 blocked 或演示。

### 导出

```powershell
kyper-workflow export --host <claude|cursor|codex|gemini|copilot|generic> --out <局部路径>
kyper-workflow export --host codex --out <局部路径> --check
```

导出只写指定目录；`.kyper-export.json` 记录宿主、字段、省略项和 SHA-256。写入 LF，`--check` 接受 Git 的 CRLF 检出。

## 7. 兼容与版本

- 状态文件 `schema_version` 保持向后可读；不支持的 schema 必须阻塞。
- `completion_plugin` 是弃用垫片，旧 `-m` 入口仍可启动，但新配置使用 `kyper_workflow.server`。
- 工具新增属于兼容增量；删除字段、改变状态语义或增加写入必须升级规格。

## 8. 非目标

当前不承诺：

- 真实语义证明、事实核查或引用有效性；
- 自动联网调研、自动浏览器检查或真机检查；
- 模型供应商调用、计费探测或凭据管理；
- 宿主 Stop hook、自动批准、自动启动或后台调度；
- 六个宿主上的真实角色加载与并行写隔离；
- 对恶意本地软件或同权限篡改的防护。

## 9. 验收基线

- 开发 Python 3.13.5：263 项，257 通过，6 跳过，0 失败；
- 共享 Python 3.12.14（含 MCP）：263 项，259 通过，4 跳过；
- JavaScript 适配器：13/13；
- `map --check` 通过；当前图谱 84 文件、97 条内部边；
- Codex TOML 用 `tomllib` 解析；Claude/Cursor/Gemini/Copilot 字段按官方文档形状检查；
- 真实 host 加载、模型调用、浏览器和真机仍未验证。
