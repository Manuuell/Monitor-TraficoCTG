#!/usr/bin/env python3
"""Ejecuta el chequeo programado de Google usado por el panel admin."""
from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "dashboard"))

import admin_services  # noqa: E402


def main() -> int:
    estado = admin_services.actualizar_estado_google()
    google = estado["google"]
    sheets = estado["sheets"]
    print(
        f"[{estado['actualizado']}] Google={google.get('estado', 'Desconocido')} "
        f"Sheets={'Activo' if sheets.get('ok') else 'Error'} "
        f"Partes={len(sheets.get('partes', []))}"
    )
    return 0 if google.get("ok") and sheets.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
