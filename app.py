"""Entrada compatível com o pacote na raiz ou na pasta LSV_activity."""
import sys
from pathlib import Path

root = Path(__file__).resolve().parent
package_root = root if (root / 'lsv_app').is_dir() else root / 'LSV_activity'
if not (package_root / 'lsv_app' / 'ui.py').is_file():
    raise RuntimeError(
        'A pasta lsv_app não foi encontrada. Publique a pasta completa junto do app.py '
        'ou configure Main file path como LSV_activity/app.py.'
    )
if str(package_root) not in sys.path:
    sys.path.insert(0, str(package_root))

from lsv_app.ui import main

main()
