"""The instruction that travels with an archive.

A file path is not a briefing.  WeChatBridge learned this the hard way: pasting
a ZIP into an agent gets a summary of the ZIP, not an answer to the question the
user actually had.  So every scene carries a prompt, and the rendered prompt
always opens with the archive paths, the conversation, the window, and the job
id -- enough for the agent to reason about *scope* before it reasons about
content.
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from ..jobs.models import JobManifest, window_text
from .models import Scene

DEFAULT_TASK = "请通读这份归档，围绕「{scene_name}」输出结构化结果。"

CITATION_RULE = (
    "引用规范：每条结论后面用 [消息ID] 标注出处（例如 [m006]）；"
    "归档里找不到依据的内容写「归档中未提及」，不要推测或补写。"
)

_NO_FILES = "（无归档文件，仅按下述要求处理）"


class _Placeholders(dict):
    """Leave unknown placeholders untouched instead of failing the export."""

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def render_prompt(
    scene: Scene,
    manifest: JobManifest,
    files: Sequence[str | Path] = (),
    *,
    extra: str | None = None,
) -> str:
    """Build the text to paste into an agent, or to save next to the archive."""
    paths = [str(Path(item).expanduser().resolve()) for item in files]
    files_text = "\n".join(paths) if paths else _NO_FILES

    lines = [f"【归档】{paths[0] if paths else _NO_FILES}"]
    for extra_path in paths[1:]:
        lines.append(f"　　　　{extra_path}")
    lines.append(f"【会话】{manifest.conversation_name}（{manifest.conversation_id}）")
    window = window_text(manifest)
    scope = f"【时间窗】{window}　【消息数】{manifest.message_count}"
    if manifest.query:
        scope += f"　【关键词】{manifest.query}"
    lines.append(scope)
    lines.append(f"【任务号】{manifest.job_id}")

    body = (scene.prompt or DEFAULT_TASK).strip()
    values = _Placeholders(
        {
            "scene_name": scene.name,
            "scene_description": scene.description,
            "conversation": manifest.conversation_name,
            "conversation_id": manifest.conversation_id,
            "start": manifest.start.strftime("%Y-%m-%d") if manifest.start else "",
            "end": manifest.end.strftime("%Y-%m-%d") if manifest.end else "",
            "message_count": str(manifest.message_count),
            "query": manifest.query or "",
            "job_id": manifest.job_id,
            "files": files_text,
        }
    )
    try:
        body = body.format_map(values)
    except (IndexError, ValueError):
        pass

    blocks = ["\n".join(lines), body]
    if extra and extra.strip():
        blocks.append(extra.strip())
    blocks.append(CITATION_RULE)
    return "\n\n".join(block for block in blocks if block)
