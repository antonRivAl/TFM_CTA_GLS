from __future__ import annotations

import math
from functools import lru_cache

from .constants import STRING_DESCANSO, STRING_NO_TURNO
from . import restrictions

# =============================================================================
# CORRESPONDENCIA CON CÓDIGO JAVA
# =============================================================================
# Archivos Java (en src/main/fitnessFunction/):
#   - DeciderFitnessFunction.java
#       → switch_fitness()  ≡  DeciderFitnessFunction.switchFitnessF()
#
#   - Fitness.java
#       → fit_ponderado_restric_y_num_ctrls_y_similitud_y_continuidad()
#            ≡  Fitness.fitPonderadoRestricYNumCtrlsYSimilitudYContinuidad()
#       → slots_classification()  ≡  Fitness.slotsClassification()
#       → continuidad_momento_cambio()  ≡  Fitness.continuidadMomentoCambio()
#       → fit_global()  ≡  Fitness.fitGlobal()
#
#   - FitnessFase3.java
#       → tiempo_opt_trabajo_descanso()     ≡  FitnessFase3.tiempoOptTrabajoDescanso()
#       → tiempo_opt_trabajo_posicion()     ≡  FitnessFase3.tiempoOptTrabajoPosicion()
#       → tiempo_porcentaje()               ≡  FitnessFase3.tiempoPorcentaje()
#       → estadillos()                      ≡  FitnessFase3.estadillos()
#       → minimizar_intervalos()            ≡  FitnessFase3.minimizarIntervalos()
#       → maximizar_acreditacion()          ≡  FitnessFase3.maximizarAcreditacion()
#       → homogenea()                       ≡  FitnessFase3.homogenea()
# =============================================================================


class Fitness:
    sectores_elementales_totales = 0.0
    ctrls_completos = 0.0


@lru_cache(maxsize=50000)
def _slots_classification_cached(controlador: str) -> tuple[int, int]:
    rest = controlador.count(STRING_DESCANSO) + controlador.count(STRING_NO_TURNO)
    return rest, (len(controlador) // 3) - rest


def slots_classification(controlador: str) -> list[int]:
    return list(_slots_classification_cached(controlador))


def switch_fitness(individuo, entrada, parametros, parametros_alg, fase: int = 2) -> list[float]:
    """Selecciona la función de fitness en función de la fase del algoritmo.

    Args:
        individuo      : Solución a evaluar.
        entrada        : Entrada del problema.
        parametros     : Parámetros del problema.
        parametros_alg : Parámetros del algoritmo.
        fase           : 2 → elegir entre fitness unificado (eliminar imaginarios + fitGlobal), o bifasico (F2 elimina controladores imaginarios y R1-14, F3 optimiza fitGlobal).
                         3 → fitness de optimización pura (fitGlobal, sin término f0).

    Returns:
        [fit, f0_o_f1, f1, f2, f3, f4] como lista de floats.
        - f0: fracción de turnos con controlador real (1.0 = sin imaginarios).
        - fit: fitness combinado si hay imaginarios, fitGlobal si no.
    """

    if fase == 3:
        return fit_global(individuo, entrada, parametros, parametros_alg)

    # Fase 2 — fitness unificado (imaginarios + fitGlobal)
    fun = parametros_alg.getFuncionFitnessFase2()
    if fun == "reduccionControladoresYRestriccionesYSimilitudYContinuidad":
        return fit_ponderado_restric_y_num_ctrls_y_similitud_y_continuidad(individuo, entrada, parametros, parametros_alg)
    if fun == "unificadaF2y3":
        return fit_global_con_imaginarios(individuo, entrada, parametros, parametros_alg)
    if fun == "OnlyConstrains":
        return [1000 - restrictions.penalizacion_por_restricciones(individuo, entrada, parametros)]
    print(f"[Fitness Fase 2] Función '{fun}' por implementar. Se devuelve fitness 0.")
    return [0.0, 0.0, 0.0, 0.0, 0.0]


def fit_global_con_imaginarios(individuo, entrada, parametros, param_alg) -> list[float]:
    """Fitness unificado: fitGlobal + término f0 para controladores imaginarios.

    En lugar de dos fases separadas, un único fitness combina:
      - f0: fracción de turnos asignados a controladores reales (1.0 = sin imaginarios).
            Cuando f0 < 1, actúa como palanca prioritaria para eliminar imaginarios.
      - fit_global: los 4 objetivos de Fase 3 (O1..O4).

    La combinación es:
        fit = W0 * f0 + (1 - W0) * fit_global    si hay imaginarios
        fit = fit_global                           cuando f0 == 1.0

    W0 (gls.w_imaginarios) controla cuánto peso se da a eliminar imaginarios.
    Con W0=0.6 el algoritmo los prioriza sin ignorar la calidad global.

    Returns: [fit, f0, f1, f2, f3, f4] — el f0 ocupa el índice 1 mientras hay
             imaginarios, igual que f1 lo hacía en la Fase 2 anterior.
             La transición Fase 2→3 en gls.py se detecta cuando f0 >= 1.0 (≡ fit_tuple[1] >= 1).
    """
    c_req   = len(entrada.getControladores())   # controladores reales disponibles
    tmn = len(individuo.getTurnos())        # turnos en la solución actual
    fit = f1 = 0

    # Calcular siempre fitGlobal para usarlo como componente
    fg = fit_global(individuo, entrada, parametros, param_alg)
    # fg = [fit, f1, f2, f3, f4]

    if c_req >= tmn: 
        # Sin imaginarios: fitness puro de fitGlobal, sin término f0
        f1 = 1.0
        fit = fg[0]
    else:
        # Reduccion de controladores imaginarios
        n_slots = len(entrada.getSectorizacion())
        c_max = len(entrada.getListaSectoresAbiertos()) * 3
        f1_min = sum(n_slots * (i * 2) for i in range(1, tmn + 1) if i < math.floor(Fitness.ctrls_completos))
        f1_min = f1_min / (c_max * c_max) if c_max else 0
        f1_max = sum(n_slots * (i * 2) for i in range(1, tmn + 1) if not (i <= (tmn - math.floor(Fitness.ctrls_completos))))
        f1_max = f1_max / (c_req * c_req) if c_req else 0
        for idx, turno in enumerate(individuo.getTurnos()):
            f1 += slots_classification(turno)[1] * ((idx * 2) + 1)
        f1 = f1 / (tmn * tmn) if tmn else 0
        denom = f1_max - f1_min
        f1 = (f1 - f1_min) / denom if denom else 0

        # Con imaginarios: combinación ponderada
        w0 = getattr(param_alg, 'GLS', None)
        w0 = w0.getWImaginarios() if w0 else 0.75
        fit = w0 * f1 + (1.0 - w0) * fg[0]    
    return [fit, f1, fg[1], fg[2], fg[3], fg[4]]



def fit_ponderado_restric_y_num_ctrls_y_similitud_y_continuidad(individuo, entrada, parametros, param_alg) -> list[float]:
    """Fitness de Fase 2: factibilización (eliminar controladores imaginarios).

    Rama Fase 2 (c_req < tmn — existen controladores imaginarios):
        f1 = distribución ponderada por índice de turno.
             Cuando f1 → 1 los imaginarios tienen menos trabajo (→ pueden eliminarse).
        f2 = tasa de cumplimiento de R1–R14.
        f3 = continuidad en el momento de cambio de turno.
        f4 = 0 (desactivado en Fase 2).

    Rama Fase 3 interna (c_req >= tmn — todos los controladores son reales):
        Usada cuando se llama con fase=2 pero la solución ya es factible.
        f1 = 1 fijo.
        f2, f3, f4 = restricciones, continuidad y estadillos.

    Returns: [fit, f1, f2, f3, f4]
    """
    fit = f1 = f2 = f3 = f4 = 0.0
    tmn = len(individuo.getTurnos())
    n_slots = len(entrada.getSectorizacion())
    max_restricciones = (20 if entrada.getTurno().getNombre().lower() == "noche" else 18) * tmn
    # Track: Calculo Restricciones y Objetivos
    # Track: Calculo de R1+R2+R3+R4+R5+R6+R7+R8+R9+R10+R11+R12+R13+R14 (ponderadas → escalar r)
    r = restrictions.comprobar_restricciones_en_paralelo(individuo, entrada, parametros)
    c_req = len(entrada.getControladores())

    if c_req >= tmn:
        # Condición: c_req >= tmn  →  controladores reales (c_req) ≥ turnos de la solución (tmn)
        # Significado: TODOS los turnos tienen controlador real asignado; no quedan imaginarios.
        # Objetivo: optimizar calidad de la solución ya factible con los 4 objetivos:

        f1 = 1 # f1=1 fijo (ctrlrs ya optimizados)
        # Track: Calculo de R1..R14 → f2 (tasa de cumplimiento de restricciones)
        f2 = (max_restricciones - r) / max_restricciones if max_restricciones else 0
        # Track: Calculo de O3b (continuidad en momento de cambio de turno) → f3
        f3 = continuidad_momento_cambio(individuo, entrada) # QUITAR LUEGO
        # Track: Calculo de O2 (similitud con estadillos) → f4
        f4 = estadillos(len(individuo.getControladores()), len(individuo.getTurnos()[0]) // 3, individuo.getTurnos(), entrada.getSlotMomentoActual()) # QUITAR LUEGO
        fit = (
            f1 * param_alg.getPonderacionFitness1() # QUITAR LUEGO
            + f2 * param_alg.getPonderacionFitness2() # QUITAR LUEGO
            #f2 * (param_alg.getPonderacionFitness2() + param_alg.getPonderacionFitness1())
            + f3 * param_alg.getPonderacionFitness3() # QUITAR LUEGO
            + f4 * param_alg.getPonderacionFitness4() # QUITAR LUEGO
        )
    else:
        # Condición: c_req < tmn  →  turnos de la solución (tmn) > controladores reales (c_req)
        # Significado: existen turnos asignados a controladores IMAGINARIOS que deben eliminarse.
        # Objetivo: comprimir los turnos imaginarios hacia los reales optimizando 3 objetivos:

        # Track: Calculo de O4 (distribucion equilibrada de carga) + parcialmente O1 y O3 → f1
        c_max = len(entrada.getListaSectoresAbiertos()) * 3
        f1_min = sum(n_slots * (i * 2) for i in range(1, tmn + 1) if i < math.floor(Fitness.ctrls_completos))
        f1_min = f1_min / (c_max * c_max) if c_max else 0
        f1_max = sum(n_slots * (i * 2) for i in range(1, tmn + 1) if not (i <= (tmn - math.floor(Fitness.ctrls_completos))))
        f1_max = f1_max / (c_req * c_req) if c_req else 0
        for idx, turno in enumerate(individuo.getTurnos()):
            f1 += slots_classification(turno)[1] * ((idx * 2) + 1)
        f1 = f1 / (tmn * tmn) if tmn else 0
        denom = f1_max - f1_min
        f1 = (f1 - f1_min) / denom if denom else 0
        # Track: Calculo de R1..R14 → f2 (tasa de cumplimiento de restricciones)
        f2 = (max_restricciones - r) / max_restricciones if max_restricciones else 0
        # Track: Calculo de O3b (continuidad en momento de cambio de turno) → f3
        f3 = continuidad_momento_cambio(individuo, entrada) # QUITAR LUEGO
        fit = f1 * param_alg.getPonderacionFitness1() + f2 * (param_alg.getPonderacionFitness2() + param_alg.getPonderacionFitness4()) + f3 * param_alg.getPonderacionFitness3()
    return [fit, f1, f2, f3, f4]


# ===========================================================================
# FITNESS FASE 3 — fitGlobal  (port de Fitness.fitGlobal + FitnessFase3.java)
# ===========================================================================

def fit_global(individuo, entrada, parametros, param_alg) -> list[float]:
    """Fitness de Fase 3: optimización completa de todos los objetivos del TFM.

    Equivalente a Fitness.fitGlobal() en Java, que usa todas las funciones
    de FitnessFase3.java.

    Estructura de objetivos:
        f1 (cDeseables) = O1a·w1a + O1b·w1b + O1c·w1c
            O1a: tiempo óptimo de trabajo en misma posición (45 min)
            O1b: tiempo óptimo de trabajo continuo entre descansos (90 min)
            O1c: porcentaje de tiempo en posición ejecutiva (40–60%)
        f2 (estadillos)          = O2: similitud con estadillos anteriores
        f3 (obj3)                = O3a·w3a + O3b·w3b
            O3a: minimizar intervalos de descanso
            O3b: maximizar sectores elementales (acreditaciones)
        f4 (homogenea)           = O4: distribución equilibrada de carga

    Returns: [fit, f1, f2, f3, f4]
    """
    # Track: Calculo Restricciones y Objetivos
    num_controladores = len(individuo.getControladores())
    num_turnos = len(individuo.getTurnos()[0]) // 3   # slots por turno
    turnos = individuo.getTurnos()
    pObj = parametros.getPesosObjetivos()

    # Track: Calculo de O1a (tiempo óptimo trabajo en misma posición) → traPosicion
    tra_posicion = tiempo_opt_trabajo_posicion(num_controladores, num_turnos, turnos, parametros)
    # Track: Calculo de O1b (tiempo óptimo trabajo continuo entre descansos) → traDescanso
    tra_descanso = tiempo_opt_trabajo_descanso(num_controladores, num_turnos, turnos, parametros)
    # Track: Calculo de O1c (porcentaje tiempo ejecutivo 40-60%) → porcentaje
    porcentaje = 1.0 - tiempo_porcentaje(num_controladores, num_turnos, turnos, parametros)

    # f1 = combinación ponderada de los tres sub-objetivos de O1
    f1 = (pObj.peso_obj1_sub1 * tra_posicion
          + pObj.peso_obj1_sub2 * tra_descanso
          + pObj.peso_obj1_sub3 * porcentaje)

    # Track: Calculo de O2 (similitud con estadillos) → f2
    f2 = estadillos(num_controladores, num_turnos, turnos, entrada.getSlotMomentoActual())

    # Track: Calculo de O3a (minimizar intervalos de descanso) → minimizar_int
    minimizar_int = minimizar_intervalos(num_controladores, num_turnos, turnos)
    # Track: Calculo de O3b (maximizar sectores elementales/acreditaciones) → max_acred
    max_acred = maximizar_acreditacion(entrada, num_controladores, num_turnos, turnos,
                                       Fitness.sectores_elementales_totales)
    # f3 = combinación ponderada de los dos sub-objetivos de O3
    f3 = minimizar_int * pObj.peso_obj3_sub1 + max_acred * pObj.peso_obj3_sub2

    # Track: Calculo de O4 (distribución equilibrada de carga) → f4
    f4 = homogenea(turnos)

    fit = (pObj.getPesoObj1() * f1
           + pObj.getPesoObj2() * f2
           + pObj.getPesoObj3() * f3
           + pObj.getPesoObj4() * f4)

    return [fit, f1, f2, f3, f4]


# ===========================================================================
# FUNCIONES OBJETIVOS INDIVIDUALES — port de FitnessFase3.java
# ===========================================================================

# Track: Calculo de O1b (tiempo óptimo de trabajo continuo entre descansos) – llamada desde fit_global
def tiempo_opt_trabajo_descanso(num_controladores: int, num_turnos: int,
                                 tabla: list[str], parametros) -> float:
    """O1.1 — Tiempo óptimo de trabajo continuo entre descansos (90 min).

    Mide la desviación media del tiempo de cada bloque de trabajo respecto al
    óptimo ``tiempoTrabOpt``. Cuanto más cercana sea la media a 0, más cerca
    están los bloques del óptimo.

    Returns: valor normalizado en [0, 1]. 1 = perfecto (todos los bloques duran exactamente tiempoTrabOpt).
    """
    trab_opt = parametros.getTiempoTrabOpt()
    taman_slot = parametros.getTamanoSlots()
    # Máxima desviación posible: si cada controlador tiene un bloque de trabajo
    # tan lejos del óptimo como sea posible (= tiempoTrabOpt - tiempoTrabMin)
    # ocurriendo num_turnos/6 veces (heurístico del Java original)
    max_dev = (trab_opt - parametros.getTiempoTrabMin()) * (num_turnos / 6)
    desvios = []
    for i in range(num_controladores):
        turno = tabla[i]
        diferencia = 0
        t_posicion = 0
        for j in range(num_turnos):
            slot = turno[j * 3: j * 3 + 3]
            if slot != STRING_DESCANSO and slot != STRING_NO_TURNO:
                t_posicion += taman_slot
                if j + 1 == num_turnos and t_posicion != 0:
                    diferencia += abs(t_posicion - trab_opt)
                    t_posicion = 0
            else:
                if t_posicion != 0:
                    diferencia += abs(t_posicion - trab_opt)
                    t_posicion = 0
        desvios.append(diferencia)

    fitness = sum(desvios) / num_controladores if num_controladores else 0.0
    return (max_dev - fitness) / max_dev if max_dev else 0.0


# Track: Calculo de O1a (tiempo óptimo en misma posición/sector consecutivo) – llamada desde fit_global
def tiempo_opt_trabajo_posicion(num_controladores: int, num_turnos: int,
                                 tabla: list[str], parametros) -> float:
    """O1.2 — Tiempo óptimo de trabajo en una misma posición consecutiva (45 min).

    Mide la desviación media del tiempo que un controlador pasa en cada bloque
    de slots consecutivos con el MISMO código (mismo sector y misma posición)
    respecto al óptimo ``tiempoPosOpt``.

    Returns: valor normalizado en [0, 1]. 1 = perfecto.
    """
    pos_opt  = parametros.getTiempoPosOpt()
    trab_min = parametros.getTiempoTrabMin()
    taman_slot = parametros.getTamanoSlots()
    max_dev = (pos_opt - trab_min) * 8 * (num_turnos / 30)
    desvios = []
    for i in range(num_controladores):
        turno = tabla[i]
        diferencia = 0
        t_posicion = 0
        str_previa = None
        for j in range(num_turnos + 1):
            if j == num_turnos:
                if str_previa and str_previa != STRING_DESCANSO and str_previa != STRING_NO_TURNO:
                    diferencia += abs(t_posicion - pos_opt)
            else:
                slot = turno[j * 3: j * 3 + 3]
                if str_previa is not None:
                    if slot == str_previa:
                        if slot != STRING_DESCANSO and slot != STRING_NO_TURNO:
                            t_posicion += taman_slot
                    else:
                        if str_previa != STRING_DESCANSO and str_previa != STRING_NO_TURNO:
                            diferencia += abs(t_posicion - pos_opt)
                            t_posicion = taman_slot
                        else:
                            t_posicion = taman_slot
                elif slot != STRING_DESCANSO and slot != STRING_NO_TURNO:
                    t_posicion = taman_slot
                str_previa = slot
        desvios.append(diferencia)

    fitness = sum(desvios) / num_controladores if num_controladores else 0.0
    return (max_dev - fitness) / max_dev if max_dev else 0.0


# Track: Calculo de O1c (porcentaje tiempo ejecutivo 40-60%) – llamada desde fit_global
def tiempo_porcentaje(num_controladores: int, num_turnos: int,
                       tabla: list[str], parametros) -> float:
    """O1.3 — Porcentaje de trabajo óptimo en posición ejecutiva (40–60%).

    Un slot es ejecutivo si su código es UPPERCASE (p.ej. 'AAB').
    Devuelve la penalización media normalizada por estar fuera del rango
    [porcentPosMin, porcentPosMax]. 0 = perfecto (todos dentro del rango).

    Returns: penalización en [0, 1]. 0 = perfecto.
    """
    porc_min = parametros.getPorcentPosMin()
    porc_max = parametros.getPorcentPosMax()
    taman_slot = parametros.getTamanoSlots()
    array = []
    for i in range(num_controladores):
        turno = tabla[i]
        t_total = 0.0
        t_ejecutivo = 0.0
        for j in range(num_turnos):
            slot = turno[j * 3: j * 3 + 3]
            if slot != STRING_DESCANSO and slot != STRING_NO_TURNO:
                if slot[0].isupper():
                    t_ejecutivo += taman_slot
                t_total += taman_slot
        if t_total == 0:
            array.append(0.0)
            continue
        diferencia = t_ejecutivo / t_total
        if diferencia < porc_min:
            array.append((porc_min - diferencia) / porc_min)
        elif diferencia > porc_max:
            array.append((diferencia - porc_max) / porc_min)
        else:
            array.append(0.0)
    return sum(array) / num_controladores if num_controladores else 0.0


# Track: Calculo de O2 (similitud con estadillos/plantillas) – llamada desde fit_ponderado* → f4 y desde fit_global → f2
def estadillos(num_controladores: int, num_slots: int, tabla: list[str], momento_actual: int) -> float:
    """O2 — Similitud con estadillos anteriores.

    Mide la compacidad del estadillo: cuántas celdas adyacentes (horizontal
    y vertical) tienen el mismo sector. Valores altos → solución parecida a
    un estadillo clásico.

    Returns: valor normalizado en [0, 1]. 1 = máxima similitud posible.
    """
    count = 0.0
    for i in range(num_controladores):
        if i >= len(tabla):
            break
        for j in range(momento_actual, num_slots):
            actual = tabla[i][j * 3 : j * 3 + 3]
            if j < num_slots - 1:
                derecha = tabla[i][(j + 1) * 3 : (j + 1) * 3 + 3]
                if actual.lower() == derecha.lower():
                    count += 1.5 if actual == derecha else 1
            if i < min(num_controladores, len(tabla)) - 1:
                abajo = tabla[i + 1][j * 3 : j * 3 + 3]
                if actual.lower() == abajo.lower():
                    count += 1
    max_value = (num_controladores - 1) * (1.5 * ((num_slots - momento_actual) - 1)) * 2
    return 1 - ((max_value - count) / max_value) if max_value else 0


# Track: Calculo de O3a (minimizar intervalos de descanso) – llamada desde fit_global → f3
def minimizar_intervalos(num_controladores: int, num_turnos: int, tabla: list[str]) -> float:
    """O3.1 — Minimizar número de intervalos de descanso (agruparlos).

    Cuenta el número total de bloques de descanso (transiciones trabajo→descanso)
    sumados para todos los controladores. Menos bloques = descanso más compacto.

    Returns: valor normalizado en [0, 1]. 1 = mínimo de intervalos posible.
    """
    min_intervalos = num_controladores                                  # mínimo: 1 bloque por ctrl
    max_intervalos = (num_turnos // 6) * num_controladores              # máximo heurístico
    num_intervalos_descanso = 0
    for i in range(num_controladores):
        turno = tabla[i]
        str_previa = ""
        for j in range(num_turnos):
            slot = turno[j * 3: j * 3 + 3]
            if slot == STRING_DESCANSO and str_previa != STRING_DESCANSO:
                num_intervalos_descanso += 1
            str_previa = slot
    denom = max_intervalos - min_intervalos
    return (max_intervalos - num_intervalos_descanso) / denom if denom else 0.0


# Track: Calculo de O3b (maximizar sectores elementales/acreditaciones) – llamada desde fit_global → f3
def maximizar_acreditacion(entrada, num_controladores: int, num_turnos: int,
                            turnos: list[str], sectores_elementales_totales: float) -> float:
    """O3.2 — Maximizar el número de sectores elementales cubiertos (acreditaciones).

    Cuenta para cada controlador cuántos sectores elementales distintos cubre
    a lo largo de su turno. La suma total se normaliza entre el mínimo posible
    (1 por controlador) y el máximo (todos los elementales cubiertos por todos).

    Returns: valor normalizado en [0, 1]. 1 = todos los controladores cubren todos los elementales.
    """
    sectores_abiertos = entrada.getListaSectoresAbiertos()
    cnt = 0.0
    for turno in turnos:
        # Sectores (objetos Sector) que visita este turno
        sectores_turno = []
        for j in range(0, len(turno), 3):
            slot = turno[j: j + 3]
            if slot.lower() != STRING_DESCANSO.lower() and slot != STRING_NO_TURNO:
                for sector in sectores_abiertos:
                    if sector.id.lower() == slot.lower() and sector not in sectores_turno:
                        sectores_turno.append(sector)
        # Sectores elementales cubiertos por los sectores de este turno
        elementales = []
        for sector in sectores_turno:
            for elem in sector.sectores_elementales:
                if not any(e.lower() == elem.lower() for e in elementales):
                    elementales.append(elem)
        cnt += len(elementales)

    max_val = len(turnos) * sectores_elementales_totales
    min_val = len(turnos)
    denom = max_val - min_val
    return 1.0 - ((max_val - cnt) / denom) if denom else 0.0


# Track: Calculo de O4 (distribución equilibrada de carga de trabajo) – llamada desde fit_global → f4
def homogenea(tabla: list[str]) -> float:
    """O4 — Distribución equilibrada de la carga de trabajo.

    Calcula (media - desviación_típica) / media sobre los slots trabajados
    de cada controlador. Cuanto menor sea la desviación típica respecto a la
    media, más equilibrada es la distribución.

    Returns: valor en [0, 1]. 1 = distribución perfectamente equilibrada (todos trabajan igual).
    """
    if not tabla:
        return 0.0
    work_slots = []
    for turno in tabla:
        total = len(turno) // 3
        rest = turno.count(STRING_DESCANSO) + turno.count(STRING_NO_TURNO)
        work_slots.append(total - rest)
    mean = sum(work_slots) / len(work_slots)
    if mean == 0:
        return 0.0
    variance = sum((x - mean) ** 2 for x in work_slots) / len(work_slots)
    std_dev = math.sqrt(variance)
    return (mean - std_dev) / mean


# Track: Calculo de O3b (continuidad en momento de cambio) – llamada desde fit_ponderado* → f3
def continuidad_momento_cambio(solucion, entrada) -> float:
    """Objetivo operativo: continuidad en el momento de cambio de turno.

    Fracción de turnos donde el slot justo antes del momento de cambio es
    idéntico al slot en/después del momento de cambio. Si no hay momento de
    cambio (slot_momento_actual == 0), retorna 1.0.

    Returns: valor en [0, 1]. 1 = todos los controladores mantienen sector en el relevo.
    """
    actual = entrada.getSlotMomentoActual() * 3
    if actual == 0:
        return 1.0
    turnos = solucion.getTurnos()
    fit = 0.0
    norm = 1.0 / len(turnos) if turnos else 0
    for turno in turnos:
        if actual + 3 <= len(turno) and turno[actual - 3 : actual] == turno[actual : actual + 3]:
            fit += norm
    return fit
