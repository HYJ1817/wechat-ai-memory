"""Application entry point -- and the PyInstaller entry script.

Both packaging specs build from THIS file, so everything that must ship has to
be reachable from its import graph.  The real launch logic lives in
``wechat_context_exporter.ui.launch``, which imports both the classic and the
glass windows; do not reduce this to a conditional import of a single window,
or the glass dashboard will silently drop out of the built exe again.
"""

from pathlib import Path
import subprocess
import sys


project_dir = Path(__file__).resolve().parent
project_python = project_dir / ".venv-gui" / "Scripts" / "python.exe"
if project_python.is_file() and Path(sys.executable).resolve() != project_python.resolve():
    raise SystemExit(
        subprocess.call(
            [str(project_python), str(Path(__file__).resolve()), *sys.argv[1:]],
            cwd=project_dir,
        )
    )

src_dir = project_dir / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from wechat_context_exporter.ui.launch import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
