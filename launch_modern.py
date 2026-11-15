"""
Quick launcher for modern UI with startup info.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

if __name__ == "__main__":
    print("=" * 60)
    print("微信 AI 记忆库 - 现代化 UI")
    print("=" * 60)
    print()
    print("🎨 设计特性:")
    print("  • 暖色渐变背景（米色→浅橙色）")
    print("  • 半透明毛玻璃卡片")
    print("  • 大圆角设计（12-16px）")
    print("  • 橙色渐变主按钮")
    print("  • 智能家居风格")
    print()
    print("💡 提示:")
    print("  • 如需切换回经典版，运行: python app.py")
    print("  • 样式文件: src/wechat_context_exporter/ui/modern_styles.py")
    print()
    print("🚀 正在启动...")
    print("=" * 60)
    print()

    # Import and launch
    from app_modern import main
    sys.exit(main())
