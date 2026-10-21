"""move_sector_repair.py – Operador de movimiento especializado en reducción y reparación de sectores (R12) y permanencia mínima (R11).

Combina tres mecanismos complementarios:
1. movimiento_reparacion_permanencia_minima:
   Localiza turnos con micro-bloques de trabajo en posición (< tiempoPosMin, típicamente < 15 min / 3 slots)
   y los transfiere o unifica con turnos que ya operan en dicho sector o con descansos, erradicando las
   violaciones de R11.

2. movimiento_reparacion_sectores:
   Localiza turnos infractores de R12 (> num_sctrs_max), identifica su sector residual/minoritario
   y transfiere ese intervalo a un turno receptor compatible (que ya posea ese sector o que tenga descanso),
   eliminando la presencia del sector intruso en el dador sin crear nuevas violaciones de R11.

3. movimiento_sector_safe:
   Variante de move15 equipada con un 'cortafuegos' de doble protección que descarta cualquier intercambio
   que aumente el número de sectores distintos (R12) o genere micro-bloques de posición (< 3 slots, R11).
"""

from __future__ import annotations

from ..constants import STRING_DESCANSO, STRING_NO_TURNO
from ..java_random import JavaRandom
from ..models import Solucion
from .. import move15, restrictions


# ---------------------------------------------------------------------------
# Helpers de conteo e inspección de sectores (R12) y permanencia mínima (R11)
# ---------------------------------------------------------------------------

def _count_sectors(turno: str, entrada) -> int:
    """Calcula el número efectivo de sectores distintos en un turno, coincidiendo con R12."""
    restrictions._ensure_fast_cache(entrada)
    volumes = entrada._fast_volumes_by_id
    sector_by_id = entrada._fast_sector_by_id
    cache = entrada._fast_num_max_sectores_cache
    sectores = restrictions.lista_de_sectores_turno(turno, sector_by_id)
    key = tuple(sector.id for sector in sectores)
    value = cache.get(key)
    if value is None:
        value = restrictions.calculate(sectores, volumes)
        cache[key] = value
    return value


def _count_r11_violations_turno(turno: str, p_min: int) -> float:
    """Calcula las infracciones de permanencia mínima en posición (R11) para un único turno."""
    p = 0.0
    t1 = 0
    cnt = 0
    prev = None
    for i in range(0, len(turno), 3):
        slot = turno[i: i + 3]
        is_rest = slot in restrictions.REST_SLOTS
        if is_rest:
            if 0 < cnt < p_min:
                p += 1 if t1 == 0 else 0.05
                t1 = 1
            cnt = 0
        else:
            if prev is None:
                cnt = 1
            elif slot == prev:
                cnt += 1
            else:
                if 0 < cnt < p_min:
                    p += 1 if t1 == 0 else 0.05
                    t1 = 1
                cnt = 1
        prev = slot
    if 0 < cnt < p_min:
        p += 1 if t1 == 0 else 0.05
    return p


def _get_sector_slot_counts(turno: str) -> dict[str, int]:
    """Retorna un diccionario {sector_id_lower: total_slots} para un turno."""
    counts: dict[str, int] = {}
    for i in range(0, len(turno), 3):
        slot = turno[i: i + 3]
        if slot not in restrictions.REST_SLOTS:
            s_lower = slot.lower()
            counts[s_lower] = counts.get(s_lower, 0) + 1
    return counts


def _get_contiguous_blocks_of_sector(turno: str, target_sector_lower: str) -> list[tuple[int, int]]:
    """Devuelve los rangos [inicio_char, fin_char] de los bloques contiguos de un sector."""
    blocks: list[tuple[int, int]] = []
    in_block = False
    start = 0
    t_len = len(turno)
    for i in range(0, t_len, 3):
        slot = turno[i: i + 3]
        if slot.lower() == target_sector_lower:
            if not in_block:
                start = i
                in_block = True
        else:
            if in_block:
                blocks.append((start, i))
                in_block = False
    if in_block:
        blocks.append((start, t_len))
    return blocks


def _get_r11_violating_blocks(turno: str, p_min: int) -> list[tuple[int, int, str, int]]:
    """Devuelve los bloques [inicio_char, fin_char, sector, num_slots] que incumplen R11 (< p_min)."""
    violaciones: list[tuple[int, int, str, int]] = []
    in_work = False
    start = 0
    curr_sector = ""
    cnt = 0
    t_len = len(turno)

    for i in range(0, t_len, 3):
        slot = turno[i: i + 3]
        if slot not in restrictions.REST_SLOTS:
            if not in_work:
                in_work = True
                start = i
                curr_sector = slot
                cnt = 1
            elif slot == curr_sector:
                cnt += 1
            else:
                if cnt < p_min:
                    violaciones.append((start, i, curr_sector, cnt))
                start = i
                curr_sector = slot
                cnt = 1
        else:
            if in_work:
                if cnt < p_min:
                    violaciones.append((start, i, curr_sector, cnt))
                in_work = False
                cnt = 0
                curr_sector = ""

    if in_work and cnt < p_min:
        violaciones.append((start, t_len, curr_sector, cnt))

    return violaciones


# ---------------------------------------------------------------------------
# 1. Operador de Reparación de Permanencia Mínima en Posición (R11)
# ---------------------------------------------------------------------------

def movimiento_reparacion_permanencia_minima(
    sol: Solucion,
    entrada,
    parametros,
    parametros_alg,
    rng: JavaRandom,
) -> Solucion:
    """Detecta micro-bloques de trabajo (< p_min slots) y los unifica o transfiere."""
    turnos = sol.getTurnos()
    n_turnos = len(turnos)
    p_min = parametros.getTiempoPosMin() // parametros.getTamanoSlots()
    max_sec = parametros.getNumSctrsMax()

    r11_counts = [_count_r11_violations_turno(t, p_min) for t in turnos]
    sector_counts = [_count_sectors(t, entrada) for t in turnos]
    violadores = [i for i, c in enumerate(r11_counts) if c > 0]

    if not violadores:
        return sol

    # Barajar orden de turnos infractores de R11
    dadores = list(violadores)
    for i in range(len(dadores) - 1, 0, -1):
        j = rng.nextInt(i + 1)
        dadores[i], dadores[j] = dadores[j], dadores[i]

    for dador in dadores:
        t_dador = turnos[dador]
        micro_blocks = _get_r11_violating_blocks(t_dador, p_min)
        if not micro_blocks:
            continue

        for ini, fin, sec_id, k_slots in micro_blocks:
            # 1. Intentar intercambiar el micro-bloque exacto [ini, fin] con un receptor
            #    que ya opere en sec_id en momentos adyacentes o tenga descanso
            candidatos_receptores: list[int] = []
            for r in range(n_turnos):
                if r == dador:
                    continue
                t_rec = turnos[r]
                if STRING_NO_TURNO in t_rec[ini:fin]:
                    continue

                # ¿El receptor tiene sec_id adyacente o descanso?
                sec_lower = sec_id.lower()
                slot_before = t_rec[ini - 3: ini].lower() if ini >= 3 else ""
                slot_after = t_rec[fin: fin + 3].lower() if fin + 3 <= len(t_rec) else ""
                rec_segment = t_rec[ini: fin]

                es_afin = (
                    slot_before == sec_lower
                    or slot_after == sec_lower
                    or all(ch == '1' for ch in rec_segment)
                    or sec_lower in _get_sector_slot_counts(t_rec)
                )
                if es_afin:
                    candidatos_receptores.append(r)

            # Probar candidatos
            for receptor in candidatos_receptores:
                changed = move15.change_cont(sol, dador, receptor, ini, fin, entrada)
                if changed is not None:
                    new_r11_d = _count_r11_violations_turno(changed[0], p_min)
                    new_r11_r = _count_r11_violations_turno(changed[1], p_min)
                    new_s_d = _count_sectors(changed[0], entrada)
                    new_s_r = _count_sectors(changed[1], entrada)

                    # Aceptar si se reduce R11 globalmente sin desbordar R12
                    if (
                        (new_r11_d + new_r11_r < r11_counts[dador] + r11_counts[receptor])
                        and (new_s_d <= max(sector_counts[dador], max_sec))
                        and (new_s_r <= max(sector_counts[receptor], max_sec))
                    ):
                        return move15.do_change(changed, sol, dador, receptor, ini, fin)

            # 2. Si no fue posible, intentar extender el intervalo a un bloque estándar de p_min slots
            #    (para transferir un bloque completo de al menos 15 min sin dejar residuos)
            t_len = len(t_dador)
            pos_fin_ext = min(ini + p_min * 3, t_len)
            if pos_fin_ext - ini >= p_min * 3:
                for receptor in range(n_turnos):
                    if receptor == dador:
                        continue
                    t_rec = turnos[receptor]
                    if STRING_NO_TURNO in t_rec[ini:pos_fin_ext]:
                        continue
                    changed = move15.change_cont(sol, dador, receptor, ini, pos_fin_ext, entrada)
                    if changed is not None:
                        new_r11_d = _count_r11_violations_turno(changed[0], p_min)
                        new_r11_r = _count_r11_violations_turno(changed[1], p_min)
                        new_s_d = _count_sectors(changed[0], entrada)
                        new_s_r = _count_sectors(changed[1], entrada)

                        if (
                            (new_r11_d + new_r11_r <= r11_counts[dador] + r11_counts[receptor])
                            and (new_r11_d < r11_counts[dador] or new_r11_r < r11_counts[receptor])
                            and (new_s_d <= max(sector_counts[dador], max_sec))
                            and (new_s_r <= max(sector_counts[receptor], max_sec))
                        ):
                            return move15.do_change(changed, sol, dador, receptor, ini, pos_fin_ext)

    return sol


# ---------------------------------------------------------------------------
# 2. Operador de Reparación Dirigida de Sectores (R12)
# ---------------------------------------------------------------------------

def movimiento_reparacion_sectores(
    sol: Solucion,
    entrada,
    parametros,
    parametros_alg,
    rng: JavaRandom,
) -> Solucion:
    """Busca un turno con exceso de sectores y transfiere su sector minoritario."""
    turnos = sol.getTurnos()
    n_turnos = len(turnos)
    max_sec = parametros.getNumSctrsMax()
    p_min = parametros.getTiempoPosMin() // parametros.getTamanoSlots()

    # Precalcular conteo de sectores y R11 por turno
    sector_counts = [_count_sectors(t, entrada) for t in turnos]
    r11_counts = [_count_r11_violations_turno(t, p_min) for t in turnos]
    violadores = [i for i, c in enumerate(sector_counts) if c > max_sec]

    if not violadores:
        return sol

    # Barajar orden de turnos infractores
    dadores = list(violadores)
    for i in range(len(dadores) - 1, 0, -1):
        j = rng.nextInt(i + 1)
        dadores[i], dadores[j] = dadores[j], dadores[i]

    for dador in dadores:
        t_dador = turnos[dador]
        slot_counts = _get_sector_slot_counts(t_dador)
        if not slot_counts:
            continue

        # Ordenar sectores de menor a mayor presencia (priorizar eliminar el fragmento más pequeño)
        sorted_sectors = sorted(slot_counts.items(), key=lambda item: item[1])

        for sec_minor, _ in sorted_sectors:
            blocks = _get_contiguous_blocks_of_sector(t_dador, sec_minor)
            if not blocks:
                continue

            for ini, fin in blocks:
                # Receptores: clasificar entre prioritarios (ya trabajan en sec_minor o tienen hueco) y otros
                prioritarios: list[int] = []
                otros: list[int] = []

                for r in range(n_turnos):
                    if r == dador:
                        continue
                    t_rec = turnos[r]
                    if STRING_NO_TURNO in t_rec[ini:fin]:
                        continue

                    rec_counts = _get_sector_slot_counts(t_rec)
                    if sec_minor in rec_counts or sector_counts[r] < max_sec:
                        prioritarios.append(r)
                    else:
                        otros.append(r)

                candidatos = prioritarios + otros
                for receptor in candidatos:
                    changed = move15.change_cont(sol, dador, receptor, ini, fin, entrada)
                    if changed is not None:
                        new_c_dador = _count_sectors(changed[0], entrada)
                        new_c_rec = _count_sectors(changed[1], entrada)
                        new_r11_d = _count_r11_violations_turno(changed[0], p_min)
                        new_r11_r = _count_r11_violations_turno(changed[1], p_min)

                        # Aceptar si el dador reduce sectores, el receptor no se desborda y R11 no empeora
                        s_ok = new_c_dador < sector_counts[dador] and (
                            new_c_rec <= max_sec or new_c_rec <= sector_counts[receptor]
                        )
                        r11_ok = (new_r11_d + new_r11_r <= r11_counts[dador] + r11_counts[receptor])

                        if s_ok and r11_ok:
                            return move15.do_change(changed, sol, dador, receptor, ini, fin)

    return sol


# ---------------------------------------------------------------------------
# 3. Operador Sector-Safe y R11-Safe (Move15 con Cortafuegos Dual)
# ---------------------------------------------------------------------------

def movimiento_sector_safe(
    sol: Solucion,
    g_max: int,
    g_min: int,
    entrada,
    parametros,
    parametros_alg,
    rng: JavaRandom,
    max_intentos: int = 40,
) -> Solucion:
    """Move15 pero descartando swaps que aumenten sectores (R12) o generen micro-bloques (R11)."""
    if move15.grid is None:
        move15.init_grid(sol, parametros, parametros_alg, entrada)
    grid = move15.grid
    g_min = parametros_alg.SA.move15_min
    g_max = parametros_alg.SA.move15_max
    max_sec = parametros.getNumSctrsMax()
    p_min = parametros.getTiempoPosMin() // parametros.getTamanoSlots()
    asignacion = sol.getTurnos()
    n_turnos = len(asignacion)

    sectores_act = [_count_sectors(t, entrada) for t in asignacion]
    r11_act = [_count_r11_violations_turno(t, p_min) for t in asignacion]

    intentos = 0
    excluded_ctrl1: set[int] = set()
    while len(excluded_ctrl1) < n_turnos and intentos < max_intentos:
        ctrl1 = move15.next_int_excluding(rng, 0, n_turnos - 1, excluded_ctrl1)
        excluded_ctrl1.add(ctrl1)
        excluded_slots: set[int] = set()
        while len(excluded_slots) < g_max - g_min + 1 and intentos < max_intentos:
            n_slots = move15.next_int_excluding(rng, g_min, g_max, excluded_slots)
            excluded_slots.add(n_slots)
            if len(grid) - 1 - n_slots < 0:
                continue
            slot = rng.randint(0, len(grid) - 1 - n_slots)
            intervalo = (grid[slot], grid[slot + n_slots])
            excluded_ctrl2 = set(excluded_ctrl1)
            while len(excluded_ctrl2) < n_turnos and intentos < max_intentos:
                ctrl2 = move15.next_int_excluding(rng, 0, n_turnos - 1, excluded_ctrl2)
                excluded_ctrl2.add(ctrl2)
                intentos += 1
                changed = move15.change_cont(sol, ctrl1, ctrl2, intervalo[0], intervalo[1], entrada)
                if changed is not None:
                    new_s1 = _count_sectors(changed[0], entrada)
                    new_s2 = _count_sectors(changed[1], entrada)
                    new_r11_1 = _count_r11_violations_turno(changed[0], p_min)
                    new_r11_2 = _count_r11_violations_turno(changed[1], p_min)

                    # Cortafuegos dual:
                    # 1. No crear nuevas infracciones de sectores si ya estaban en el límite
                    c1_s_ok = (new_s1 <= max(sectores_act[ctrl1], max_sec))
                    c2_s_ok = (new_s2 <= max(sectores_act[ctrl2], max_sec))

                    # 2. No incrementar infracciones de permanencia mínima
                    c1_r11_ok = (new_r11_1 <= max(r11_act[ctrl1], 0))
                    c2_r11_ok = (new_r11_2 <= max(r11_act[ctrl2], 0))

                    if c1_s_ok and c2_s_ok and c1_r11_ok and c2_r11_ok:
                        return move15.do_change(changed, sol, ctrl1, ctrl2, intervalo[0], intervalo[1])

    # Si se agotan los intentos seguros, usar move15 estándar para no detener la búsqueda
    return move15.movimiento(sol, g_max, g_min, entrada, parametros, parametros_alg, rng)


# ---------------------------------------------------------------------------
# 4. Operador Maestro Combinado
# ---------------------------------------------------------------------------

def movimiento(
    sol: Solucion,
    g_max: int,
    g_min: int,
    entrada,
    parametros,
    parametros_alg,
    rng: JavaRandom,
) -> Solucion:
    """Función de movimiento principal: repara activamente R11 y R12 y realiza búsqueda sector-safe."""
    p_min = parametros.getTiempoPosMin() // parametros.getTamanoSlots()
    max_sec = parametros.getNumSctrsMax()
    turnos = sol.getTurnos()

    hay_r11 = any(_count_r11_violations_turno(t, p_min) > 0 for t in turnos)
    hay_r12 = any(_count_sectors(t, entrada) > max_sec for t in turnos)

    r = rng.random()
    # Si hay infracciones de R11 (permanencia mínima), priorizar repararlas
    if hay_r11 and r < 0.40:
        sol_reparada_r11 = movimiento_reparacion_permanencia_minima(sol, entrada, parametros, parametros_alg, rng)
        if sol_reparada_r11 is not sol:
            return sol_reparada_r11

    # Si hay infracciones de R12 (dispersión de sectores), repararlas
    if hay_r12 and r < 0.75:
        sol_reparada_r12 = movimiento_reparacion_sectores(sol, entrada, parametros, parametros_alg, rng)
        if sol_reparada_r12 is not sol:
            return sol_reparada_r12

    # En el resto de casos, exploración segura con cortafuegos dual
    return movimiento_sector_safe(sol, g_max, g_min, entrada, parametros, parametros_alg, rng)
