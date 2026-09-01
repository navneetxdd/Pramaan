# -*- mode: python ; coding: utf-8 -*-
"""Build the Pramaan API as the single-file Tauri sidecar."""

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ENGINE_ROOT = Path(SPECPATH).resolve()
PROJECT_ROOT = ENGINE_ROOT.parent
PARSER_ROOT = ENGINE_ROOT / "app" / "parsers"
VALIDATION_ROOT = PROJECT_ROOT / "validation_data"


def existing_data_files():
    """Return runtime data in a stable order without packaging operator evidence."""
    files = []

    for source in sorted(PARSER_ROOT.glob("*.json")):
        files.append((str(source), "engine/app/parsers"))

    manifest = VALIDATION_ROOT / "manifest.json"
    if manifest.is_file():
        files.append((str(manifest), "validation_data"))

    models = VALIDATION_ROOT / "models"
    if models.is_dir():
        for source in sorted(path for path in models.rglob("*") if path.is_file()):
            destination = Path("validation_data/models") / source.parent.relative_to(models)
            files.append((str(source), destination.as_posix()))

    return files


a = Analysis(
    [str(PROJECT_ROOT / "run.py")],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=existing_data_files(),
    hiddenimports=sorted(collect_submodules("engine.app")),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["engine.tests", "pytest", "unittest"],
    noarchive=False,
    optimize=1,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="pramaan-engine",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)
