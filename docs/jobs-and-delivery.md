# 任务、场景与投递

导出不再只是「在某个路径生成一个 PDF」。一次导出现在是一个**任务**：有清单、有状态、有产物哈希，并且可以继续被**投递**到 Obsidian、文件夹、剪贴板或一个正在运行的 Agent。

这三层是分开的，任何一层失败都不会让前面的成果消失。

## 三个概念

| 概念 | 是什么 | 存在哪 |
|---|---|---|
| **任务 job** | 一次导出的全部记录：来源、会话、时间窗、消息数、首尾消息、产物哈希、投递结果 | `<jobs_root>/Ready/<jobId>/` |
| **场景 scene** | 一套保存好的配方：会话 + 时间窗 + 关键词 + 输出格式 + 提示词 + 投递目标 + 快捷键 | 内置 4 个，自定义写在 `scenes.json` |
| **投递 delivery** | 把任务产物送到某处：文件夹、Obsidian vault、剪贴板、正在运行的 Agent | 见 `--deliver` |

## 目录契约

```
<jobs_root>/                    默认 %LOCALAPPDATA%\WeChatAIMemory\jobs
├── .staging/<jobId>/           写入中，崩溃或中断后会被移到 Failed
│   ├── manifest.json
│   ├── state.json
│   └── files/                  PDF / Markdown / JSON / *_assets/
├── Ready/<jobId>/              原子提交后的成品，目录名就是任务号
├── Failed/<jobId>/             失败或中断，保留现场以便排查
└── Logs/<YYYY-MM-DD>.log
```

提交是一次 `rename`：只有全部产物写完、算完哈希，任务才会出现在 `Ready` 里。所以 `Ready` 下不会出现「看起来能投递、实际只有一半」的 PDF。

### manifest.json

```json
{
  "schema_version": 1,
  "job_id": "20261115T151816-5f1798",
  "created_at": "2026-11-15T15:18:16Z",
  "source": { "kind": "json", "label": "...demo_chat.json", "wechat_version": null },
  "conversation": { "id": "eco-project", "name": "ECO 项目讨论群" },
  "window": { "start": "2026-08-01T00:00:00Z", "end": "2026-08-31T23:59:59Z", "query": null },
  "scene": { "id": "decision-review", "name": "项目决策复盘" },
  "message_count": 8,
  "reference": { "first": { "id": "m001", "...": "..." }, "last": { "id": "m008", "...": "..." } },
  "artifacts": [{ "name": "ECO 项目讨论群.pdf", "kind": "pdf", "size": 518621, "sha256": "..." }],
  "notes": ["图片 1 张", "文件 1 个"]
}
```

`reference` 是范围首尾消息的摘要，用来在不打开 PDF 的情况下确认「我选对了时间窗」。`artifacts[].sha256` 让同一份归档可以被校验、去重，也是后续增量同步的基础。

### state.json 与状态机

| 状态 | 含义 |
|---|---|
| `running` | 正在写入 `.staging` |
| `ready` | 产物已提交，尚未投递。**不算结束状态，清理会保护它** |
| `delivered` | 已送达目标位置 |
| `copied` | 内容在剪贴板里，等用户粘贴（投递失败或目标不可达时的结果） |
| `failed` | 投递彻底失败，或渲染中断 |
| `expired` | 预留：超过保留期后标记 |

`attempts` 记录投递次数，失败后用同一个任务号重试即可。

## 命令行

```bash
# 用场景导出并投递到 Obsidian，同时记为任务
wechat-context-exporter --source examples/demo_chat.json \
  --conversation eco-project --scene decision-review \
  --deliver obsidian --deliver-to "D:/Notes/Vault"

# 只记录，不投递
wechat-context-exporter --source ... --conversation eco-project --record

# 投递给正在运行的 Agent（只粘贴路径与提示词，默认不接管剪贴板附件）
wechat-context-exporter --source ... --conversation eco-project \
  --scene commitments --deliver agent --agent claude

# 场景列表 / 任务历史 / 清理
wechat-context-exporter --list-scenes
wechat-context-exporter --list-jobs
wechat-context-exporter --prune-jobs 30
```

`--scene` 提供时间窗、关键词、输出格式、提示词和默认投递目标；命令行显式参数优先。命令行仍保持旧行为：不指定 `--scene`、`--deliver`、`--jobs-dir`、`--record` 时，就是一次不落记录的一键导出。

## 内置场景

| ID | 名称 | 默认窗口 | 默认投递 |
|---|---|---|---|
| `group-digest` | 群聊总结 | 最近 1 天 | 文件夹 |
| `decision-review` | 项目决策复盘 | 最近 30 天 | Obsidian |
| `commitments` | 待办与承诺 | 最近 14 天 | 剪贴板 |
| `change-trace` | 需求变更追溯 | 最近 60 天 | 文件夹 |

自定义场景写在 `scenes.json`（默认 `%LOCALAPPDATA%\WeChatAIMemory\scenes.json`）。**同 id 的自定义场景会覆盖内置场景**，删掉自定义条目就恢复内置版本。

```json
{
  "schema_version": 1,
  "scenes": [
    {
      "id": "weekly-report",
      "name": "周报素材",
      "days": 7,
      "query": null,
      "target": "folder",
      "prompt": "按项目分组，整理本周进展、风险和下周计划。",
      "shortcut": 5
    }
  ]
}
```

## 提示词

投递出去的提示词由三部分组成，顺序固定：

1. **范围头**：归档绝对路径、会话、时间窗、消息数、任务号；
2. **场景正文**：场景里写的任务（内置场景已写好，也支持 `{conversation}`、`{start}`、`{files}` 等占位符，未知占位符原样保留）；
3. **引用规范**：每条结论用 `[消息ID]` 标注出处，找不到依据就写「归档中未提及」。

第三段是刻意固定的：归档的价值在于可追溯，一个不能回溯到消息 ID 的总结只是又一次猜测。

## 失败策略

- **渲染失败** → 任务进 `Failed`，保留已经写出的文件，异常照常抛出；
- **投递失败** → 自动回落到剪贴板：产物一定在剪贴板里，用户离一次 `Ctrl+V` 只有一步；状态记为 `copied`；
- **剪贴板也失败** → 状态 `failed`，两条错误都写进 `state.json`；
- **进程被杀** → 下次运行 `recover_stale()` 把 `.staging` 里的残留移到 `Failed`，并注明 `interrupted before commit`。

## 环境变量

| 变量 | 作用 |
|---|---|
| `WECHAT_AI_MEMORY_OUTPUT_DIR` | 产出根目录，默认 `C:\微信记忆` |
| `WECHAT_AI_MEMORY_JOBS_DIR` | 覆盖任务目录（便携版、测试隔离） |
| `WECHAT_AI_MEMORY_SCENES_FILE` | 覆盖场景文件路径 |

## 产出位置

用户能看到的东西统一落在**一个**根目录，默认 `C:\微信记忆`（非 Windows 为 `~/微信记忆`），由 `paths.output_root()` 统一提供：

| 产出 | 路径 |
|---|---|
| GUI 的默认导出文件 | `C:\微信记忆\WeChat_Memory_<时间戳>.pdf` |
| 「投递到文件夹」的默认目标 | `C:\微信记忆`（每次导出建 `<日期> <会话名>/` 子目录） |
| Obsidian 投递 | 由 `--deliver-to` 指定的 vault，不受上面影响 |

任务目录（`manifest.json` / `state.json` / `.staging`）**故意不放在这里**：它是程序状态，不是档案；放进归档目录会让用户误删或误改，而删掉它等于丢掉历史与去重依据。任务目录仍在 `%LOCALAPPDATA%\WeChatAIMemory\jobs`。

CLI 的 `--output` 仍然要求显式指定（脚本需要确定性），错误提示里会带上当前归档根目录。

## 图形界面

两个窗口的「场景 / 投递」都在导出区：选场景会自动带上时间窗与输出选项，选投递目标后可填目录或 Agent 名称。GUI 的每次导出都会记录为任务，并把 PDF 额外复制回你在保存对话框里选的路径——任务目录用于追溯，你选的位置用于日常使用。

## 与路线图的对应

这一层是 `v0.4`「持久化记忆库、增量同步、稳定 ID、去重」的底座：`manifest.json` 里的来源指纹、消息区间和 `sha256` 已经足够判断「这次导出和上次是不是同一段对话」，`Ready` / `Failed` 的分离则让重跑不会污染历史。
