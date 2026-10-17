"""Root entrypoint executing EvalMatrix CLI."""

import sys
from pathlib import Path

# Ensure src is on sys.path for direct invocation
src_dir = Path(__file__).resolve().parent / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from evalmatrix.main import app, main

if __name__ == "__main__":
    main()
