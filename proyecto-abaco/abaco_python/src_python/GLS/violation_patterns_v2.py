"""Versión V2 de Violation-Patterns para el algoritmo GLS.

Esta versión calcula EXACTAMENTE las mismas 14 restricciones duras que 
la función _checks() en restrictions.py, con la opcion de agregar la
penalización de forma global, o identificar la entidad (Turno o Controlador)
concreta que está cometiendo la infracción.

Esto permite al algoritmo GLS aplicar las utilidades y penalizaciones
con la granularidad requerida por el método.
"""

import math
from enum import IntEnum
from typing import NamedTuple, Hashable

from ..constants import STRING_DESCANSO, STRING_NO_TURNO
from ..restrictions import (
    PESO_POR_RESTRICCION,
    REST_SLOTS,
    PENALIZACION,
    _slots,
    _checks,
    _ensure_fast_cache,
    lista_de_sectores_turno,
    calculate,
    comprobar_afinidad
)

from ..fitness import slots_classification, Fitness


class TipoRestriccion(IntEnum):
    R1 = 0
    R2 = 1
    R3 = 2
    R4 = 3
    R5 = 4
    R6 = 5
    R7 = 6
    R8 = 7
    R9 = 8
    R10 = 9
    R11 = 10
    R12 = 11
    R13 = 12
    R14 = 13
    Rf1 = 14

class ViolationPattern(NamedTuple):
    tipo: TipoRestriccion
    id_entidad: Hashable
    coi: float  # Magnitud de la infracción sin peso (coste)

# ==============================================================================
# FUNCIONES EXTRACTORAS DE PATRONES (Espejo de R1-R14 en restrictions.py)
# ==============================================================================

def _patterns_R1(individuo, entrada) -> list[ViolationPattern]:
    if len(entrada.getNucleosAbiertos()) == 1:
        return []
    sector_ids = entrada._fast_sector_ids
    patterns = []
    for idx_c, controlador in enumerate(individuo.getControladores()):
        num_turno = controlador.turno_asignado
        if num_turno == -1:
            patterns.append(ViolationPattern(TipoRestriccion.R1, idx_c, 1.0))
            continue
        x = 0.0
        turno = individuo.getTurnos()[num_turno]
        for slot in _slots(turno):
            if slot not in REST_SLOTS:
                if slot.lower() not in sector_ids:
                    x += PENALIZACION
        if x:
            patterns.append(ViolationPattern(TipoRestriccion.R1, idx_c, 1.0 + x))
    return patterns

def _patterns_R2(individuo, entrada) -> list[ViolationPattern]:
    ruta_ids = entrada._fast_ruta_ids
    patterns = []
    for idx_c, controlador in enumerate(individuo.getControladores()):
        if not controlador.con or controlador.turno_asignado == -1:
            continue
        x = 0.0
        turno = individuo.getTurnos()[controlador.turno_asignado]
        for slot in _slots(turno):
            ok = slot in REST_SLOTS or slot.lower() in ruta_ids
            if not ok:
                x += PENALIZACION
        if x:
            patterns.append(ViolationPattern(TipoRestriccion.R2, idx_c, 1.0 + x))
    return patterns

def _patterns_R3(individuo, entrada, turno_obj, parametros) -> list[ViolationPattern]:
    slots_des_tl = turno_obj.getSlotsDesTL()
    slots_des_tc = turno_obj.getSlotsDesTC()
    patterns = []
    for idx_c, controlador in enumerate(individuo.getControladores()):
        ok = True
        num_turno = controlador.turno_asignado
        if num_turno != -1:
            assigned = individuo.getTurnos()[num_turno]
            cnt = sum(1 for slot in _slots(assigned) if slot in REST_SLOTS)
            if controlador.turno.upper() in {"TL", "ML", "N"} and slots_des_tl > cnt:
                ok = False
            elif controlador.turno.upper() in {"TC", "MC"} and slots_des_tc > cnt:
                ok = False
        if not ok or num_turno == -1:
            patterns.append(ViolationPattern(TipoRestriccion.R3, idx_c, 1.0))
    return patterns

def _patterns_R4(individuo, entrada) -> list[ViolationPattern]:
    patterns = []
    controladores = individuo.getControladores()
    sector_ids = entrada._fast_sector_ids
    
    for idx_c, controlador in enumerate(controladores):
        p_val = 0.0
        if controlador.turno_noche != 0 and controlador.turno_asignado != -1:
            turno = individuo.getTurnos()[controlador.turno_asignado]
            x = 0
            for slot in _slots(turno):
                if slot.lower() not in sector_ids:
                    x += PENALIZACION
            if x:
                p_val += 1.0
                
        # Replicamos el check de la línea 421 de restrictions.py (c.turno_noche == idx)
        if controlador.turno_noche != 0:
            if sum(1 for c in controladores if c.turno_noche == idx_c) < 4:
                p_val += 1.0
                
        if p_val > 0:
            patterns.append(ViolationPattern(TipoRestriccion.R4, idx_c, p_val))
    return patterns

def _patterns_R5(turnos: list[str], parametros) -> list[ViolationPattern]:
    patterns = []
    t_max = parametros.getTiempoTrabMax() // parametros.getTamanoSlots()
    for idx_t, turno in enumerate(turnos):
        t = 0
        cnt = 0
        p_val = 0.0
        for slot in _slots(turno):
            if slot not in REST_SLOTS:
                cnt += 1
            else:
                if cnt > t_max:
                    if t == 0:
                        p_val += 1.0 + (cnt - t_max) * 0.025
                        t = 1
                    else:
                        p_val += 0.2
                cnt = 0
        if cnt > t_max:
            if t == 0:
                p_val += 1.0 + (cnt - t_max) * 0.025
            else:
                p_val += 0.2
        if p_val > 0:
            patterns.append(ViolationPattern(TipoRestriccion.R5, idx_t, p_val))
    return patterns

def _patterns_R6(individuo, entrada) -> list[ViolationPattern]:
    patterns = []
    resto = entrada.getTurno().getTl()[1] - entrada.getTurno().getTc()[1]
    inicio_corto = entrada.getTurno().getTc()[0]
    for idx_c, controlador in enumerate(individuo.getControladores()):
        if controlador.turno.upper() != "TC" or controlador.turno_asignado == -1:
            continue
        turno = individuo.getTurnos()[controlador.turno_asignado]
        slots = list(_slots(turno))
        zone = slots[-resto:] if inicio_corto == 0 else slots[:inicio_corto]
        t1 = 0
        p_val = 0.0
        for slot in zone:
            if slot not in REST_SLOTS:
                p_val += 1.0 if t1 == 0 else 0.05
                t1 = 1
        if p_val > 0:
            patterns.append(ViolationPattern(TipoRestriccion.R6, idx_c, p_val))
    return patterns

def _patterns_R7(turnos: list[str], parametros) -> list[ViolationPattern]:
    patterns = []
    ventana = (parametros.getTiempoTrabMax() + parametros.getTiempoDesPorTrabajo()) * 3 // parametros.getTamanoSlots()
    d_min = parametros.getTiempoDesPorTrabajo() // parametros.getTamanoSlots()
    t_max = parametros.getTiempoTrabMax() // parametros.getTamanoSlots()
    for idx_t, turno in enumerate(turnos):
        ds = tr = 0
        x = 0.0
        slots = list(_slots(turno))
        for j, slot in enumerate(slots):
            if slot == STRING_DESCANSO:
                ds += 1
            elif slot != STRING_NO_TURNO:
                tr += 1
            char_j = j * 3
            if char_j >= ventana and (ds + tr) * 3 >= ventana:
                leaving = slots[(char_j - ventana) // 3]
                if leaving == STRING_DESCANSO:
                    ds -= 1
                elif leaving != STRING_NO_TURNO:
                    tr -= 1
                if ds < d_min and tr > t_max:
                    x += PENALIZACION
        if x > 0:
            patterns.append(ViolationPattern(TipoRestriccion.R7, idx_t, 1.0 + x))
    return patterns

def _patterns_R8(turnos: list[str], mapa_afinidad: dict[str, set[str]], lista_sec) -> list[ViolationPattern]:
    patterns = []
    for idx_t, turno in enumerate(turnos):
        x = 0.0
        slots = list(_slots(turno))
        for current, nxt in zip(slots, slots[1:]):
            if current not in REST_SLOTS and nxt not in REST_SLOTS and current != nxt:
                if current.isupper() and nxt.isupper() and not comprobar_afinidad(current, nxt, mapa_afinidad):
                    x += PENALIZACION
        if x > 0:
            patterns.append(ViolationPattern(TipoRestriccion.R8, idx_t, 1.0 + x))
    return patterns

def _patterns_R9(turnos: list[str], parametros) -> list[ViolationPattern]:
    patterns = []
    t_min = parametros.getTiempoTrabMin() // parametros.getTamanoSlots()
    for idx_t, turno in enumerate(turnos):
        cnt = 0
        t1 = 0
        p_val = 0.0
        for slot in _slots(turno):
            if slot not in REST_SLOTS:
                cnt += 1
            else:
                if cnt < t_min and cnt != 0:
                    p_val += 1.0 if t1 == 0 else 0.05
                    t1 = 1
                cnt = 0
        if cnt < t_min and cnt != 0:
            p_val += 1.0 if t1 == 0 else 0.05
        if p_val > 0:
            patterns.append(ViolationPattern(TipoRestriccion.R9, idx_t, p_val))
    return patterns

def _patterns_R10(turnos: list[str], parametros) -> list[ViolationPattern]:
    patterns = []
    d_min = parametros.getTiempoDesMin() // parametros.getTamanoSlots()
    for idx_t, turno in enumerate(turnos):
        t1 = 0
        cnt = 0
        p_val = 0.0
        for slot in _slots(turno):
            if slot == STRING_DESCANSO:
                cnt += 1
            else:
                if cnt < d_min and cnt != 0 and slot != STRING_NO_TURNO:
                    p_val += 1.0 if t1 == 0 else 0.05
                    t1 = 1
                cnt = 0
        if p_val > 0:
            patterns.append(ViolationPattern(TipoRestriccion.R10, idx_t, p_val))
    return patterns

def _patterns_R11(turnos: list[str], parametros) -> list[ViolationPattern]:
    patterns = []
    p_min = parametros.getTiempoPosMin() // parametros.getTamanoSlots()
    for idx_t, turno in enumerate(turnos):
        t1 = 0
        cnt = 0
        prev = None
        p_val = 0.0
        for slot in _slots(turno):
            is_rest = slot in REST_SLOTS
            if is_rest and cnt == 0:
                pass
            elif is_rest and cnt < p_min:
                p_val += 1.0 if t1 == 0 else 0.05
                t1 = 1
            elif is_rest and cnt >= p_min:
                cnt = 0
            elif not is_rest:
                if prev is None:
                    cnt += 1
                elif slot == prev:
                    cnt += 1
                elif cnt == 0:
                    cnt += 1
                elif cnt < p_min:
                    p_val += 1.0 if t1 == 0 else 0.05
                    t1 = 1
                    cnt = 1
                else:
                    cnt = 1
            prev = slot
        if p_val > 0:
            patterns.append(ViolationPattern(TipoRestriccion.R11, idx_t, p_val))
    return patterns

def _patterns_R12(turnos: list[str], entrada, parametros) -> list[ViolationPattern]:
    patterns = []
    volumes = entrada._fast_volumes_by_id
    sector_by_id = entrada._fast_sector_by_id
    cache = entrada._fast_num_max_sectores_cache
    for idx_t, turno in enumerate(turnos):
        sectores = lista_de_sectores_turno(turno, sector_by_id)
        key = tuple(sector.id for sector in sectores)
        value = cache.get(key)
        if value is None:
            value = calculate(sectores, volumes)
            cache[key] = value
        if value > parametros.getNumSctrsMax():
            patterns.append(ViolationPattern(TipoRestriccion.R12, idx_t, 1.0))
    return patterns

def _patterns_R13(individuo) -> list[ViolationPattern]:
    patterns = []
    for idx_c, c in enumerate(individuo.getControladores()):
        if c.turno_asignado == -1:
            patterns.append(ViolationPattern(TipoRestriccion.R13, f"C_{idx_c}", 1.0))
            
    assigned = {c.turno_asignado for c in individuo.getControladores()}
    for idx_t in range(len(individuo.getTurnos())):
        if idx_t not in assigned:
            patterns.append(ViolationPattern(TipoRestriccion.R13, f"T_{idx_t}", 1.0))
    return patterns

def _patterns_R14(individuo) -> list[ViolationPattern]:
    patterns = []
    for idx_t, turno in enumerate(individuo.getTurnos()):
        work = 0
        rest = 0
        for slot in _slots(turno):
            if slot == STRING_DESCANSO:
                rest += 1
            elif slot != STRING_NO_TURNO:
                work += 1
                if rest:
                    break
        if work == 0 and rest:
            patterns.append(ViolationPattern(TipoRestriccion.R14, idx_t, 1.0))
    return patterns


# ==============================================================================
# MECANISMO CORE DEL ALGORITMO GLS
# ==============================================================================

def get_active_patterns_by_turn(individuo, entrada, parametros) -> list[ViolationPattern]:
    """Retorna todos los patrones activos, separando también en función de en que turno ocurren, escalados por su PESO correspondiente.
    El peso es el mismo que se utiliza en comprobaciones_en_paralelo().
    """
    _ensure_fast_cache(entrada)
    patterns = []
    patterns.extend(_patterns_R1(individuo, entrada))
    patterns.extend(_patterns_R2(individuo, entrada))
    patterns.extend(_patterns_R3(individuo, entrada, entrada.getTurno(), parametros))
    patterns.extend(_patterns_R4(individuo, entrada))
    patterns.extend(_patterns_R5(individuo.getTurnos(), parametros))
    patterns.extend(_patterns_R6(individuo, entrada))
    patterns.extend(_patterns_R7(individuo.getTurnos(), parametros))
    patterns.extend(_patterns_R8(individuo.getTurnos(), entrada.getMapaAfinidad(), entrada.getListaSectores()))
    patterns.extend(_patterns_R9(individuo.getTurnos(), parametros))
    patterns.extend(_patterns_R10(individuo.getTurnos(), parametros))
    patterns.extend(_patterns_R11(individuo.getTurnos(), parametros))
    patterns.extend(_patterns_R12(individuo.getTurnos(), entrada, parametros))
    patterns.extend(_patterns_R13(individuo))
    patterns.extend(_patterns_R14(individuo))
    
    # Se le aplica el peso configurado a cada pattern
    return [
        ViolationPattern(p.tipo, p.id_entidad, p.coi * PESO_POR_RESTRICCION[p.tipo.value])
        for p in patterns
    ]

def get_active_patterns(individuo, entrada, parametros) -> list[ViolationPattern]:
    """Retorna todos los patrones activos, escalados por su PESO correspondiente.
    El peso es el mismo que se utiliza en comprobaciones_en_paralelo().
    """
    _ensure_fast_cache(entrada)
    patterns = []

    for idx, value in enumerate(_checks(individuo, entrada, parametros)):
        patterns.append(ViolationPattern(TipoRestriccion(idx), idx, value * PESO_POR_RESTRICCION[idx]))
    return patterns

# Acordarse de penalty_max_observado y de W0 y el vector con R.f1 en gls.py
def get_active_patterns_and_CTA(individuo, entrada, parametros) -> list[ViolationPattern]:
    """Tiene en cuenta que el numero de controladores no contenga imaginarios"""
    _ensure_fast_cache(entrada)
    patterns = []

    for idx, value in enumerate(_checks(individuo, entrada, parametros)):
        patterns.append(ViolationPattern(TipoRestriccion(idx), idx, value * PESO_POR_RESTRICCION[idx]))
    
    c_req   = len(entrada.getControladores())
    tmn = len(individuo.getTurnos())

    if c_req >= tmn:
        patterns.append(ViolationPattern(TipoRestriccion.Rf1, 14, 0))
    else:
        f1 = 0.0
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

        value = 100/(f1**2)
        patterns.append(ViolationPattern(TipoRestriccion.Rf1, 14, value))

    return patterns


def compute_utility(pattern: ViolationPattern, penalizaciones: dict) -> float:
    """Calcula la utilidad de penalizar este patrón.
    Fórmula: util = I_i(s) / (1 + p_i)
    """
    key = (pattern.tipo, pattern.id_entidad)
    p_i = penalizaciones.get(key, 0.0)
    return pattern.coi / (1.0 + p_i)


def get_highest_utility_patterns(individuo, entrada, parametros, penalizaciones: dict) -> list[ViolationPattern]:
    """Obtiene los patrones activos con máxima utilidad."""
    activos = get_active_patterns(individuo, entrada, parametros) #CAMBIO
    if not activos:
        return []
        
    max_util = -1.0
    mejores = []
    
    for pat in activos:
        util = compute_utility(pat, penalizaciones)
        if util > max_util:
            max_util = util
            mejores = [(pat.tipo, pat.id_entidad)]
        elif math.isclose(util, max_util, rel_tol=1e-9):
            mejores.append((pat.tipo, pat.id_entidad))
    return mejores



def increment_penalties(patrones: list, penalizaciones: dict) -> None:
    """Añade 1 a la penalización de cada patrón que haya dado la máxima utilidad,
    hasta un máximo de MAX_PENALTY.
    """
    for key in patrones:
        current = penalizaciones.get(key, 0.0)
        penalizaciones[key] = current + 1.0


def increment_all_active_penalties(individuo, entrada, parametros, penalizaciones: dict) -> None:
    """Incrementa en +1 la penalización de TODOS los patrones activos en la solución actual.

    Se usa cuando el fitness no incluye las restricciones laborales directamente
    (modo unificado), por lo que el GLS debe penalizar todos los incumplimientos
    activos, no solo el de mayor utilidad.

    El incremento es +1 (plano), igual que increment_penalties. La diferenciación
    por severidad ya la proporciona coi en compute_penalty_sum a través de p_i * coi:
    patrones más graves tienen mayor coi y por tanto mayor peso en la función
    aumentada h, aunque p_i crezca al mismo ritmo para todos.
    """
    activos = get_active_patterns(individuo, entrada, parametros)
    for pat in activos:
        key = (pat.tipo, pat.id_entidad)
        current = penalizaciones.get(key, 0.0)
        penalizaciones[key] = current + 1.0


def compute_penalty_sum(individuo, entrada, parametros, penalizaciones: dict) -> float:
    """Calcula Σ(℘ᵢ · Iᵢ(t)). 
    Suma total del coste extra de las penalizaciones en el individuo actual.
    """
    if not penalizaciones:
        return 0.0
    activos = get_active_patterns(individuo, entrada, parametros)
    total = 0.0
    for pat in activos:
        key = (pat.tipo, pat.id_entidad)
        p_i = penalizaciones.get(key, 0.0)
        total += p_i * pat.coi
    return total
