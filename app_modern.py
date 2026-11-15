"""Source-tree launcher kept for ``start_modern.cmd`` / ``start_modern.vbs``.

The real logic lives in ``wechat_context_exporter.ui.launch`` so that the
packaged entry point (``app.py``) and this one cannot drift apart.  The window
is chosen there, not here.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from wechat_context_exporter.ui.launch import main  # noqa: E402


if __name__ == "__main__":
    sys.exit(main())
