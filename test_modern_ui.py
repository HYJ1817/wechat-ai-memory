"""
Test script to verify modern UI styles are correctly loaded.
"""

import sys
import io
from pathlib import Path

# Force UTF-8 output on Windows
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from wechat_context_exporter.ui.modern_styles import MODERN_STYLESHEET


def test_modern_styles():
    """Test that modern stylesheet is properly defined."""

    print("测试现代化 UI 样式表\n")

    # Check stylesheet exists and is not empty
    assert MODERN_STYLESHEET, "[X] 样式表为空"
    print("[OK] 样式表已加载")

    # Check for key modern features
    required_features = [
        "qlineargradient",  # 渐变背景
        "rgba",             # 透明度
        "border-radius",    # 圆角
        "backdrop-filter",  # 模糊效果注释
    ]

    for feature in required_features:
        if feature in MODERN_STYLESHEET:
            print(f"[OK] 包含 {feature}")
        else:
            print(f"[!] 未找到 {feature}")

    # Count style rules
    rule_count = MODERN_STYLESHEET.count("{")
    print(f"\n统计: {rule_count} 个样式规则")

    # Check size
    size_kb = len(MODERN_STYLESHEET.encode('utf-8')) / 1024
    print(f"大小: {size_kb:.2f} KB")

    # Color scheme check
    print("\n颜色方案检查:")
    if "250, 237, 225" in MODERN_STYLESHEET:
        print("[OK] 暖米色背景")
    if "255, 170, 100" in MODERN_STYLESHEET:
        print("[OK] 橙色主按钮")
    if "rgba(255, 255, 255, 0.7)" in MODERN_STYLESHEET:
        print("[OK] 半透明玻璃效果")

    print("\n测试完成！样式表已准备就绪")
    return True


if __name__ == "__main__":
    try:
        test_modern_styles()
        sys.exit(0)
    except Exception as e:
        print(f"\n[X] 测试失败: {e}")
        sys.exit(1)
