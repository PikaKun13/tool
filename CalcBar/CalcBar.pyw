"""双击运行的入口（.pyw 不会弹黑框）。"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from calcbar.ui import main   # noqa: E402

if __name__ == "__main__":
    main()
