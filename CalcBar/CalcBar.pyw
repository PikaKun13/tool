"""ダブルクリックで起動するための入口（.pyw なので黒いコンソール画面は出ない）。"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from calcbar.ui import main   # noqa: E402

if __name__ == "__main__":
    main()
