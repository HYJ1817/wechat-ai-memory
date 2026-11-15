"""Offscreen test and render validation for GlassDashboardWindow."""

import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

from wechat_context_exporter.ui.dashboard_window import GlassDashboardWindow


def pump(app: QApplication, n: int = 40) -> None:
    for _ in range(n):
        app.processEvents()


def test_glass_dashboard_render() -> None:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    app.setOrganizationName("WBGlassDashboardTest")
    app.setApplicationName("WBGlassDashboardTest")

    # Load Microsoft YaHei font
    fid = QFontDatabase.addApplicationFont(r"C:\Windows\Fonts\msyh.ttc")
    if fid != -1:
        fams = QFontDatabase.applicationFontFamilies(fid)
        if fams:
            app.setFont(QFont(fams[0], 10))

    print("1. Instantiating GlassDashboardWindow ...", flush=True)
    demo_path = str(PROJECT_ROOT / "examples" / "demo_chat.json")
    window = GlassDashboardWindow(demo_json=demo_path)
    window.resize(1340, 890)
    window.show()
    print("2. Window shown, pumping events ...", flush=True)

    # Pump event loop so background blur, layout and demo messages load
    pump(app, 60)
    print("3. Pumping complete, saving snapshot ...", flush=True)

    out_dir = PROJECT_ROOT / "outputs"
    out_dir.mkdir(exist_ok=True)
    out_png = out_dir / "glass_dashboard_rendered.png"

    pixmap = window.grab()
    saved = pixmap.save(str(out_png), "PNG")
    print(f"Rendered snapshot saved to: {out_png} (saved={saved}, size={pixmap.size().width()}x{pixmap.size().height()})", flush=True)

    assert saved, "Failed to save dashboard snapshot"
    assert out_png.exists(), "Rendered image does not exist"
    assert out_png.stat().st_size > 50000, f"Rendered image too small: {out_png.stat().st_size} bytes"

    # Assert essential widgets exist and are populated
    assert window.left_card is not None
    assert window.center_card is not None
    assert window.right_card is not None
    assert window.chat_stream is not None
    assert window.media_bar is not None
    assert window.spotlight_card is not None
    assert "ECO 项目讨论群" in window.spotlight_card.lbl_title.text()

    # Test animated toggle switches
    # Export options are checkboxes now (they were animated toggles)
    assert window.switch_image_pages.isChecked() is True
    window.switch_image_pages.setChecked(False)
    assert window.switch_image_pages.isChecked() is False
    window.switch_image_pages.setChecked(True)
    assert window.switch_image_pages.isChecked() is True
    assert window.check_markdown.isChecked() is True
    assert window.check_json.isChecked() is True
    assert window.check_pdf.isEnabled() is False  # PDF is mandatory

    # Export estimate is rendered into the status tile (the ring gauge is gone)
    assert "页" in window.lbl_export_est.text()

    # Test conversation drawer functionality
    assert len(window._conv_widgets) == 2, f"Expected 2 conversation items, found {len(window._conv_widgets)}"
    assert "eco-project" in window._conv_widgets
    assert "mentor-chat" in window._conv_widgets
    assert window._current_cid == "eco-project"
    assert window.lbl_chat_title.text() == "ECO 项目讨论群"
    assert len(window._messages) == 8

    # Test switching conversation to mentor-chat
    print("4. Testing conversation switching to mentor-chat ...", flush=True)
    window._switch_conversation("mentor-chat")
    pump(app, 20)
    assert window._current_cid == "mentor-chat"
    assert window.lbl_chat_title.text() == "导师"
    assert window.lbl_chat_tag.text() == "私聊"
    assert len(window._messages) == 2
    assert len(window._filtered_messages) == 2

    # Test search filter in conversation drawer
    print("5. Testing search filter in conversation drawer ...", flush=True)
    window._filter_conversations("导师")
    assert not window._conv_widgets["eco-project"].isVisible()
    assert window._conv_widgets["mentor-chat"].isVisible()

    window._filter_conversations("")
    assert window._conv_widgets["eco-project"].isVisible()
    assert window._conv_widgets["mentor-chat"].isVisible()

    # Switch back to eco-project
    window._switch_conversation("eco-project")
    pump(app, 20)
    assert window._current_cid == "eco-project"
    assert len(window._filtered_messages) == 8

    print("6. Closing window and app ...", flush=True)
    window.close()
    app.quit()
    print("ALL GLASS DASHBOARD CHECKS PASSED!", flush=True)


if __name__ == "__main__":
    test_glass_dashboard_render()
    sys.exit(0)
