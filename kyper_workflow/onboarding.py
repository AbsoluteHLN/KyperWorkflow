"""First-run configuration checklist.

KyperWorkflow refuses to guess user decisions: where the reviewed project is,
where private state lives, which host supplies model and semantic checks, which
dependency paths apply and whether project tests may run. The MCP
`setup_checklist` tool returns this list so an assistant asks in-session before
planning work instead of inventing defaults.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from . import __version__

PRODUCT = 'KyperWorkflow'

# Machine-local configuration stays out of the repository. The file holds absolute
# paths and provider choices that belong to one operator's machine, so it is
# git-ignored; an example with placeholders is committed instead.
LOCAL_CONFIG_RELATIVE = Path('.kyper') / 'setup.local.json'
LOCAL_CONFIG_ENV = 'KYPER_SETUP_CONFIG'
CONFIG_KEYS = ('state_dir', 'dependency_paths', 'project_tests', 'host_checks',
               'model_routes', 'budget', 'shared_memory', 'skills_install')

RUNTIME_ITEM = {'id': 'python_runtime', 'category': 'environment', 'required': True,
                'title': 'Python 运行时',
                'why': '包要求 Python 3.11+（tomllib 与标准库类型注解）。',
                'how': '使用 3.11 或更新版本的独立虚拟环境，并记录解释器绝对路径。',
                'question': '使用哪个 Python 解释器（绝对路径）？'}

ITEMS = (
    {'id': 'project_root', 'category': 'scope', 'required': True,
     'title': '被审查项目根目录',
     'why': '所有文件检查都相对一个显式绝对路径，缺少它无法界定写入范围。',
     'how': '在会话中给出项目根目录绝对路径；不使用相对路径或仓库外符号链接。',
     'question': '要审查或生成的项目根目录绝对路径是什么？'},
    {'id': 'state_dir', 'category': 'scope', 'required': True,
     'title': '状态与账本目录（项目外）',
     'why': '任务状态与用量账本若写在被审查项目内，会改变被检查内容并让复核失效。',
     'how': '指定一个项目之外的私有目录，例如 ~/.kyper/state/<project>。',
     'question': '状态、账本和配置放在哪个项目外目录？'},
    {'id': 'dependency_paths', 'category': 'environment', 'required': True,
     'title': '依赖库路径',
     'why': '项目测试与导入解析需要知道额外的库目录、虚拟环境或离线缓存位置。',
     'how': '给出 PYTHONPATH 追加项、虚拟环境解释器绝对路径、node_modules 与离线缓存根目录。',
     'question': '项目依赖位于哪些路径（解释器、PYTHONPATH、node_modules、离线缓存）？'},
    {'id': 'project_tests', 'category': 'checks', 'required': True,
     'title': '项目测试执行许可',
     'why': '运行项目测试等于执行项目代码；只有获得明确许可才可开启，且需平台支持进程树清理。',
     'how': '确认是否允许 project_tests 模式；Windows 使用 Job Object，其他平台受限。',
     'question': '是否允许对受信任项目运行项目测试？在哪个平台执行？'},
    {'id': 'host_checks', 'category': 'checks', 'required': True,
     'title': '宿主检查提供方（text/model/browser/native）',
     'why': '这四类检查本地无法完成；没有宿主回调时相关任务只能保持 blocked。',
     'how': '说明哪一层提供这些检查（当前会话模型 / 浏览器工具 / 真机），以及由谁批准。',
     'question': '文本语义、模型输出、浏览器和真机检查分别由谁提供？'},
    {'id': 'model_routes', 'category': 'routing', 'required': False,
     'title': '子智能体与模型路由',
     'why': '角色→模型→effort→并发与 fallback 属于用户决策；未批准的路由不得使用。',
     'how': '给出角色名、允许的模型与 effort 档位、并发上限、允许的 fallback 顺序。',
     'question': '需要哪些子智能体角色，各自允许哪些模型/effort/并发，fallback 顺序如何？'},
    {'id': 'budget', 'category': 'routing', 'required': False,
     'title': '消耗预算',
     'why': '未知消耗下不能承诺硬预算；需要上限、币种和未核算额度的处理方式。',
     'how': '给出金额或令牌上限、币种，以及未知消耗时允许的预留额或直接阻塞。',
     'question': '本次任务的预算上限和币种是什么？未知消耗时阻塞还是允许预留额？'},
    {'id': 'shared_memory', 'category': 'integration', 'required': False,
     'title': '共享记忆接入',
     'why': '项目图谱摘要可写入共享记忆，便于其他会话复用结构事实。',
     'how': '确认是否接入共享记忆 MCP，以及写入哪个块或实体命名空间；不接入则只写本地文档。',
     'question': '是否把项目图谱摘要写入共享记忆？写入哪个命名空间？'},
    {'id': 'skills_install', 'category': 'integration', 'required': False,
     'title': 'Skill 安装位置',
     'why': 'Skill 只是流程指引，不会被自动发现；需要放到宿主能读取的目录。',
     'how': '复制 skills/kyper-workflow 到目标项目的 .agents/skills/kyper-workflow，或全局技能目录。',
     'question': 'Skill 安装在项目级还是全局技能目录？'},
)

ALL_ITEMS = (RUNTIME_ITEM,) + ITEMS


def local_config(root=None, *, path=None):
    """Read operator-local settings, or a placeholder-only example, from disk.

    Precedence: explicit `path`, then `KYPER_SETUP_CONFIG`, then
    `<root>/.kyper/setup.local.json`. Values are never invented: a missing file is
    reported as `source: None` and every item stays a question.
    """
    candidates = []
    if path:
        candidates.append(Path(path))
    elif os.environ.get(LOCAL_CONFIG_ENV):
        candidates.append(Path(os.environ[LOCAL_CONFIG_ENV]))
    else:
        candidates.append(Path.home() / '.kyper' / 'setup.local.json')
    if root and Path(root) / LOCAL_CONFIG_RELATIVE not in candidates:
        candidates.append(Path(root) / LOCAL_CONFIG_RELATIVE)
    for candidate in candidates:
        if not candidate.is_file():
            continue
        try:
            data = json.loads(candidate.read_text(encoding='utf-8'))
        except (ValueError, UnicodeError) as error:
            return {}, str(candidate), 'unreadable: %s' % type(error).__name__
        if not isinstance(data, dict):
            return {}, str(candidate), 'unreadable: expected a JSON object'
        return {key: data[key] for key in CONFIG_KEYS if key in data}, str(candidate), None
    return {}, (str(candidates[0]) if candidates else None), None


def _detect(item_id, context):
    root = context.get('root')
    config = context.get('config') or {}
    if item_id == 'python_runtime':
        return 'ok' if sys.version_info >= (3, 11) else 'blocked'
    if item_id == 'project_root':
        return 'ok' if root and Path(root).is_dir() else 'needs_user_input'
    if item_id == 'state_dir':
        return 'ok' if (context.get('state_dir') or config.get('state_dir')) else 'needs_user_input'
    if item_id == 'dependency_paths':
        if context.get('environ', {}).get('PYTHONPATH') or config.get('dependency_paths'):
            return 'ok'
        return 'needs_user_input'
    if item_id == 'project_tests':
        return 'ok' if os.name == 'nt' else 'platform_limited'
    if item_id == 'skills_install':
        candidates = []
        if root:
            candidates.append(Path(root) / '.agents' / 'skills' / 'kyper-workflow' / 'SKILL.md')
        candidates.append(Path(__file__).resolve().parent.parent / 'skills' / 'kyper-workflow' / 'SKILL.md')
        return 'ok' if any(path.is_file() for path in candidates) else 'needs_user_input'
    if item_id in ('host_checks', 'model_routes', 'budget', 'shared_memory') and (
            context.get(item_id) or config.get(item_id)):
        return 'ok'
    return 'needs_user_input'


def checklist(root=None, *, state_dir=None, environ=None, host_checks=None,
              model_routes=None, budget=None, shared_memory=None,
              config=None, config_path=None):
    """Return the first-run items, detected state and a session prompt.

    Answers recorded in the git-ignored local file count as confirmed; explicit
    keyword arguments override them. Nothing here is written to disk.
    """
    if config is None:
        config, source, error = local_config(root, path=config_path)
    else:
        source, error = ('<caller-supplied>' if config else None), None
    context = {'root': root, 'state_dir': state_dir,
               'environ': dict(environ if environ is not None else os.environ),
               'host_checks': host_checks, 'model_routes': model_routes,
               'budget': budget, 'shared_memory': shared_memory, 'config': config}
    items = [dict(item, status=_detect(item['id'], context)) for item in ALL_ITEMS]
    needs = [item['id'] for item in items if item['status'] in ('needs_user_input', 'blocked')]
    return {'product': PRODUCT, 'version': __version__, 'items': items,
            'needs_input': needs, 'ready': not needs,
            'config_source': source, 'config_error': error,
            'config_note': ('machine-local values are read from a git-ignored file; '
                            'nothing is committed or uploaded'),
            'prompt': session_prompt(items, needs)}


def session_prompt(items=None, needs=None):
    """A message the assistant can send at the start of a session."""
    items = list(items) if items is not None else [
        dict(item, status=_detect(item['id'], {})) for item in ALL_ITEMS]
    if needs is None:
        needs = [item['id'] for item in items
                 if item['status'] in ('needs_user_input', 'blocked')]
    pending = [item for item in items if item['id'] in needs]
    if not pending:
        return '%s 配置已齐备，可以开始规划任务。' % PRODUCT
    lines = ['接入 %s 后，建议先在会话中确认以下配置，再开始规划任务：' % PRODUCT, '']
    for index, item in enumerate(pending, 1):
        marker = '（必填）' if item['required'] else '（可选）'
        lines.append('%d. %s%s：%s' % (index, item['title'], marker, item['question']))
    lines += ['', '未确认前，相关任务会保持 blocked，模型类任务不会自动开始。',
              '直接逐条回答即可；我会把它们写入项目外的状态目录并作为已确认配置使用。']
    return '\n'.join(lines)


def markdown():
    """Documentation table generated from the same source as the MCP tool."""
    lines = ['| 项目 | 必填 | 为什么需要 | 配置方式 |', '|---|---|---|---|']
    for item in ALL_ITEMS:
        lines.append('| %s | %s | %s | %s |' % (
            item['title'], '是' if item['required'] else '否', item['why'], item['how']))
    return '\n'.join(lines)
