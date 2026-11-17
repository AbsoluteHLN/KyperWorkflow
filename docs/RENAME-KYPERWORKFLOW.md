# 改名：CompletionQAMCP → KyperWorkflow

2026-11-17。产品名、Python 包名、CLI、MCP server 名与 Skill 名统一为 KyperWorkflow。

| 位置 | 旧 | 新 |
|---|---|---|
| 产品名 | Completion Review Plugin / CompletionQAMCP | KyperWorkflow |
| Python 包 | `completion_plugin` | `kyper_workflow` |
| CLI 脚本 | `completion-review` | `kyper-workflow` |
| MCP server 名 | `completion-review-plugin` | `kyper-workflow` |
| Skill | `skills/completion-review` | `skills/kyper-workflow` |
| DSH 适配器 | `completionqa` | `kyperworkflow` |
| 版本 | 0.1.2 | 0.2.0 |
| GitHub 仓库 | `AbsoluteHLN/CompletionQAMCP` | `AbsoluteHLN/KyperWorkflow` |

GitHub 仓库已改名为 `https://github.com/AbsoluteHLN/KyperWorkflow.git`，本仓库 `origin` 已同步。旧地址由 GitHub 重定向，但新的克隆与文档统一使用新地址。仓库改名不触发发布：源码提交与推送仍另行处理，`kyper-workflow` 控制台脚本未经打包发布不可当作已安装版本使用。

## 兼容性

- `completion_plugin/__init__.py` 保留为**弃用垫片**：其 `__path__` 指向 `kyper_workflow`，因此 `python -m completion_plugin.server` / `python -m completion_plugin.cli` 仍可运行，并发出 `DeprecationWarning`。新配置应改用 `kyper_workflow`。
- 状态文件 `schema_version` 仍是 1，旧任务状态可直接读取；没有任何迁移脚本。
- 旧 `completion-review` 控制台脚本不再生成；如已安装旧版，重装本包后使用 `kyper-workflow`。

## 已部署 MCP 的升级步骤

如果 MCP 客户端仍指向共享环境里的旧包（例如 `-m completion_plugin.server`），需要在该环境重装：

```powershell
# 发行名也改了，所以 --upgrade 不会替换旧包：先卸载再安装
& '<python.exe>' -m pip uninstall -y completion-review-plugin
& '<python.exe>' -m pip install -e "<本仓库路径>[mcp]"   # 可编辑安装，改代码即生效
```

然后二选一：

1. 保持旧入口不变（垫片继续工作），或
2. 把客户端配置改为 `-m kyper_workflow.server`，重启该 MCP server。

`capabilities()` 会返回 `product`/`version`，可用来确认实际运行的是新版。

保留旧入口时注意：旧入口不只是 `__path__` 转发，包属性也要转发，因为 `completion_plugin.server` 的模块体里有 `from . import __version__`。`completion_plugin/__init__.py` 因此重新导出了 `__version__`，`tests/test_rename_shim.py` 覆盖这一点。

经宿主网关（例如把 server 挂在 HTTP 网关后面）连接的客户端会缓存 `tools/list` 结果：升级后要在宿主侧重连或重启该 server 才能看到新工具，直接 stdio 探测可作为对照。

## 未改名之处

- DSH 宿主侧服务名 `completionQAHost` 保持不变：它是**宿主提供**的集成缝，由宿主实现，改名需要宿主同步改动。
- `docs/RELEASE-0.1.1.md`、`docs/RELEASE-0.1.2.md` 是历史发布记录，保留原文。

## 新增能力（同批）

- `kyper_workflow.structure`：确定性的项目关系图谱。节点=文件，有向边=观测到的 Python 导入或相对文档链接，按区域分组并标注入口点。一次扫描输出同一张图的四个视图：`docs/PROJECT-MAP.md`（内嵌文件级 Mermaid 与按区域折叠的同一张图）、`.kyper/project-map.json`、`.kyper/project-graph.dot`、`.kyper/project-graph.graphml`、`.kyper/project-graph.tsv`；`map --graph --graph-format json|mermaid|dot|graphml|tsv` 单视图打印，`--max-nodes N` 只保留度数最高的 N 个文件；`--check` 覆盖全部视图。共享记忆的实体/关系载荷仅准备，不写入。全部为标准库静态分析，无时间戳、无模型调用。
- `kyper_workflow.onboarding`：首次接入配置清单，经 MCP `setup_checklist` 暴露。
