"""GLS – Fase 3: Optimización mediante Guided Local Search (GLS).
"""

from __future__ import annotations

import time
import csv
import os

from .. import move15, move4, move6, restrictions
from . import move_sector_repair
from ..fitness import switch_fitness
from ..java_random import JavaRandom
from ..metaheuristic import order_by_lazy_criteria
from .violation_patterns_v2 import (
    TipoRestriccion,
    compute_penalty_sum,
    get_highest_utility_patterns,
    increment_penalties,
    increment_all_active_penalties,
)

from ..restrictions import penalizacion_por_restricciones, restricciones_sin_pesos, comprobar_restricciones_en_paralelo, _checks


# ---------------------------------------------------------------------------
# Registro de soluciones en las que se estancó el algoritmo
# ---------------------------------------------------------------------------
# Estado por individuo: (fase, ind_idx) -> {"count": int, "last_iter": int}
_optimum_state: dict = {}

_LOG_MAX_ENTRIES   = 20       # Máximo de entradas por archivo
_LOG_MIN_ITER_GAP  = 100_000  # Iteraciones mínimas entre registros


def _log_local_optimum(
    t,
    fase: int,
    idx: int,
    iteracion: int,
    g_actual: float,
    h_actual: float,
) -> None:
    """Añade una entrada al archivo de óptimos locales del individuo actual.

    Sobrescribe siempre el mismo archivo (modo 'a'), con el formato:

        === Iteracion X, g = X.XXXXXX, h = X.XXXXXX ===
        C00: ...
        C01: ...

    Limitaciones:
        - Máximo _LOG_MAX_ENTRIES entradas por archivo.
        - Al menos _LOG_MIN_ITER_GAP iteraciones entre entradas consecutivas.
    """
    key = (fase, idx)
    state = _optimum_state.setdefault(key, {"count": 0, "last_iter": -_LOG_MIN_ITER_GAP})

    if state["count"] >= _LOG_MAX_ENTRIES:
        return
    if iteracion - state["last_iter"] < _LOG_MIN_ITER_GAP:
        return

    os.makedirs("logs_gls", exist_ok=True)
    filename = f"logs_gls/optimos_locales_{idx}.txt"

    with open(filename, "a", encoding="utf-8") as f:
        f.write(f"\n=== Iteracion {iteracion}, g = {g_actual:.6f}, h = {h_actual:.6f} ===\n")
        for i, turno in enumerate(t.getTurnos()):
            slots = [turno[j:j+3] for j in range(0, len(turno), 3)]
            f.write(f"C{i:02d}: {' '.join(slots)}\n")

    state["count"] += 1
    state["last_iter"] = iteracion


# ---------------------------------------------------------------------------
# Registro de fitness para gráficas
# ---------------------------------------------------------------------------

class _FitnessLogger:
    """Escribe g_actual, g_star y h_actual a un CSV durante el bucle GLS.

    El archivo se crea en ``logs_gls/`` con nombre
    ``fitness_fase<F>_ind<I>.csv``.
    La escritura usa un buffer interno (csv.writer con flush explícito cada
    FLUSH_EVERY registros) para minimizar el impacto en disco.
    """

    FLUSH_EVERY = 500  # Registros entre flushes explícitos

    def __init__(self, fase: int, idx: int) -> None:
        os.makedirs("logs_gls", exist_ok=True)
        path = f"logs_gls/fitness_{idx}.csv"
        self._file = open(path, "w", newline="", encoding="utf-8", buffering=1)
        self._writer = csv.writer(self._file)
        self._writer.writerow(["iteracion", "R_star", "R_actual", "h_actual"])
        self._count = 0
        self._path = path
        print(f"[GLS] Logging fitness → {path}")

    def log(self, iteracion: int, R_star: float, R_actual: float, h_actual: float) -> None:
        self._writer.writerow([iteracion, f"{R_star:.8f}", f"{R_actual:.8f}", f"{h_actual:.8f}"])
        self._count += 1
        if self._count % self.FLUSH_EVERY == 0:
            self._file.flush()

    def close(self) -> None:
        self._file.flush()
        self._file.close()
        print(f"[GLS] Fitness log cerrado: {self._path} ({self._count} registros)")



# ===========================================================================
# API PÚBLICA
# ===========================================================================

# Cada cuántas iteraciones se comprueba el reloj (time.time() es costoso en bucles densos)
_CHECK_INTERVAL = 5000

def bucle_gls(
    poblacion: list,
    parametros_alg,
    parametros,
    entrada,
    seed: int | None = None,
    max_seconds: float | None = None,
    max_iterations: int | None = None,
    idx_prueba: str | None = None,
) -> list:
    """Bucle externo GLS: optimiza cada individuo de la población con GLS.

    Optimiza y factibiliza las soluciones mediante Guided Local Search.
    Todos los parámetros del algoritmo GLS (λ, patience, condiciones de parada, etc.)
    se leen de ``parametros_alg.GLS`` (sección GLS de algorithm.properties).
    Los parámetros de tiempo y máx. iteraciones se pueden sobreescribir en llamada
    o se usan los valores de properties.

    Args:
        poblacion       : Lista de Solucion de la Fase 2.
        parametros_alg  : ParametrosAlgoritmo. Los parámetros GLS se leen
                          de ``parametros_alg.GLS``.
        parametros      : Parametros del problema.
        entrada         : Entrada del problema.
        seed            : Semilla para el RNG. None → semilla por tiempo.
        max_seconds     : Tiempo máximo por individuo (s). None → usa
                          ``maxTimeAllowed`` de properties. Valor < 0 → usa
                          max_iterations como único criterio.
        max_iterations  : Iteraciones máximas por individuo. None → usa
                          ``maxIterationsAllowed`` de properties.

    Returns:
        Lista de Solucion optimizadas (una por individuo de entrada).
    """
    rng = JavaRandom(seed if seed is not None else int(time.time() * 1000))

    _max_seconds = (
        max_seconds
        if max_seconds is not None
        else parametros_alg.max_miliseconds_allowed / 1000
    )
    _max_iterations = (
        max_iterations
        if max_iterations is not None
        else parametros_alg.max_iterations_allowed
    )

    g_max = getattr(parametros_alg.GLS, "move15_max", 3)
    g_min = getattr(parametros_alg.GLS, "move15_min", 1)

    poblacion_mejorada = []
    for idx, individuo in enumerate(poblacion):
        print(f"\n[GLS] Iniciando individuo {idx + 1}/{len(poblacion)} …\n")
        move15.init_grid(individuo, parametros, parametros_alg, entrada)

        mejor = _gls_loop(
            individuo=individuo,
            g_max=g_max,
            g_min=g_min,
            parametros_alg=parametros_alg,
            parametros=parametros,
            entrada=entrada,
            rng=rng,
            max_seconds=_max_seconds,
            max_iterations=_max_iterations,
            idx_prueba=idx_prueba,
            ind_idx=idx,
        )
        poblacion_mejorada.append(mejor)

    print("\n[GLS] FIN GLS\n")
    return poblacion_mejorada


# ===========================================================================
# BUCLE GLS INTERNO  (un único individuo)
# ===========================================================================

def _gls_loop(
    individuo,
    g_max: int,
    g_min: int,
    parametros_alg,
    parametros,
    entrada,
    rng: JavaRandom,
    max_seconds: float,
    max_iterations: int,
    idx_prueba: str,
    ind_idx: int = 0,
) -> object:
    """Bucle GLS para un único individuo.

    Implementa el algoritmo IMPROVE-SOLUTION del paper GLS.
    Todos los parámetros del algoritmo se leen de ``parametros_alg.GLS``.

    Diseño de rendimiento (equivalente a SA):
      - 1 vecino por iteración (move15, igual que SA).
      - h(t) calculada inline: g ya viene de switch_fitness; penalty_sum sólo
        se llama si penalizaciones no está vacío (fast-path en compute_penalty_sum).
      - time.time() comprobado cada _CHECK_INTERVAL iteraciones.
      - Invariantes extraídos del bucle.

    Args:
        individuo : Solucion inicial (Fase 2).  No se modifica in-place.

    Returns:
        Mejor Solucion encontrada según g(t) (fitness real, sin aumentar).
    """
    # ── Extraer parámetros GLS (una sola vez, fuera del bucle) ────────────────
    gls             = parametros_alg.GLS
    patience        = gls.getPatience()
    cond_porcent    = gls.getCondicionParadaPorcent()
    cond_ciclos     = gls.getCondicionParadaCiclos()
    lambda_         = gls.getLambda()
    p_mov_diver     = 0

    # Precalcular si hay condición de parada por porcentaje activa
    check_porcent = cond_ciclos > 0
    start = time.time()
    deadline = start + max_seconds if max_seconds >= 0 else float("inf")

    # ── Inicialización ────────────────────────────────────────────────────────
    t = order_by_lazy_criteria(individuo)

    penalizaciones: dict = {}          # {(TipoRestriccion, id_entidad) → ℘ᵢ}
    fase = 2
    fit_tuple = switch_fitness(t, entrada, parametros, parametros_alg, fase)
    g_actual = fit_tuple[0]

    r = comprobar_restricciones_en_paralelo(t, entrada, parametros)
    tmn = len(individuo.getTurnos())
    max_restricciones = (20 if entrada.getTurno().getNombre().lower() == "noche" else 18) * tmn
    R_star = (max_restricciones - r) / max_restricciones if max_restricciones else 0
    R_act = R_star
    R_ant = R_star

    # CAMBIO: QUE TODAS LAS RESTRICCIONES EMPIECEN CON PENALIZACION +1?
    indices_penalizaciones = [(TipoRestriccion.R1, 0), (TipoRestriccion.R2, 1), (TipoRestriccion.R3, 2), (TipoRestriccion.R4, 3),
                        (TipoRestriccion.R5, 4), (TipoRestriccion.R6, 5), (TipoRestriccion.R7, 6), (TipoRestriccion.R8, 7),
                        (TipoRestriccion.R9, 8), (TipoRestriccion.R10, 9), (TipoRestriccion.R11, 10), (TipoRestriccion.R12, 11),
                        (TipoRestriccion.R13, 12), (TipoRestriccion.R14, 13)]

    penalty = compute_penalty_sum(t, entrada, parametros, penalizaciones)

    # ── Función aumentada h = g - λ·penalty
    h_actual = g_actual - lambda_ * penalty

    t_star = t
    g_star = g_actual

    iteraciones_sin_mejora_h = 0
    fit_ant = g_star

    iteracion = 0
    flag = True

    # ── Logger de fitness para gráficas (se crea tras saber la fase de inicio) ──
    fitness_logger = _FitnessLogger(fase, idx_prueba)
    f_init = 0

    # ── Bucle principal ─────────────────────────────────────────────
    while iteracion < max_iterations:

        # --- Condición de parada por tiempo (cada _CHECK_INTERVAL iters) ---
        if iteracion % _CHECK_INTERVAL == 0 and time.time() >= deadline:
            break

        # --- Condición de parada / Diversificación por porcentaje de mejora ---
        if check_porcent and iteracion > 0 and iteracion % cond_ciclos == 0:
            porcent_mejora = (g_star * 100.0 / fit_ant - 100.0) if fit_ant else 0.0
            # CAMBIO: Guardar mejora de R
            pm = (R_star * 100.0 / R_ant - 100.0) if R_ant else 0.0
            str_pat=""
            for key, value in penalizaciones.items():
                str_pat += f"R{key[-1]}: {value}; "

            elapsed = time.time() - start
            print(
                f"\n[GLS] iter={iteracion} | g_best={g_star:.12f} | h_actual={h_actual:.12f} | "
                f"g_mejora%={porcent_mejora:.12f} | R_mejora%={pm:.12f} | "
                f"R_star={R_star:.12f} | R_act={R_act:.12f} | "
                f"Tamano Ind: {len(t.getTurnos())} | t={elapsed/60:.2f}min | "
                f"it_sin_mejora_h={iteraciones_sin_mejora_h} |\n"
                f"pat℘ = [ {str_pat} ]"
            )
            if R_star == 1.0 and porcent_mejora < cond_porcent:
                print(f"[GLS] NO HA MEJORADO EL FITNESS g\n")
                str_res = ""
                for idx, value in enumerate(_checks(t_star, entrada, parametros)):
                    str_res += f"R{idx}: {value:.4f}; "
                print(f"\nRestricciones incumplidas = [ {str_res} ] \n")
                return t_star
            elif pm < cond_porcent:
                print(f"[GLS] NO HA MEJORADO LA FACTIBILIDAD R\n")
                str_res = ""
                for idx, value in enumerate(_checks(t_star, entrada, parametros)):
                    str_res += f"R{idx}: {value:.4f}; "
                print(f"\nRestricciones incumplidas = [ {str_res} ] \n")
                return t_star
            else:
                fit_ant = g_star
                R_ant = R_star

        # --- Generar 1 vecino con move guiado por penalizaciones y reparación sectorial ---
        if iteraciones_sin_mejora_h == 0 and rng.random() < p_mov_diver: # MOVIMIENTO ALEATORIO, MIENTRAS SEA MODO ABIERTO
            t_prima = move_sector_repair.movimiento(t, g_max, g_min, entrada, parametros, parametros_alg, rng)
            for _ in range(2):
                t_prima = move_sector_repair.movimiento(t_prima, g_max, g_min, entrada, parametros, parametros_alg, rng)
            h_actual = float("-inf")

        else:
            t_prima = move_sector_repair.movimiento(t, g_max, g_min, entrada, parametros, parametros_alg, rng)
            if flag and len(t_prima.getTurnos()) == 22:
                p_mov_diver = gls.getPorcentajeMovDiversificacion()
                h_actual = float("-inf")
                fit_ant = 0.001
                flag = False

        # Si move15 no encontró movimiento válido, saltar sin contar estancamiento
        if t_prima is t:
            iteracion += 1
            continue

        # --- Evaluar t': fitness y función aumentada h ---
        fit_tuple_prima = switch_fitness(t_prima, entrada, parametros, parametros_alg, fase)

        g_prima = fit_tuple_prima[0]
        penalty = compute_penalty_sum(t_prima, entrada, parametros, penalizaciones)

        h_prima = g_prima - lambda_ * penalty

        # --- Criterio de aspiración jerárquico: priorizar R, y a igualdad de R, maximizar fitness g ---
        r = comprobar_restricciones_en_paralelo(t_prima, entrada, parametros)
        R_prima = (max_restricciones - r) / max_restricciones if max_restricciones else 0

        if R_prima > R_star or (R_prima == 1.0 and g_prima > g_star):
            t_star = t_prima
            R_star = R_prima
            g_star = g_prima

        # --- Decisión de movimiento ---
        if h_prima > h_actual:
            t = t_prima
            g_actual = g_prima
            h_actual = h_prima
            R_act = R_prima
            iteraciones_sin_mejora_h = 0
        else:
            iteraciones_sin_mejora_h += 1

        # --- Mecanismo de escape de óptimos locales ---
        if iteraciones_sin_mejora_h >= patience:
            mejores = get_highest_utility_patterns(
                t, entrada, parametros, penalizaciones
            )                
            if mejores:
                increment_penalties(mejores, penalizaciones)
            iteraciones_sin_mejora_h = 0
        
            # Recalcular h_actual sobre t con el nuevo estado de ℘
            penalty_nuevo = compute_penalty_sum(t, entrada, parametros, penalizaciones)
            h_actual = g_actual - lambda_ * penalty_nuevo

        # --- Muestreo de fitness para gráfica ---
        if f_init != h_actual:
            fitness_logger.log(iteracion, R_star, R_act, h_actual)
            f_init = h_actual

        iteracion += 1

    # ── Cerrar logger ────────────────────────────────────────────────────────
    fitness_logger.log(iteracion, R_star, R_act, h_actual)  # último punto
    fitness_logger.close()

    # ── Estadísticas finales ──────────────────────────────────────────────────
    str_res = ""
    for idx, value in enumerate(_checks(t_star, entrada, parametros)):
        str_res += f"R{idx}: {value:.4f}; "
    elapsed_total = (time.time() - start) / 60
    print(
        f"\n[GLS] FIN individuo: {iteracion} iters | "
        f"g_best={g_star:.6f} | "
        f"R_star={R_star:.12f} | "
        f"\nRestricciones incumplidas = [ {str_res} ] | \n"
        f"t={elapsed_total:.2f}min"
    )
    return t_star