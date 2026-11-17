# 首次接入配置（KyperWorkflow）

KyperWorkflow 不替用户猜配置。接入 MCP 后，助手应**先在会话中**调用 `setup_checklist`，把下面这些条目一次性问清楚，再开始规划任务。未确认的条目对应的任务保持 `blocked`，模型类任务不会自动开始。

本文的“局部路径”指**每台机器自行解析、不随仓库或共享记忆分发**的路径。路径尚未确定时统一写 `待配置`；`setup_checklist` 会把 `待配置`、`局部路径` 和 `<...>` 占位符都当作未确认，不会误报 `ok`。

可以直接把这段作为首轮消息（`setup_checklist` 的 `prompt` 字段会生成同样内容）：

> 接入 KyperWorkflow 后，建议先在会话中确认以下配置，再开始规划任务：
> 1. 被审查项目根目录（必填）：要审查或生成的项目根目录使用哪个局部路径（未确定时写“待配置”）？
> 2. 状态与账本目录（必填）：状态、账本和配置放在哪个项目外的局部路径（未确定时写“待配置”）？
> 3. 依赖库路径（必填）：项目依赖位于哪些局部路径（解释器、PYTHONPATH、node_modules、离线缓存）？
> 4. 项目测试执行许可（必填）：是否允许对受信任项目运行项目测试？在哪个平台执行？
> 5. 宿主检查提供方（必填）：文本语义、模型输出、浏览器和真机检查分别由谁提供？
> 6. 子智能体与模型路由（可选）：需要哪些角色，各自允许哪些模型/effort/并发，fallback 顺序如何？
> 7. 子智能体执行方式（可选）：本次由哪个宿主执行，使用原生子智能体、顺序执行，还是混合？
> 8. 消耗预算（可选）：预算上限和币种？未知消耗时阻塞还是允许预留额？
> 9. 共享记忆接入（可选）：是否把项目图谱摘要写入共享记忆？写入哪个命名空间？
> 10. Skill 安装位置（可选）：安装在项目级还是全局技能目录？

## 条目表

| 项目 | 必填 | 为什么需要 | 配置方式 |
|---|---|---|---|
| Python 运行时 | 是 | 包要求 Python 3.11+（tomllib 与标准库类型注解） | 使用 3.11+ 的独立虚拟环境，记录解释器的局部路径 |
| 被审查项目根目录 | 是 | 所有文件检查都相对一个显式局部路径，缺少它无法界定写入范围 | 会话中给出本机局部路径；未确定写 `待配置`，不要把机器路径提交 |
| 状态与账本目录 | 是 | 状态写在被审查项目内会改变被检查内容并让复核失效 | 项目外的私有局部路径；未确定写 `待配置` |
| 依赖库路径 | 是 | 项目测试与导入解析需要额外库目录、虚拟环境或离线缓存 | 给出 PYTHONPATH 追加项、解释器、node_modules、离线缓存的局部路径 |
| 项目测试执行许可 | 是 | 运行测试等于执行项目代码；需要明确许可与平台清理能力 | 确认是否允许 `project_tests`；Windows 用 Job Object，其他平台受限 |
| 宿主检查提供方 | 是 | text/model/browser/native 本地无法完成，没有回调只能 blocked | 说明由哪一层提供，以及由谁批准 |
| 子智能体与模型路由 | 否 | 角色→模型→effort→并发与 fallback 属于用户决策 | 给出角色名、允许模型与 effort、并发上限、fallback 顺序 |
| 子智能体执行方式 | 否 | 原生角色卡与顺序执行的隔离、成本和可观测性不同 | 给出宿主、`native`/`sequential`/`mixed` 和导出目录 |
| 消耗预算 | 否 | 未知消耗下不能承诺硬预算 | 给出上限与币种，以及未知消耗的预留额或直接阻塞 |
| 共享记忆接入 | 否 | 项目图谱摘要可被其他会话复用 | 指定共享记忆 MCP 与写入的块/实体命名空间 |
| Skill 安装位置 | 否 | Skill 只是流程指引，不会被自动发现 | 复制 `skills/kyper-workflow` 到 `.agents/skills/kyper-workflow` 或全局目录 |

## 检测与"未知"的语义

`setup_checklist(root, state_dir=...)` 只做本地可判定的检测：

- `python_runtime`：当前解释器版本是否 ≥ 3.11。
- `project_root`：给定路径是否存在且为目录。
- `project_tests`：平台是否为原生 Windows（Job Object）；其他平台返回 `platform_limited`。
- `dependency_paths`：是否设置了 `PYTHONPATH`；没有则仍需用户说明实际依赖位置。
- `skills_install`：项目 `.agents/skills/kyper-workflow/SKILL.md` 或包内 Skill 是否存在。
- `host_checks` / `model_routes` / `execution_topology` / `budget` / `shared_memory`：无法从本地推断，默认 `needs_user_input`；只有调用方显式传入配置才记为 `ok`。

状态值只有三种：`ok`、`needs_user_input`、`blocked`/`platform_limited`。**没有"默认可用"这一档**，检测不到就是需要用户确认。

## 与 MCP 的关系

- `capabilities()` 返回 `first_run_setup: required_before_planning`，提醒客户端先走本流程。
- `setup_checklist` 只返回清单与建议话术，不写任何文件、不改配置。
- 用户确认后的值由宿主写入项目外状态目录；KyperWorkflow 不会把模型自报的值当成用户确认。

## 本机配置放哪里（不要提交）

答案属于个人机器，不入库。把 `docs/setup.local.example.json` 复制为下列任一路径并填自己的值：

1. 环境变量 `KYPER_SETUP_CONFIG` 指向的文件；
2. `~/.kyper/setup.local.json`（跨项目共用一份）；
3. `<root>/.kyper/setup.local.json`（单项目，已在 `.gitignore` 中）。

查找顺序：显式 `config_path` → `KYPER_SETUP_CONFIG` → `~/.kyper/setup.local.json` → `<root>/.kyper/setup.local.json`。`setup_checklist` 会回显实际读取的 `config_source`，JSON 坏了记为 `config_error` 并继续把条目当未确认。

- 只认 `state_dir`、`dependency_paths`、`project_tests`、`host_checks`、`model_routes`、`execution_topology`、`budget`、`shared_memory`、`skills_install` 这些键，其他键忽略。
- 文件里可以出现本机局部路径，但它被 `.gitignore` 排除；未确定时写 `待配置`。示例文件只含占位符，`tests/test_onboarding.py` 会检查示例文件不含真实盘符路径，并检查占位符仍被算作未确认。
- 项目图谱同样不写机器路径：`render_json` 在序列化时丢弃解析出的绝对 `root`，只保留仓库相对路径，所以 `.kyper/project-map.json` 与导出的图谱文件可以安全公开。
- 读取本机配置只是**读取**，不构成用户确认的替代：跨项目复用同一份配置前，仍应在会话里确认一遍。
