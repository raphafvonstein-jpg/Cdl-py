"""Ponto de entrada independente para evitar instâncias antigas do Streamlit."""

from pathlib import Path


codigo = Path(__file__).with_name("app.py").read_text(encoding="utf-8")
exec(compile(codigo, "app.py", "exec"))
