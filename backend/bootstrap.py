from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

REQUIRED_IMPORTS = (
    "flask",
    "flask_cors",
    "flask_sqlalchemy",
    "sqlalchemy",
    "psycopg",
    "flask_migrate",
    "alembic",
    "pydantic",
    "email_validator",
    "numpy",
    "pandas",
    "sklearn",
    "dotenv",
    "pytest",
)

GET_PIP_URL = "https://bootstrap.pypa.io/get-pip.py"


def can_import_all(python_bin: str) -> bool:
    if not Path(python_bin).exists() and python_bin != sys.executable:
        return False
    check_code = "import " + ", ".join(REQUIRED_IMPORTS)
    result = subprocess.run(
        [python_bin, "-c", check_code],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def ensure_venv(venv_dir: Path) -> Path:
    venv_python = venv_dir / "bin" / "python"
    if venv_python.exists():
        return venv_python

    print(f"[bootstrap] Creating Python virtual environment at {venv_dir}...", flush=True)
    res = subprocess.run(
        [sys.executable, "-m", "venv", str(venv_dir)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    if res.returncode != 0:
        print(
            "[bootstrap] Standard venv creation failed (likely missing ensurepip); retrying with --without-pip...",
            flush=True,
        )
        subprocess.run(
            [sys.executable, "-m", "venv", "--clear", "--without-pip", str(venv_dir)],
            check=True,
        )
    return venv_python


def ensure_pip(venv_python: Path) -> None:
    pip_check = subprocess.run(
        [str(venv_python), "-m", "pip", "--version"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if pip_check.returncode == 0:
        return

    print("[bootstrap] pip missing in virtualenv; bootstrapping via get-pip.py...", flush=True)
    with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        urllib.request.urlretrieve(GET_PIP_URL, tmp_path)
        subprocess.run(
            [str(venv_python), tmp_path, "--no-cache-dir", "--no-warn-script-location"],
            check=True,
        )
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass


def main() -> int:
    backend_dir = Path(__file__).resolve().parent
    venv_dir = backend_dir / ".venv"
    requirements_file = backend_dir / "requirements.txt"

    venv_python = venv_dir / "bin" / "python"
    if venv_python.exists() and can_import_all(str(venv_python)):
        return 0

    venv_python = ensure_venv(venv_dir)
    if can_import_all(str(venv_python)):
        return 0

    ensure_pip(venv_python)

    print(f"[bootstrap] Installing Python dependencies from {requirements_file}...", flush=True)
    subprocess.run(
        [
            str(venv_python),
            "-m",
            "pip",
            "install",
            "--no-cache-dir",
            "--disable-pip-version-check",
            "-r",
            str(requirements_file),
        ],
        check=True,
    )

    if not can_import_all(str(venv_python)):
        raise RuntimeError("Python dependencies installed, but required imports still failed.")

    print("[bootstrap] Python backend environment is ready.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
