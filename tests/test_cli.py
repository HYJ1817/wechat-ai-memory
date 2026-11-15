from __future__ import annotations

from wechat_context_exporter.cli import main
from wechat_context_exporter.sources import JsonChatSource


def test_cli_lists_conversations(capsys):
    assert main(["--source", "examples/demo_chat.json"]) == 0
    captured = capsys.readouterr()
    assert "eco-project" in captured.out
    assert "8 messages" in captured.out


def test_cli_exports_filtered_roundtrip_json(tmp_path):
    output = tmp_path / "filtered.pdf"
    normalized = tmp_path / "filtered.json"

    result = main(
        [
            "--source",
            "examples/demo_chat.json",
            "--conversation",
            "eco-project",
            "--query",
            "随机种子",
            "--output",
            str(output),
            "--json",
            str(normalized),
        ]
    )

    assert result == 0
    assert output.is_file()
    messages = JsonChatSource(normalized).get_messages("eco-project")
    assert [message.id for message in messages] == ["m006"]


def test_cli_rejects_reversed_date_range(tmp_path, capsys):
    result = main(
        [
            "--source",
            "examples/demo_chat.json",
            "--conversation",
            "eco-project",
            "--start",
            "2026-08-22",
            "--end",
            "2026-08-21",
            "--output",
            str(tmp_path / "invalid.pdf"),
        ]
    )

    assert result == 1
    assert "must not be after" in capsys.readouterr().err


def test_cli_lists_builtin_scenes(capsys):
    assert main(["--list-scenes"]) == 0
    out = capsys.readouterr().out
    assert "group-digest" in out
    assert "项目决策复盘" in out


def test_cli_scene_exports_delivers_and_records(tmp_path, capsys):
    jobs_dir = tmp_path / "jobs"
    out_dir = tmp_path / "out"

    result = main(
        [
            "--source",
            "examples/demo_chat.json",
            "--conversation",
            "eco-project",
            "--scene",
            "group-digest",
            "--start",
            "2026-08-01",
            "--end",
            "2026-08-31",
            "--deliver",
            "folder",
            "--deliver-to",
            str(out_dir),
            "--jobs-dir",
            str(jobs_dir),
        ]
    )

    assert result == 0
    printed = capsys.readouterr().out
    assert "Recorded" in printed
    assert "已投递" in printed

    job_dir = next((jobs_dir / "Ready").iterdir())
    assert (job_dir / "manifest.json").is_file()
    assert (job_dir / "state.json").is_file()
    assert list((job_dir / "files").glob("*.pdf"))
    assert (out_dir / "2026-11-15 ECO 项目讨论群" / "ECO 项目讨论群.pdf").is_file()
    assert (out_dir / "2026-11-15 ECO 项目讨论群" / "给 Agent 的提示词.txt").is_file()

    assert main(["--list-jobs", "--jobs-dir", str(jobs_dir)]) == 0
    listed = capsys.readouterr().out
    assert job_dir.name in listed
    assert "delivered" in listed


def test_cli_list_jobs_when_nothing_was_recorded(tmp_path, capsys):
    assert main(["--list-jobs", "--jobs-dir", str(tmp_path / "empty")]) == 0
    assert "没有记录的任务" in capsys.readouterr().out


def test_cli_requires_output_without_recording(tmp_path, capsys):
    result = main(
        [
            "--source",
            "examples/demo_chat.json",
            "--conversation",
            "eco-project",
        ]
    )

    assert result == 2
    assert "--output is required" in capsys.readouterr().err


def test_cli_reports_a_missing_delivery_destination(tmp_path, capsys):
    result = main(
        [
            "--source",
            "examples/demo_chat.json",
            "--conversation",
            "eco-project",
            "--scene",
            "group-digest",
            "--deliver",
            "obsidian",
            "--jobs-dir",
            str(tmp_path / "jobs"),
        ]
    )

    assert result == 2
    assert "--deliver-to" in capsys.readouterr().err


def test_cli_lists_builtin_scenes(capsys):
    assert main(["--list-scenes"]) == 0
    out = capsys.readouterr().out
    assert "group-digest" in out
    assert "项目决策复盘" in out


def test_cli_scene_exports_delivers_and_records(tmp_path, capsys):
    jobs_dir = tmp_path / "jobs"
    out_dir = tmp_path / "out"

    result = main(
        [
            "--source",
            "examples/demo_chat.json",
            "--conversation",
            "eco-project",
            "--scene",
            "group-digest",
            "--start",
            "2026-08-01",
            "--end",
            "2026-08-31",
            "--deliver",
            "folder",
            "--deliver-to",
            str(out_dir),
            "--jobs-dir",
            str(jobs_dir),
        ]
    )

    assert result == 0
    printed = capsys.readouterr().out
    assert "Recorded" in printed
    assert "已投递" in printed

    job_dir = next((jobs_dir / "Ready").iterdir())
    assert (job_dir / "manifest.json").is_file()
    assert (job_dir / "state.json").is_file()
    assert list((job_dir / "files").glob("*.pdf"))
    assert (out_dir / "2026-11-15 ECO 项目讨论群" / "ECO 项目讨论群.pdf").is_file()
    assert (out_dir / "2026-11-15 ECO 项目讨论群" / "给 Agent 的提示词.txt").is_file()

    assert main(["--list-jobs", "--jobs-dir", str(jobs_dir)]) == 0
    listed = capsys.readouterr().out
    assert job_dir.name in listed
    assert "delivered" in listed


def test_cli_list_jobs_when_nothing_was_recorded(tmp_path, capsys):
    assert main(["--list-jobs", "--jobs-dir", str(tmp_path / "empty")]) == 0
    assert "没有记录的任务" in capsys.readouterr().out


def test_cli_requires_output_without_recording(tmp_path, capsys):
    result = main(
        [
            "--source",
            "examples/demo_chat.json",
            "--conversation",
            "eco-project",
        ]
    )

    assert result == 2
    assert "--output is required" in capsys.readouterr().err


def test_cli_reports_a_missing_delivery_destination(tmp_path, capsys):
    result = main(
        [
            "--source",
            "examples/demo_chat.json",
            "--conversation",
            "eco-project",
            "--scene",
            "group-digest",
            "--deliver",
            "obsidian",
            "--jobs-dir",
            str(tmp_path / "jobs"),
        ]
    )

    assert result == 2
    assert "--deliver-to" in capsys.readouterr().err
