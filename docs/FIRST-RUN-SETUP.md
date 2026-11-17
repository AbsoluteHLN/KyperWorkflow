# 首次接入配置（KyperWorkflow）

KyperWorkflow 不替用户猜配置。接入 MCP 后，助手应**先在会话中**调用 `setup_checklist`，把下面这些条目一次性问清楚，再开始规划任务。未确认的条目对应的任务保持 `blocked`，模型类任务不会自动开始。

可以直接把这段作为首轮消息（`setup_checklist` 的 `prompt` 字段会生成同样内容）：

> 接入 KyperWorkflow 后，建议先在会话中确认以下配置，再开始规划任务：
> 1. 被审查项目根目录（必填）：要审查或生成的项目根目录绝对路径是什么？
> 2. 状态与账本目录（必填）：状态、账本和配置放在哪个项目外目录？
> 3. 依赖库路径（必填）：项目依赖位于哪些路径（解释器、PYTHONPATH、node_modules、离线缓存）？
> 4. 项目测试执行许可（必填）：是否允许对受信任项目运行项目测试？在哪个平台执行？
> 5. 宿主检查提供方（必填）：文本语义、模型输出、浏览器和真机检查分别由谁提供？
> 6. 子智能体与模型路由（可选）：需要哪些角色，各自允许哪些模型/effort/并发，fallback 顺序如何？
> 7. 消耗预算（可选）：预算上限和币种？未知消耗时阻塞还是允许预留额？
> 8. 共享记忆接入（可选）：是否把项目图谱摘要写入共享记忆？写入哪个命名空间？
> 9. Skill 安装位置（可选）：安装在项目级还是全局技能目录？

## 条目表

| 项目 | 必填 | 为什么需要 | 配置方式 |
|---|---|---|---|
| Python 运行时 | 是 | 包要求 Python 3.11+（tomllib 与标准库类型注解） | 使用 3.11+ 的独立虚拟环境，记录解释器绝对路径 |
| 被审查项目根目录 | 是 | 所有文件检查都相对一个显式绝对路径，缺少它无法界定写入范围 | 会话中给出绝对路径；不要用相对路径或仓库外符号链接 |
| 状态与账本目录 | 是 | 状态写在被审查项目内会改变被检查内容并让复核失效 | 项目外的私有目录，例如 `~/.kyper/state/<project>` |
| 依赖库路径 | 是 | 项目测试与导入解析需要额外库目录、虚拟环境或离线缓存 | 给出 PYTHONPATH 追加项、解释器绝对路径、node_modules、离线缓存根 |
| 项目测试执行许可 | 是 | 运行测试等于执行项目代码；需要明确许可与平台清理能力 | 确认是否允许 `project_tests`；Windows 用 Job Object，其他平台受限 |
| 宿主检查提供方 | 是 | text/model/browser/native 本地无法完成，没有回调只能 blocked | 说明由哪一层提供，以及由谁批准 |
| 子智能体与模型路由 | 否 | 角色→模型→effort→并发与 fallback 属于用户决策 | 给出角色名、允许模型与 effort、并发上限、fallback 顺序 |
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
- `host_checks` / `model_routes` / `budget` / `shared_memory`：无法从本地推断，默认 `needs_user_input`；只有调用方显式传入配置才记为 `ok`。

状态值只有三种：`ok`、`needs_user_input`、`blocked`/`platform_limited`。**没有"默认可用"这一档**，检测不到就是需要用户确认。

## 与 MCP 的关系

- `capabilities()` 返回 `first_run_setup: required_before_planning`，提醒客户端先走本流程。
- `setup_checklist` 只返回清单与建议话术，不写任何文件、不改配置。
- 用户确认后的值由宿主写入项目外状态目录；KyperWorkflow 不会把模型自报的值当成用户确认。
