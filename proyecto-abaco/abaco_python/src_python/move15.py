from __future__ import annotations

from .constants import STRING_DESCANSO, STRING_NO_TURNO
from .java_random import JavaRandom
from .models import Solucion

# =============================================================================
# CORRESPONDENCIA CON CÓDIGO JAVA
# =============================================================================
# Archivo Java:
#   - src/main/algorithms/simulatedAnnealing/moves/Move15.java
#       → init_grid(), movimiento(), change_cont(), do_change(),
#         comprobar_nucleos(), next_int_excluding()
#
# Move15 es el único movimiento activo en el flujo SA actual
# (configurado vía "movimientosEntorno=movimiento15" en algorithm.properties).
# Los demás moves (Move1..8, Move12, Move17) no están implementados en Python.
# =============================================================================

grid: list[int] | None = None


def init_grid(sol: Solucion, parametros, parametros_alg, entrada) -> list[int]:
    global grid
    aux = [entrada.getSlotMomentoActual() * 3, len(sol.getTurnos()[0])]
    for turno in sol.getTurnos():
        for i in range((entrada.getSlotMomentoActual() * 3) + 3, len(turno) - 1, 3):
            if turno[i - 3 : i] != turno[i : i + 3] and i not in aux:
                aux.append(i)
    aux.sort()
    grid = aux
    return grid


def movimiento(sol: Solucion, g_max: int, g_min: int, entrada, parametros, parametros_alg, rng: JavaRandom) -> Solucion:
    global grid
    if grid is None:
        init_grid(sol, parametros, parametros_alg, entrada)
    g_min = parametros_alg.SA.move15_min
    g_max = parametros_alg.SA.move15_max
    sol2 = sol.clone()
    asignacion = sol.getTurnos()
    excluded_ctrl1: set[int] = set()
    while len(excluded_ctrl1) < len(asignacion):
        ctrl1 = next_int_excluding(rng, 0, len(asignacion) - 1, excluded_ctrl1)
        excluded_ctrl1.add(ctrl1)
        excluded_slots: set[int] = set()
        while len(excluded_slots) < g_max - g_min + 1:
            n_slots = next_int_excluding(rng, g_min, g_max, excluded_slots)
            excluded_slots.add(n_slots)
            if len(grid) - 1 - n_slots < 0:
                continue
            slot = rng.randint(0, len(grid) - 1 - n_slots)
            intervalo = (grid[slot], grid[slot + n_slots])
            excluded_ctrl2 = set(excluded_ctrl1)
            while len(excluded_ctrl2) < len(asignacion):
                ctrl2 = next_int_excluding(rng, 0, len(asignacion) - 1, excluded_ctrl2)
                excluded_ctrl2.add(ctrl2)
                changed = change_cont(sol, ctrl1, ctrl2, intervalo[0], intervalo[1], entrada)
                if changed is not None:
                    return do_change(changed, sol, ctrl1, ctrl2, intervalo[0], intervalo[1])
    return sol2


def next_int_excluding(rng: JavaRandom, ini: int, fin: int, excluded: set[int]) -> int:
    if excluded is None:
        return ini + rng.nextInt(fin - ini + 1)
    exclusions_in_range = 0
    excluded_values = list(excluded)
    for value in excluded_values:
        if ini <= value <= fin:
            exclusions_in_range += 1

    c = rng.nextInt(fin - exclusions_in_range - ini + 1)
    res = ini - 1
    while True:
        res += 1
        otra_vuelta = True
        while otra_vuelta:
            otra_vuelta = False
            for value in excluded_values:
                if res == value:
                    res += 1
                    otra_vuelta = True
        c -= 1
        if c < 0:
            return res


def change_cont(sol: Solucion, dador: int, receptor: int, inicio: int, fin: int, entrada) -> list[str] | None:
    individuo = sol.getTurnos()
    ctrl_vago = individuo[dador]
    ctrl_p = individuo[receptor]
    cadena = ctrl_vago[inicio:fin]
    cadena_p = ctrl_p[inicio:fin]
    if STRING_NO_TURNO in cadena or STRING_NO_TURNO in cadena_p:
        return None
    ctrl_vago2 = ctrl_vago[:inicio] + cadena_p + ctrl_vago[fin:]
    ctrl_p2 = ctrl_p[:inicio] + cadena + ctrl_p[fin:]
    if not comprobar_nucleos(cadena, ctrl_p, entrada) or not comprobar_nucleos(ctrl_vago, cadena_p, entrada):
        return None
    return [ctrl_vago2, ctrl_p2]


def do_change(changed: list[str], individuo: Solucion, dador: int, receptor: int, inicio: int, fin: int) -> Solucion:
    """
    Equivalente a Move15.DoChange1() en Java.
    Aplica el intercambio entre dador y receptor. Si nControladores != nTurnos
    y el turno del dador queda vacío (solo descansos/no-turno), intenta reasignar
    su controlador o eliminarlo con reajuste de índices.
    """
    turnos = list(individuo.getTurnos())
    turnos[dador] = changed[0]
    turnos[receptor] = changed[1]

    cs = [c.clone() for c in individuo.getControladores()]

    if len(cs) != len(individuo.getTurnos()):
        # ¿El turno del dador quedó solo con '1' y '0' (descanso/no-turno)?
        es_descanso = all(c in ('1', '0') for c in changed[0])

        if es_descanso:
            print("Eliminando Turno")
            asignado = False
            for i, ctrl in enumerate(cs):
                if ctrl.getTurnoAsignado() == dador:
                    resultado = _asignar_controlador(i, dador, cs, changed[0], turnos)
                    if resultado is not None:
                        cs, turnos = resultado
                        asignado = True
                    break

            if not asignado:
                # Reajustar índices y eliminar el turno vacío
                for ctrl in cs:
                    if ctrl.getTurnoAsignado() > dador:
                        ctrl.setTurnoAsignado(ctrl.getTurnoAsignado() - 1)
                turnos.pop(dador)

            result = individuo.clone()
            result.setControladores(cs)
            result.setTurnos(turnos)
            return result

    result = individuo.clone()
    result.setControladores(cs)
    result.setTurnos(turnos)
    return result


def _asignar_controlador(
    pos_ctrl: int, dador: int, cs: list, turno_vacio: str, turnos: list[str]
) -> tuple | None:
    """
    Equivalente a Move15.asignarControlador() en Java.
    Intenta reasignar el controlador en pos_ctrl a otro turno existente,
    eliminando el turno dador vacío. Devuelve (cs, turnos) o None.
    """
    posiciones_zeros = [
        i for i in range(0, len(turno_vacio), 3)
        if turno_vacio[i:i + 3].upper() == STRING_NO_TURNO.upper()
    ]
    aux = [ctrl.getTurnoAsignado() for ctrl in cs]

    if not posiciones_zeros:
        return _modificar_sin_zeros(cs, dador, aux, turnos, pos_ctrl)

    max_cnt = 0
    mejor_pos = -1
    for i, turno in enumerate(turnos):
        if i in aux:
            continue
        cnt = sum(
            1 for p in posiciones_zeros
            if turno[p:p + 3].upper() in {STRING_NO_TURNO.upper(), STRING_DESCANSO.upper()}
        )
        if cnt == len(posiciones_zeros):
            # Java asigna el indice original del turno receptor antes de eliminar
            # el dador; replicamos ese comportamiento aunque el indice se desplace.
            for ctrl in cs:
                if ctrl.getTurnoAsignado() > dador:
                    ctrl.setTurnoAsignado(ctrl.getTurnoAsignado() - 1)
            cs[pos_ctrl].setTurnoAsignado(i)
            return cs, [t for j, t in enumerate(turnos) if j != dador]
        elif cnt >= max_cnt:
            max_cnt = cnt
            mejor_pos = i

    t = _repartir_trabajo(mejor_pos, posiciones_zeros, turnos, dador)
    if t is None:
        return None

    for ctrl in cs:
        if ctrl.getTurnoAsignado() > dador:
            ctrl.setTurnoAsignado(ctrl.getTurnoAsignado() - 1)
    cs[pos_ctrl].setTurnoAsignado(mejor_pos)
    return cs, [s for j, s in enumerate(t) if j != dador]


def _modificar_sin_zeros(cs: list, dador: int, aux: list, turnos: list[str], pos_ctrl: int) -> tuple | None:
    """Equivalente a Move15.modificarSinZeros() en Java."""
    for ctrl in cs:
        if ctrl.getTurnoAsignado() > dador:
            ctrl.setTurnoAsignado(ctrl.getTurnoAsignado() - 1)
    for j in range(len(cs)):
        if j not in aux:
            cs[pos_ctrl].setTurnoAsignado(j)
            break
    return cs, [t for i, t in enumerate(turnos) if i != dador]


def _repartir_trabajo(
    pos_aceptador: int, posiciones_zeros: list, turnos_orig: list[str], pos_vacio: int
) -> list[str] | None:
    """Equivalente a Move15.repartirTrabajo() en Java."""
    turnos = list(turnos_orig)
    ta = list(turnos[pos_aceptador])

    for i, turno_str in enumerate(turnos):
        if i == pos_aceptador or i == pos_vacio:
            continue
        t = list(turno_str)
        for p in posiciones_zeros:
            seg_a = "".join(ta[p:p + 3])
            seg_t = "".join(t[p:p + 3])
            if seg_a.upper() == STRING_DESCANSO.upper():
                ta[p:p + 3] = list(STRING_NO_TURNO)
            if (seg_a.upper() not in {STRING_NO_TURNO.upper(), STRING_DESCANSO.upper()}
                    and seg_t.upper() == STRING_DESCANSO.upper()):
                t[p:p + 3] = list(seg_a)
                ta[p:p + 3] = list(STRING_NO_TURNO)
                turnos[i] = "".join(t)

    for p in posiciones_zeros:
        if "".join(ta[p:p + 3]).upper() not in {STRING_NO_TURNO.upper(), STRING_DESCANSO.upper()}:
            return None

    turnos[pos_aceptador] = "".join(ta)
    return turnos


def comprobar_nucleos(cad: str, con_p: str, entrada) -> bool:
    if len(entrada.getNucleosAbiertos()) == 1:
        return True
    sectores_abiertos = entrada.getListaSectoresAbiertos()
    for cadena in [cad, con_p]:
        correcto = False
        for _nucleo in entrada.getNucleosAbiertos():
            ok = True
            for i in range(0, len(cadena), 3):
                slot = cadena[i : i + 3]
                if slot.lower() not in {STRING_DESCANSO, STRING_NO_TURNO}:
                    if not any(slot.lower() == sector.id.lower() for sector in sectores_abiertos):
                        ok = False
                        break
            if ok:
                correcto = True
                break
        if not correcto:
            return False
    return True


# =============================================================================
# OPERADORES RUIN & RECREATE — diversificación para GLS
# =============================================================================
#
# Ambas funciones operan a nivel de SLOT INDIVIDUAL (bloques de 3 chars), no
# a nivel de intervalo de rejilla. Esto garantiza que el intercambio nunca
# produce desalineaciones en la cadena de turno (cada slot tiene exactamente
# 3 caracteres independientemente de la longitud del bloque de rejilla).
#
# Restricción fundamental respetada en ambas versiones:
#   - Las posiciones con STRING_NO_TURNO nunca se mueven ni reciben otros slots.
#     Estas posiciones marcan el tiempo fuera de la ventana del turno y son fijas.
#
# Cuándo usarlas:
#   Se activan desde el bucle GLS cuando la condición de diversificación detecta
#   estancamiento prolongado (porcent_mejora < umbral durante N ciclos seguidos).
# =============================================================================


def _active_slot_indices(turno: str) -> list[int]:
    """Devuelve los índices de slot (base-0) que NO son STRING_NO_TURNO."""
    return [
        i for i in range(len(turno) // 3)
        if turno[i * 3: i * 3 + 3] != STRING_NO_TURNO
    ]


def ruin_and_recreate_intra(
    sol: Solucion,
    rng: JavaRandom,
    p_destroy: float = 0.3,
    n_slots_to_shuffle: int = 4,
    entrada=None,
) -> Solucion:
    """Operador Ruin & Recreate intra-turno.

    Para cada turno de la solución, con probabilidad ``p_destroy``, selecciona
    ``n_slots_to_shuffle`` slots activos al azar y permuta su contenido dentro
    del MISMO turno. El multiconjunto de slots de cada turno no cambia:
    solo se reordena su posición en la cadena.

    Args:
        sol                : Solución original (no se modifica in-place).
        rng                : Generador de números aleatorios.
        p_destroy          : Probabilidad de aplicar la permutación a cada turno.
                             Recomendado: 0.2 – 0.4 (no destruir demasiado a la vez).
        n_slots_to_shuffle : Número de slots a permutar por turno. Se acota
                             automáticamente al número de slots activos disponibles.
        entrada            : Objeto Entrada (reservado para validación futura;
                             actualmente no se usa dentro de esta función).

    Returns:
        Nueva Solucion con los turnos perturbados. Si ningún turno es elegido,
        se devuelve ``sol`` sin clonar.
    """
    turnos = list(sol.getTurnos())
    modified = False

    for idx_t in range(len(turnos)):
        if rng.random() >= p_destroy:
            continue

        turno = turnos[idx_t]
        activos = _active_slot_indices(turno)

        if len(activos) < 2:
            continue  # no se puede permutar con menos de 2 slots activos

        # Cuántos slots se van a permutar
        k = min(n_slots_to_shuffle, len(activos))
        if k < 2:
            continue

        # Seleccionar k posiciones aleatorias sin repetición del pool de activos
        pool = list(activos)
        elegidos = []
        for _ in range(k):
            idx = rng.nextInt(len(pool))
            elegidos.append(pool.pop(idx))

        # Extraer los slots en esas posiciones
        contenidos = [turno[p * 3: p * 3 + 3] for p in elegidos]

        # Mezclar los contenidos (Fisher-Yates con el RNG propio)
        for i in range(len(contenidos) - 1, 0, -1):
            j = rng.nextInt(i + 1)
            contenidos[i], contenidos[j] = contenidos[j], contenidos[i]

        # Reconstruir el turno con los slots permutados
        t_chars = list(turno)
        for pos, slot_content in zip(elegidos, contenidos):
            t_chars[pos * 3: pos * 3 + 3] = list(slot_content)

        turnos[idx_t] = "".join(t_chars)
        modified = True

    if not modified:
        return sol

    result = sol.clone()
    result.setControladores([c.clone() for c in sol.getControladores()])
    result.setTurnos(turnos)
    return result


def ruin_and_recreate_inter(
    sol: Solucion,
    rng: JavaRandom,
    p_destroy: float = 0.3,
    n_slots_to_swap: int = 4,
    max_receptor_attempts: int = 5,
    entrada=None,
) -> Solucion:
    """Operador Ruin & Recreate inter-turno.

    Para cada turno ``dador`` seleccionado (con probabilidad ``p_destroy``),
    elige aleatoriamente un turno ``receptor`` distinto y permuta
    ``n_slots_to_swap`` slots entre los dos turnos.

    Los slots intercambiados se seleccionan sobre las posiciones que son
    activas (no STRING_NO_TURNO) en AMBOS turnos simultáneamente, de modo
    que ninguno de los dos recibe un slot en una posición que le estaba
    vetada.

    A diferencia de ``move15``, el intercambio puede involucrar slots
    NO contiguos y más de un par a la vez, lo que produce perturbaciones
    mucho más grandes y mejora la diversificación.

    Args:
        sol                  : Solución original (no se modifica in-place).
        rng                  : Generador de números aleatorios.
        p_destroy            : Probabilidad de que un turno sea elegido como
                               dador. Recomendado: 0.2 – 0.4.
        n_slots_to_swap      : Número máximo de pares de slots a intercambiar
                               por dador. Se acota al número de posiciones
                               comunes disponibles.
        max_receptor_attempts: Intentos para encontrar un receptor que tenga
                               al menos 2 posiciones comunes con el dador.
        entrada              : Objeto Entrada (reservado para validación futura).

    Returns:
        Nueva Solucion con los pares de turnos perturbados. Si no se
        encuentra ningún intercambio válido, devuelve ``sol`` sin clonar.
    """
    turnos = list(sol.getTurnos())
    n_turnos = len(turnos)
    if n_turnos < 2:
        return sol

    modified = False

    for idx_dador in range(n_turnos):
        if rng.random() >= p_destroy:
            continue

        activos_dador = _active_slot_indices(turnos[idx_dador])
        if len(activos_dador) < 2:
            continue

        # Buscar un receptor con posiciones comunes suficientes
        receptor_encontrado = False
        excluidos: set[int] = {idx_dador}

        for _ in range(max_receptor_attempts):
            if len(excluidos) >= n_turnos:
                break  # ya probamos todos los turnos

            # Elegir receptor al azar excluyendo los ya probados
            idx_receptor = next_int_excluding(rng, 0, n_turnos - 1, excluidos)
            excluidos.add(idx_receptor)

            activos_receptor = _active_slot_indices(turnos[idx_receptor])

            # Posiciones activas en AMBOS turnos (intercambio siempre válido)
            comunes = sorted(set(activos_dador) & set(activos_receptor))

            if len(comunes) < 2:
                continue  # este receptor no sirve

            receptor_encontrado = True

            # Cuántos slots vamos a intercambiar
            k = min(n_slots_to_swap, len(comunes))

            # Seleccionar k posiciones sin repetición
            pool = list(comunes)
            posiciones = []
            for _ in range(k):
                idx = rng.nextInt(len(pool))
                posiciones.append(pool.pop(idx))

            # Intercambiar los slots entre dador y receptor
            t_dador = list(turnos[idx_dador])
            t_receptor = list(turnos[idx_receptor])

            for pos in posiciones:
                slot_d = turnos[idx_dador][pos * 3: pos * 3 + 3]
                slot_r = turnos[idx_receptor][pos * 3: pos * 3 + 3]
                t_dador[pos * 3: pos * 3 + 3] = list(slot_r)
                t_receptor[pos * 3: pos * 3 + 3] = list(slot_d)

            turnos[idx_dador] = "".join(t_dador)
            turnos[idx_receptor] = "".join(t_receptor)
            modified = True
            break  # un receptor por dador es suficiente

    if not modified:
        return sol

    result = sol.clone()
    result.setControladores([c.clone() for c in sol.getControladores()])
    result.setTurnos(turnos)
    return result

