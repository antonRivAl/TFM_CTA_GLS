from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from .entrada import Entrada
from .fitness import switch_fitness
from .initial_population import inicializar_poblacion
from .models import Controlador, Propiedades, Solucion, Turno
from .parameters import Parametros, ParametrosAlgoritmo
from .restrictions import penalizacion_por_restricciones, restricciones_sin_pesos
from .simulated_annealing import bucle_sa
from .GLS import bucle_gls


# =============================================================================
# CORRESPONDENCIA CON CÓDIGO JAVA
# =============================================================================
# Archivo Java principal:
#   - src/main/main/Main.java          → orquestación general (lectura, flujo SA/VNS)
#   - src/main/main/Main_SA.java       → lanzamiento del bucle SA y report de resultados
#
# Funciones de escritura de resultados (al final del archivo):
#   - src/main/rwFiles/Escritura.java       → _write_solution_txt()
#   - src/main/rwFiles/EscrituraExcel.java  → _write_solution_xlsx()
# =============================================================================


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="abaco_py")
    parser.add_argument("--repo", default=_default_repo(), help="Path to proyecto-abaco")
    subparsers = parser.add_subparsers(dest="command", required=True)

    native_parser = subparsers.add_parser("run-sa", help="Run the native Python SA solver (Phases 2+3 with SA)")
    native_parser.add_argument("--case", choices=["madN_M1", "madN_M2", "both"], default="madN_M1")
    native_parser.add_argument("--max-seconds", type=float, default=None)
    native_parser.add_argument("--max-iterations", type=int, default=None)
    native_parser.add_argument("--seed", type=int, default=1234)
    native_parser.add_argument("--prueba", default="P0")

    gls_parser = subparsers.add_parser("run-gls", help="Run GLS (Phase 2 y 3)")
    gls_parser.add_argument("--case", choices=["madN_M1", "madN_M2", "both"], default="madN_M1")
    gls_parser.add_argument("--max-seconds-sa",  type=float, default=None, help="Max seconds for SA Phase 2 (None = use algorithm.properties)")
    gls_parser.add_argument("--max-seconds-gls", "--max-seconds-sls", type=float, default=None, help="Max seconds for GLS Phase 3 (None = use algorithm.properties)", dest="max_seconds_gls")
    gls_parser.add_argument("--max-iterations",  type=int,   default=None)
    gls_parser.add_argument("--seed",            type=int,   default=1234)
    gls_parser.add_argument("--prueba",      default="P0")
    # Los parámetros GLS (λ, patience, condiciones de parada, etc.) se leen
    # de la sección [GLS] de algorithm.properties.  Ver GLSParameters en parameters.py.

    native_check = subparsers.add_parser("check", help="Run native Python checks without Java")
    native_check.add_argument("--max-seconds", type=float, default=3.0)
    native_check.add_argument("--max-iterations", type=int, default=20)

    args = parser.parse_args(argv)
    repo = Path(args.repo).resolve()

    if args.command == "run-sa":
        return _run_sa(repo, args)
    if args.command == "run-gls":
        return _run_gls(repo, args)
    if args.command == "check":
        return _check_native(repo, args.max_seconds, args.max_iterations)
    return 2


def _default_repo() -> str:
    return str(Path(__file__).resolve().parents[2])


def _self_check_models(repo: Path) -> int:
    algorithm = ParametrosAlgoritmo.from_file(repo / "resources" / "algorithm.properties")
    problem = Parametros.from_files(repo / "resources" / "problemParameters.properties", repo / "resources" / "options.properties")

    controller = Controlador(1, "Manana", "Madrid", True, False, False, Propiedades.ALTA, 0, 0)
    solution = Solucion(["AAA111"], [controller], 2)
    clone = solution.clone()
    clone.controladores[0].setTurnoAsignado(3)
    if solution.controladores[0].getTurnoAsignado() == clone.controladores[0].getTurnoAsignado():
        print("Python clone check failed.", file=sys.stderr)
        return 1

    turno_slots = Turno.turnos_slots("10:30", "18:30", "12:30", "18:30", problem)
    if turno_slots != [0, 96, 24, 96]:
        print(f"Turno slot check failed: {turno_slots}", file=sys.stderr)
        return 1

    summary = {
        "python": {
            "algorithm": algorithm.getAlgoritmo(),
            "max_milliseconds": algorithm.getMaxMilisecondsAllowed(),
            "fitness_weights": [
                algorithm.getPonderacionFitness1(),
                algorithm.getPonderacionFitness2(),
                algorithm.getPonderacionFitness3(),
                algorithm.getPonderacionFitness4(),
            ],
            "slot_size": problem.getTamanoSlots(),
            "turno_slots_sample": turno_slots,
            "model_clone": "ok",
        }
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


def _load_defaults(repo: Path):
    algorithm = ParametrosAlgoritmo.from_file(repo / "resources" / "algorithm.properties")
    problem = Parametros.from_files(repo / "resources" / "problemParameters.properties", repo / "resources" / "options.properties")
    return algorithm, problem


def _case_specs(case: str):
    specs = {
        "madN_M1": ("madN_M1", "madN_M1-2019-02-12", "Madrid"),
        "madN_M2": ("madN_M2", "madN_M2-2019-02-16", "Madrid"),
    }
    if case == "both":
        return list(specs.values())
    return [specs[case]]


def _run_sa(repo: Path, args) -> int:
    output_dir = Path(args.output_dir).resolve() if args.output_dir else Path(__file__).resolve().parents[1] / "resultados_py"
    output_dir.mkdir(parents=True, exist_ok=True)
    summaries = []
    for idx, (case_path, entrada_id, entorno) in enumerate(_case_specs(args.case)):
        algorithm, problem = _load_defaults(repo)
        algorithm.algoritmo = "SA"
        entrada = Entrada.leer_entrada(repo, problem, case_path, entrada_id, entorno, estudio_estadillos=True)
        # AQUI EMPIEZA LA FASE 1 (Heurística de Inicialización)
        poblacion = inicializar_poblacion(entrada, problem)
        
        # AQUI EMPIEZA LA FASE 2 Y FASE 3 (el SA las cubre ambas automáticamente:
        # Fase 2: c_req < tmn  → factibilización, eliminar controladores imaginarios
        # Fase 3 y c_req >= tmn → optimización, mejorar calidad. Transición automática en fitness.py)
        soluciones = bucle_sa(
            poblacion,
            algorithm,
            problem,
            entrada,
            seed=args.seed + idx if args.seed is not None else None,
            max_seconds=args.max_seconds,
            max_iterations=args.max_iterations,
        )
        all_solutions = [entrada.getDistribucionInicial(), *poblacion, *soluciones]
        case_dir = output_dir / f"{case_path}_{entrada_id}"
        case_dir.mkdir(parents=True, exist_ok=True)
        for sol_idx, sol in enumerate(all_solutions, start=1):
            _write_solution_txt(case_dir / f"solucion{sol_idx}.txt", sol)
            _write_solution_xlsx(case_dir / f"solucion{sol_idx}.xlsx", sol)
        best = soluciones[-1] if soluciones else poblacion[-1]
        summary = {
            "case": case_path,
            "entrada_id": entrada_id,
            "solutions_written": len(all_solutions),
            "output": str(case_dir),
            "fitnessF2": switch_fitness(best, entrada, problem, algorithm, fase=2),
            "fitnessF3": switch_fitness(best, entrada, problem, algorithm, fase=3),
            "weighted_restrictions": penalizacion_por_restricciones(best, entrada, problem),
            "raw_restrictions": restricciones_sin_pesos(best, entrada, problem),
        }
        summaries.append(summary)
        print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


def _run_gls(repo: Path, args) -> int:
    """Ejecuta GLS para las fases 2 y 3.

    Los parámetros del algoritmo GLS (λ, patience, condiciones de parada, etc.)
    se leen de la sección GLS de algorithm.properties a través de GLSParameters.
    Solo se pueden sobreescribir por CLI el tiempo máximo y las iteraciones máximas.
    """
    idx_prueba = args.prueba
    output_dir = Path(__file__).resolve().parents[1] / "resultados_py"
    output_dir.mkdir(parents=True, exist_ok=True)
    summaries = []

    for idx, (case_path, entrada_id, entorno) in enumerate(_case_specs(args.case)):
        algorithm, problem = _load_defaults(repo)
        algorithm.algoritmo = "SA"
        entrada = Entrada.leer_entrada(
            repo, problem, case_path, entrada_id, entorno, estudio_estadillos=True
        )
        seed = args.seed + idx if args.seed is not None else None

        # AQUI EMPIEZA LA FASE 1 (Heurística de Inicialización)
        poblacion = inicializar_poblacion(entrada, problem)

        soluciones_fase3 = bucle_gls(
            poblacion,
            algorithm,
            problem,
            entrada,
            seed=seed,
            max_seconds=args.max_seconds_gls,
            max_iterations=args.max_iterations,
            idx_prueba=idx_prueba,
        )

        all_solutions = [
            entrada.getDistribucionInicial(),
            *poblacion,
            *soluciones_fase3,
        ]
        case_dir = output_dir / f"GLS_{case_path}_{entrada_id}_{idx_prueba}"
        case_dir.mkdir(parents=True, exist_ok=True)
        for sol_idx, sol in enumerate(all_solutions, start=1):
            _write_solution_txt(case_dir / f"solucion{sol_idx}.txt", sol)
            _write_solution_xlsx(case_dir / f"solucion{sol_idx}.xlsx", sol)

        best = soluciones_fase3[-1] if soluciones_fase3 else poblacion[-1]
        
        summary = {
            "case": case_path,
            "entrada_id": entrada_id,
            "mode": "GLS(F2 y F3)",
            "gls_lambda": algorithm.GLS.getLambda(),
            "gls_p_move4": algorithm.GLS.getPorcentajeMovDiversificacion(),
            "gls_patience": algorithm.GLS.getPatience(),
            "solutions_written": len(all_solutions),
            "output": str(case_dir),
            "fitnessF2": switch_fitness(best, entrada, problem, algorithm, fase=2),
            "weighted_restrictions": penalizacion_por_restricciones(best, entrada, problem),
            "raw_restrictions": restricciones_sin_pesos(best, entrada, problem),
        }
        summaries.append(summary)
        print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


def _write_solution_txt(path: Path, solution: Solucion) -> None:
    lines = ["# turnos"]
    lines.extend(solution.getTurnos())
    lines.append("# controladores")
    for controlador in solution.getControladores():
        lines.append(
            f"id={controlador.id};turno={controlador.turno};nucleo={controlador.nucleo};"
            f"PTD={controlador.ptd};CON={controlador.con};turnoAsignado={controlador.turno_asignado};"
            f"imaginario={controlador.imaginario}"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_solution_xlsx(path: Path, solution: Solucion) -> None:
    try:
        from openpyxl import Workbook
    except ImportError:
        return

    wb = Workbook()
    ws = wb.active
    ws.title = "Turnos"
    ws.append(["turno_index", "slot_index", "valor"])
    for turno_idx, turno in enumerate(solution.getTurnos()):
        for slot_idx in range(0, len(turno), 3):
            ws.append([turno_idx, slot_idx // 3, turno[slot_idx : slot_idx + 3]])

    ws_ctrl = wb.create_sheet("Controladores")
    ws_ctrl.append(["id", "turno", "nucleo", "PTD", "CON", "turnoAsignado", "imaginario", "bajaAlta", "slotAlta", "slotBaja"])
    for controlador in solution.getControladores():
        ws_ctrl.append([
            controlador.id,
            controlador.turno,
            controlador.nucleo,
            controlador.ptd,
            controlador.con,
            controlador.turno_asignado,
            controlador.imaginario,
            controlador.baja_alta.value,
            controlador.slot_alta,
            controlador.slot_baja,
        ])
    wb.save(path)


def _check_native(repo: Path, max_seconds: float, max_iterations: int) -> int:
    class Args:
        case = "madN_M1"
        output_dir = str(Path(__file__).resolve().parents[1] / "resultados_py" / "_check_native")
        seed = 1234

    args = Args()
    args.max_seconds = max_seconds
    args.max_iterations = max_iterations
    return _run_sa(repo, args)


if __name__ == "__main__":
    raise SystemExit(main())
