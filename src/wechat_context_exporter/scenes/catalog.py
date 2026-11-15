"""Scenes that ship with the app.

Each one answers a question that actually gets asked of a chat archive.  They are
deliberately narrow: "summarise the group" is a prompt; "who promised what and
did they deliver" is a task with an answer that can be checked against message
ids.

Ids are stable -- a user's scenes.json may override them by id, and shortcuts
1-4 are reserved for these four.
"""

from __future__ import annotations

from .models import Scene

BUILTIN_SCENES: tuple[Scene, ...] = (
    Scene(
        id="group-digest",
        name="群聊总结",
        description="最近一天的群聊纪要：结论、待办、悬空问题。",
        days=1,
        target="folder",
        shortcut=1,
        builtin=True,
        prompt=(
            "把归档整理成一份能在一分钟内读完的纪要：\n"
            "1. 一句话结论：这段时间这个群在推进什么。\n"
            "2. 分段摘要：按话题归类，不要按时间流水账。\n"
            "3. 明确的待办：谁 / 做什么 / 什么时间前，缺一项就写“未指定”。\n"
            "4. 尚未解决的分歧或悬空问题。\n"
            "5. 值得回看的原始消息，给出消息 ID。"
        ),
    ),
    Scene(
        id="decision-review",
        name="项目决策复盘",
        description="把一段时间的讨论还原成可追溯的决策记录。",
        days=30,
        target="obsidian",
        shortcut=2,
        builtin=True,
        prompt=(
            "把归档还原成决策记录，逐条列出：\n"
            "议题 → 当时的结论 → 依据（引用消息 ID）→ 谁提过反对意见、理由是什么 → "
            "后续是否执行、有没有被推翻。\n"
            "最后给一张三栏清单：已定 / 待定 / 已推翻。\n"
            "只写归档里出现过的决策，不要把讨论中的猜测当成结论。"
        ),
    ),
    Scene(
        id="commitments",
        name="待办与承诺",
        description="谁答应了什么，兑现了没有。",
        days=14,
        target="clipboard",
        shortcut=3,
        builtin=True,
        prompt=(
            "只抽取“承诺”和“待办”：谁答应了什么、给谁定了什么时间、后来有没有兑现。\n"
            "按“已兑现 / 未兑现 / 无法判断”三组输出，每条都带消息 ID 和日期。\n"
            "没有明确承诺的内容不要写进来，宁缺勿滥。"
        ),
    ),
    Scene(
        id="change-trace",
        name="需求变更追溯",
        description="按时间还原需求改过几次、为什么改。",
        days=60,
        target="folder",
        shortcut=4,
        builtin=True,
        prompt=(
            "按时间顺序还原需求的变化：最初的要求 → 每一次修改 → 当前的最新版本。\n"
            "对每处变化说明“改了什么、为什么改、谁提出的”，"
            "并指出新旧版本之间互相冲突、或还没有人确认的地方。\n"
            "结尾给出“当前有效版本”的一段完整描述。"
        ),
    ),
)

BUILTIN_BY_ID = {scene.id: scene for scene in BUILTIN_SCENES}
