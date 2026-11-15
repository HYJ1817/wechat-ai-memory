from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime, time
from pathlib import Path

from .delivery import (
    TARGETS,
    AgentDelivery,
    ClipboardDelivery,
    DeliveryTarget,
    FolderDelivery,
    ObsidianDelivery,
)
from .jobs import JobStore, default_jobs_dir
from .paths import output_root
from .pipeline import run_export
from .scenes import Scene, SceneError, SceneStore
from .service import ExportOptions
from .sources import JsonChatSource, SourceError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="wechat-context-exporter",
        description=(
            "Build an agent-readable memory archive from a local JSON chat source, "
            "record it as a job, and deliver it where the agent can read it."
        ),
    )
    parser.add_argument("--source", type=Path, help="Path to a version 1 chat JSON file")
    parser.add_argument("--conversation", help="Conversation id; omit to list available conversations")
    parser.add_argument("--output", type=Path, help="Destination PDF path")
    parser.add_argument("--start", type=_parse_start, help="Inclusive ISO 8601 start date/time")
    parser.add_argument("--end", type=_parse_end, help="Inclusive ISO 8601 end date/time")
    parser.add_argument("--no-image-pages", action="store_true", help="Do not insert full-page image attachments")
    parser.add_argument("--pages-dir", type=Path, help="Keep the rendered PNG pages in this directory")
    parser.add_argument("--markdown", type=Path, help="Also write a Markdown transcript")
    parser.add_argument("--json", dest="json_output", type=Path, help="Also write normalized filtered JSON")
    parser.add_argument("--query", help="Only export messages whose sender, content, or type contains this text")

    scenes = parser.add_argument_group("scenes")
    scenes.add_argument("--scene", help="Scene id (see --list-scenes) supplying window, filter, prompt, and target")
    scenes.add_argument("--list-scenes", action="store_true", help="List built-in and custom scenes")

    delivery = parser.add_argument_group("delivery")
    delivery.add_argument(
        "--deliver",
        choices=TARGETS,
        help="Where to send the archive; defaults to the scene's target, then none",
    )
    delivery.add_argument("--deliver-to", type=Path, help="Folder root, or Obsidian vault")
    delivery.add_argument("--agent", help="Application name or exe to activate, e.g. claude")
    delivery.add_argument("--agent-dry-run", action="store_true", help="Copy the prompt but do not activate any app")
    delivery.add_argument("--jobs-dir", type=Path, help="Where job records live (default: %%LOCALAPPDATA%%\\WeChatAIMemory\\jobs)")

    history = parser.add_argument_group("history")
    history.add_argument("--record", action="store_true", help="Record this export as a job even without a scene")
    history.add_argument("--list-jobs", action="store_true", help="List recorded jobs")
    history.add_argument("--prune-jobs", type=int, metavar="DAYS", help="Delete finished jobs older than DAYS")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.list_scenes:
        return _print_scenes()
    if args.list_jobs:
        return _print_jobs(args.jobs_dir)
    if args.prune_jobs is not None:
        return _prune_jobs(args.jobs_dir, args.prune_jobs)

    if not args.source:
        print(
            "error: --source is required unless --list-scenes, --list-jobs, or --prune-jobs is used",
            file=sys.stderr,
        )
        return 2

    try:
        source = JsonChatSource(args.source)
    except SourceError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    try:
        scene = SceneStore().get(args.scene) if args.scene else None
    except SceneError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    conversation_id = args.conversation or (scene.conversation_id if scene else None)
    if not conversation_id:
        _print_conversations(source)
        return 0

    try:
        target, target_name = _resolve_target(args, scene)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    record = args.record or bool(args.scene) or target is not None or args.jobs_dir is not None
    if not record and not args.output:
        print(
            "error: --output is required when --conversation is set "
            f"(默认归档目录是 {output_root()})",
            file=sys.stderr,
        )
        return 2

    store = JobStore(args.jobs_dir or default_jobs_dir()) if record else None
    if store is not None:
        for recovered in store.recover_stale():
            print(f"warning: 上次中断的任务已移入 Failed: {recovered}", file=sys.stderr)

    start, end = args.start, args.end
    if start is None and end is None and scene is not None:
        start, end = scene.window()
    query = args.query if args.query is not None else (scene.query if scene else None)
    include_image_pages = (
        False if args.no_image_pages else (scene.include_image_pages if scene else True)
    )

    options = ExportOptions(
        conversation_id=conversation_id,
        output_pdf=args.output or Path("wechat-memory.pdf"),
        start=start,
        end=end,
        include_image_pages=include_image_pages,
        pages_dir=args.pages_dir,
        markdown_path=args.markdown,
        json_path=args.json_output,
        query=query,
    )

    try:
        result = run_export(
            source,
            options,
            store=store,
            scene=scene,
            target=target,
            progress=_print_progress,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(
        f"Created {result.export.pdf_path} ({result.export.page_count} pages, "
        f"{result.export.message_count} messages, {result.export.image_page_count} image pages)"
    )
    if result.job is not None:
        print(f"Recorded {result.job.job_id} [{result.job.state.status.value}] -> {result.job.directory}")
    if result.delivery is not None:
        print(f"Delivery ({target_name}): {result.delivery.describe()}")
    if result.export.message_count == 0:
        hint = ""
        if scene is not None and scene.days is not None:
            hint = f"；场景「{scene.name}」只看最近 {scene.days} 天"
        print(
            f"warning: 筛选结果为 0 条消息，归档是空的{hint}；可用 --start/--end 指定范围",
            file=sys.stderr,
        )

    if record and args.output:
        try:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(result.export.pdf_path, args.output)
            print(f"Copied PDF -> {args.output}")
        except OSError as exc:
            print(f"warning: 无法复制到 {args.output}: {exc}", file=sys.stderr)
    elif record and (args.markdown or args.json_output):
        print("note: 记录模式下 Markdown/JSON 一并写入任务目录，投递时会一起带走", file=sys.stderr)

    return 0 if result.ok else 1


def _resolve_target(
    args: argparse.Namespace, scene: Scene | None
) -> tuple[DeliveryTarget | None, str]:
    name = args.deliver or (scene.target if scene else "none")
    if name == "none":
        return None, "none"
    if name == "clipboard":
        return ClipboardDelivery(), name
    if name == "folder":
        if not args.deliver_to:
            raise ValueError("--deliver folder requires --deliver-to <目录>")
        return FolderDelivery(args.deliver_to), name
    if name == "obsidian":
        if not args.deliver_to:
            raise ValueError("--deliver obsidian requires --deliver-to <Obsidian vault 路径>")
        return ObsidianDelivery(args.deliver_to), name
    if name == "agent":
        if not args.agent:
            raise ValueError("--deliver agent requires --agent <应用名或 exe>")
        return AgentDelivery(args.agent, dry_run=args.agent_dry_run), name
    raise ValueError(f"unknown delivery target: {name}")


def _print_conversations(source: JsonChatSource) -> None:
    print("Available conversations:")
    for conversation in source.list_conversations():
        count = len(source.get_messages(conversation.id))
        print(f"  {conversation.id}\t{conversation.name}\t{count} messages")


def _print_scenes() -> int:
    store = SceneStore()
    for scene in store.list():
        origin = "builtin" if scene.builtin else "custom"
        shortcut = f"[{scene.shortcut}]" if scene.shortcut else "   "
        print(
            f"{shortcut} {scene.id:<16} {scene.name:<8} "
            f"target={scene.target:<9} {origin:<7} {scene.description}"
        )
    for warning in store.last_warnings:
        print(f"warning: {warning}", file=sys.stderr)
    return 0


def _print_jobs(jobs_dir: Path | None) -> int:
    store = JobStore(jobs_dir or default_jobs_dir())
    records = store.list_jobs()
    if not records:
        print(f"没有记录的任务（{store.root}）")
        return 0
    for record in records:
        print(record.summary())
    print(f"\n{len(records)} 个任务 · {store.root}")
    for warning in store.last_warnings:
        print(f"warning: {warning}", file=sys.stderr)
    return 0


def _prune_jobs(jobs_dir: Path | None, days: int) -> int:
    if days < 0:
        print("error: --prune-jobs 需要一个非负天数", file=sys.stderr)
        return 2
    store = JobStore(jobs_dir or default_jobs_dir())
    removed = store.prune(days)
    print(f"已清理 {len(removed)} 个任务（超过 {days} 天且已结束）")
    for job_id in removed:
        print(f"  {job_id}")
    for warning in store.last_warnings:
        print(f"warning: {warning}", file=sys.stderr)
    return 0


def _parse_datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone().replace(tzinfo=None)
        return parsed
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid ISO 8601 date/time: {value}") from exc


def _parse_start(value: str) -> datetime:
    parsed = _parse_datetime(value)
    return datetime.combine(parsed.date(), time.min) if len(value) == 10 else parsed


def _parse_end(value: str) -> datetime:
    parsed = _parse_datetime(value)
    return datetime.combine(parsed.date(), time.max) if len(value) == 10 else parsed


def _print_progress(current: int, total: int, label: str) -> None:
    print(f"[{current}/{total}] {label}", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
