from __future__ import annotations

import math
import time

from . import move15, restrictions
from .fitness import switch_fitness
from .java_random import JavaRandom
from .metaheuristic import order_by_lazy_criteria

# =============================================================================
# CORRESPONDENCIA CON CÓDIGO JAVA
# =============================================================================
# Archivos Java:
#   - src/main/algorithms/simulatedAnnealing/SimulatedAnnealing.java
#       → bucle_sa(), simulated_annealing()
#
#   - src/main/algorithms/simulatedAnnealing/moves/DeciderMove.java
#       → El switch de movimientos está inlineado: solo se llama a move15.
#         (En Java: DeciderMove.switchMoves → case "movimiento15" → Move15)
#
# NOTA: En Java, el SA tiene una lógica adicional de primera iteración
# (orderByControllerID) cuando nTurnos == nControladores que no está
# implementada en esta versión Python.
# =============================================================================



def order_by_controller_id(individuo):
    """
    Equivalente a SimulatedAnnealing.orderByControllerID() en Java.
    Reordena los turnos para que turno[i] corresponda al controlador con id=i+1,
    actualizando turnoAsignado de cada controlador a su posición nueva.
    """
    turnos = individuo.getTurnos()
    controladores = individuo.getControladores()
    turnos_ordenados = []
    for controlador in controladores:
        num_turno = controlador.getTurnoAsignado()
        turnos_ordenados.append(turnos[num_turno])
        controlador.setTurnoAsignado(controladores.index(controlador))
    individuo.setTurnos(turnos_ordenados)
    individuo.setControladores(controladores)
    return individuo


def bucle_sa(poblacion_inicial, parametros_alg, parametros, entrada, seed: int | None = None, max_seconds: float | None = None, max_iterations: int | None = None, stop_on_phase3: bool = False):
    """Ejecuta el bucle SA sobre la poblacion inicial.

    Args:
        stop_on_phase3: Si True, el SA se detiene en cuanto detecta que una
            solucion candidata ha entrado en Fase 3 (f1 > 0, condicion
            c_req < tmn en fitness.py). La solucion detectada se devuelve
            para que el GLS continue la optimizacion. Si False (por defecto),
            el SA cubre ambas fases como hasta ahora.
    """
    rng = JavaRandom(seed if seed is not None else int(time.time() * 1000))
    poblacion_mejorada = []
    for idx, individuo in enumerate(poblacion_inicial):
        move15.init_grid(individuo, parametros, parametros_alg, entrada)
        improved = simulated_annealing(individuo, idx, parametros_alg, parametros, entrada, rng, max_seconds, max_iterations, stop_on_phase3=stop_on_phase3)
        if improved is not None:
            poblacion_mejorada.append(improved)
    print("FIN RECOCIDO")
    return poblacion_mejorada


def simulated_annealing(individuo, n, parametros_alg, parametros, entrada, rng, max_seconds=None, max_iterations=None, stop_on_phase3: bool = False):
    start = time.time()
    temperatura = parametros_alg.SA.getTemperaturaInicial()
    descenso_temp = parametros_alg.SA.getDescensoTemperatura()
    iteraciones_temp = parametros_alg.SA.getIteracionesTemperaturaL()
    cut_off = parametros_alg.SA.metodo_descenso_iteraciones.lower() == "cutoff"
    condicion_ciclos = parametros_alg.SA.condicion_parada_ciclos
    condicion_porcent = parametros_alg.SA.condicion_parada_porcent
    numero_mejoras = parametros_alg.SA.condicion_parada_numero_mejoras
    g_max = (parametros_alg.SA.getTamanoMaxMov() // parametros.getTamanoSlots()) * 3
    g_min = (parametros_alg.SA.getTamanoMinMov() // parametros.getTamanoSlots()) * 3
    max_seconds = max_seconds if max_seconds is not None else parametros_alg.max_miliseconds_allowed / 1000
    max_iterations = max_iterations if max_iterations is not None else parametros_alg.max_iterations_allowed

    iteracion = 0
    porcent_mejora = 1
    individuo = order_by_lazy_criteria(individuo)
    best_sol = individuo
    fit1 = switch_fitness(individuo, entrada, parametros, parametros_alg)
    fit_ant = fit1[0]
    best_fit = fit_ant
    m = 0
    a_mejor = 1
    cut_count = 0
    first_time = True

    while (
        (iteracion % condicion_ciclos != 0 or (condicion_porcent < porcent_mejora or a_mejor >= numero_mejoras))
        and (iteracion < max_iterations if max_seconds < 0 else time.time() - start < max_seconds)
    ):
        if max_seconds >= 0 and max_iterations is not None and iteracion >= max_iterations:
            break
        individuo2 = move15.movimiento(individuo, g_max, g_min, entrada, parametros, parametros_alg, rng)
        if len(individuo.getTurnos()) != len(individuo.getControladores()):
            individuo2 = order_by_lazy_criteria(individuo2)
        elif first_time and len(individuo.getTurnos()) == len(individuo.getControladores()):
            # Equivalente a la lógica firstTime de SimulatedAnnealing.java:
            # ordena por ID de controlador en la primera iteración cuando todos
            # los turnos tienen controlador asignado (caso Pre-táctico II).
            individuo = order_by_controller_id(individuo)
            individuo2 = order_by_controller_id(individuo2)
            first_time = False
        fit2 = switch_fitness(individuo2, entrada, parametros, parametros_alg)
        val1, val2 = fit1[0], fit2[0]
        if len(fit2) > 2 and fit2[2] == 1:
            print("Solucion valida.")
            individuo = individuo2
            fit1 = fit2
            best_fit = val2
            best_sol = individuo2
            break
        # AQUI EMPIEZA LA FASE 3 (deteccion): si stop_on_phase3 y f1 > 0,
        # la solucion candidata ya entro en Fase 3 (c_req < tmn en fitness.py).
        # Se guarda como mejor y se cede el control al GLS.
        # PROVISIONAL
        if stop_on_phase3 and len(entrada.getControladores()) >= len(individuo2.getTurnos()):
            print("[SA→GLS] Fase 3 detectada (f1 > 0). Cediendo control al GLS.")
            if val2 > best_fit:
                best_fit = val2
                best_sol = individuo2
            break
        if val1 >= val2:
            empeora = math.exp((-(val1 - val2) / temperatura)) if temperatura else 0
            if rng.random() < empeora:
                individuo = individuo2
                fit1 = fit2
                cut_count += 1
        else:
            if best_fit < val2:
                best_fit = val2
                best_sol = individuo2
            m += 1
            cut_count += 1
            individuo = individuo2
            fit1 = fit2

        if cut_off and cut_count == 2000:
            temperatura *= descenso_temp
            cut_count = 0
        iteracion += 1
        if iteraciones_temp and iteracion % iteraciones_temp == 0:
            if parametros_alg.SA.metodo_descenso_temperatura.lower() == "krikpatric":
                temperatura *= descenso_temp
            elif parametros_alg.SA.metodo_descenso_temperatura.lower() == "aarts":
                temperatura = parametros_alg.SA.getTemperaturaInicial() / (1 + descenso_temp * math.log(1 + iteracion))
            parametros_alg.SA.porcentaje_eleccion_mov *= 0.99
            a_mejor = m / iteraciones_temp
            m = 0
            cut_count = 0
        if iteracion % condicion_ciclos == 0:
            porcent_mejora = (best_fit * 100 / fit_ant) - 100 if fit_ant else 0
            print(f"TempAct: {temperatura}| Iteracion: {iteracion} |Tamano Ind: {len(individuo.getTurnos())} |Porct. de Mejora: {porcent_mejora}% o N. Mejoras: {a_mejor} |FITAnt .. FITBest: {fit_ant} {best_fit} |tiempo: {(time.time() - start)/60}")
            if best_fit > fit_ant:
                fit_ant = best_fit
        if best_fit == 1:
            break
    res = restrictions.penalizacion_por_restricciones(best_sol, entrada, parametros)
    print(f"TIME: {(time.time() - start)/60} | Restricciones: {res}")
    return best_sol
