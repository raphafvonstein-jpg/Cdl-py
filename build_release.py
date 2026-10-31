"""Empacota somente o aplicativo LSV Python, sem dados e sem arquivos legados."""
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parent


def build():
    paths = [ROOT / name for name in ['app.py', 'requirements.txt', 'README.md', 'build_release.py', '.gitignore', '.streamlit/config.toml']]
    for folder in ['lsv_app', 'tests', 'examples']:
        paths.extend(path for path in (ROOT / folder).rglob('*') if path.is_file() and '__pycache__' not in path.parts and path.suffix in ('.py', '.json'))
    output = ROOT / 'dist' / 'lsv-streamlit.zip'
    output.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(paths):
            archive.write(path, path.relative_to(ROOT).as_posix())
    with zipfile.ZipFile(output) as archive:
        assert archive.testzip() is None
        assert all(not name.startswith(('LSV/', 'Cdl/', '.cache/', '.venv/')) for name in archive.namelist())
    print(output)
    return output


if __name__ == '__main__':
    build()
