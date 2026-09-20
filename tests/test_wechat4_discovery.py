from __future__ import annotations

from pathlib import Path

from wechat_context_exporter.sources import wechat4_discovery


def test_discovery_skips_unavailable_root_and_finds_other_account(tmp_path, monkeypatch) -> None:
    unavailable = tmp_path / "unavailable" / "xwechat_files"
    available = tmp_path / "available" / "xwechat_files"
    account = available / "wxid_test"
    session = account / "db_storage" / "session" / "session.db"
    session.parent.mkdir(parents=True)
    session.touch()

    monkeypatch.setattr(wechat4_discovery, "_candidate_xwechat_roots", lambda: [unavailable, available])
    original_is_dir = Path.is_dir

    def is_dir(path: Path) -> bool:
        if path == unavailable:
            raise OSError(31, "A device attached to the system is not functioning")
        return original_is_dir(path)

    monkeypatch.setattr(Path, "is_dir", is_dir)

    accounts = wechat4_discovery.discover_wechat4_accounts()

    assert [entry.account_dir for entry in accounts] == [account]


def test_candidate_scan_skips_unavailable_drive_directory(monkeypatch) -> None:
    drive = Path("K:/")
    unavailable = drive / "115open"
    original_is_dir = Path.is_dir

    monkeypatch.setattr(Path, "exists", lambda path: path == drive)
    monkeypatch.setattr(Path, "iterdir", lambda path: iter([unavailable]))

    def is_dir(path: Path) -> bool:
        if path == unavailable:
            raise OSError(31, "A device attached to the system is not functioning")
        return original_is_dir(path)

    monkeypatch.setattr(Path, "is_dir", is_dir)

    assert drive / "xwechat_files" in wechat4_discovery._candidate_xwechat_roots()


def test_discovery_skips_unavailable_account_directory(tmp_path, monkeypatch) -> None:
    root = tmp_path / "xwechat_files"
    unavailable = root / "wxid_unavailable"
    available = root / "wxid_test"
    session = available / "db_storage" / "session" / "session.db"
    session.parent.mkdir(parents=True)
    session.touch()
    unavailable.mkdir()

    monkeypatch.setattr(wechat4_discovery, "_candidate_xwechat_roots", lambda: [root])
    original_is_dir = Path.is_dir

    def is_dir(path: Path) -> bool:
        if path == unavailable:
            raise OSError(31, "A device attached to the system is not functioning")
        return original_is_dir(path)

    monkeypatch.setattr(Path, "is_dir", is_dir)

    accounts = wechat4_discovery.discover_wechat4_accounts()

    assert [entry.account_dir for entry in accounts] == [available]
