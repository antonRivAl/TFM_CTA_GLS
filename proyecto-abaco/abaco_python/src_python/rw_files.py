from __future__ import annotations

from pathlib import Path

# =============================================================================
# CORRESPONDENCIA CON CÓDIGO JAVA
# =============================================================================
# Archivo Java:
#   - src/main/rwFiles/Lectura.java
#       → clase Lectura: vector(), listar(), array(), matriz()
#         (métodos de lectura de ficheros de texto/CSV usados por Entrada)
#
# NOTA: Escritura.java y EscrituraExcel.java están implementados directamente
# en __main__.py como _write_solution_txt() y _write_solution_xlsx().
# =============================================================================


def vector(path: str | Path) -> list[float]:
    first_line = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()[0]
    return [float(item) for item in first_line.split(" ") if item]


def listar(path: str | Path, opcional: bool = False) -> list[str]:
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        if opcional:
            return []
        raise


def array(path: str | Path) -> list[list[float]]:
    col1: list[float] = []
    col2: list[float] = []
    for line in listar(path):
        if not line:
            continue
        left, right = line.split(";")[:2]
        col1.append(float(left))
        col2.append(float(right))
    return [col1, col2]


def matriz(path: str | Path) -> list[list[float]]:
    rows: list[list[float]] = []
    for line in listar(path):
        if line:
            rows.append([float(item) for item in line.split(" ") if item])
    return rows


class Lectura:
    Vector = staticmethod(vector)
    Listar = staticmethod(listar)
    array = staticmethod(array)
    Matriz = staticmethod(matriz)

