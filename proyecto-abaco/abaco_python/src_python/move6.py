"""move6.py – Port de Move6.java al flujo Python del algoritmo ABACO.

Corresponde a:
    - src/main/algorithms/simulatedAnnealing/moves/Move6.java
    - src/main/algorithms/simulatedAnnealing/moves/DeciderMove.java (case "movimiento6")

Descripción del Movimiento 6:
    - Identifica los intervalos de trabajo (bloques contiguos sin descansos ni no-turno)
      a partir de slotMomentoActual en un turno dador.
    - Selecciona una granularidad de corte basada en la longitud de descansos (crearListG)
      acotada por granularidadMax (múltiplos de 9, 12 o 15 caracteres según longdescansos).
    - Busca un turno receptor compatible donde intercambiar dicho intervalo mediante ChangeCont
      (validando pertenencia a núcleos y ausencia de '000').
    - En DeciderMove.java, el movimiento 6 consiste en ejecutar este operador de intervalos
      dos veces consecutivas sobre la solución (mov1 = Move6(...), mov = Move6(mov1, ...)).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .constants import STRING_DESCANSO, STRING_NO_TURNO
from .java_random import JavaRandom
from .models import Solucion


# ---------------------------------------------------------------------------
# Estructura auxiliar Movimiento
# ---------------------------------------------------------------------------

@dataclass
class _Movimiento:
    dador: int
    receptor: int
    inicio: int   # índice de char (no de slot)
    fin: int      # índice de char (exclusivo)


# ---------------------------------------------------------------------------
# Helpers privados
# ---------------------------------------------------------------------------

def _turno_aleatorio(contc: set[int] | list[int], n_turnos: int, rng: JavaRandom) -> int:
    """Elige un índice de turno al azar que no esté en contc.

    Equivalente a Move6.TurnoAleatorio().
    """
    excluidos = set(contc)
    while True:
        c = rng.nextInt(n_turnos)
        if c not in excluidos:
            return c


def _get_intervalos(trabajador: str, slot_momento_actual: int) -> list[list[int]]:
    """Calcula los intervalos de trabajo (bloques sin descanso ni no-turno) de un turno.

    Equivalente exacto de Move6.GetIntervalos(trabajador, slotMomentoActual).

    Retorna lista de [inicio_char, fin_char] donde:
        - inicio_char : primer char del primer slot de trabajo del bloque (>= mActual)
        - fin_char    : char siguiente al último slot de trabajo del bloque
    """
    intervalo: list[list[int]] = []
    inicio: list[int] = []
    fin: list[int] = []
    m_actual = slot_momento_actual * 3
    t_len = len(trabajador)

    # Primeros slots de trabajo (cuando se inicia un intervalo)
    for i in range(m_actual, t_len, 3):
        slot = trabajador[i: i + 3]
        if slot != STRING_DESCANSO and slot != STRING_NO_TURNO:
            if (
                i == m_actual
                or trabajador[i - 3: i] == STRING_DESCANSO
                or trabajador[i - 3: i] == STRING_NO_TURNO
            ):
                inicio.append(i)

    # Últimos slots de trabajo (cuando finaliza un intervalo)
    for i in range(t_len - 3, m_actual - 1, -3):
        slot = trabajador[i: i + 3]
        if slot != STRING_DESCANSO and slot != STRING_NO_TURNO:
            if i >= t_len - 3:
                fin.append(i + 3)
            else:
                if (
                    i == m_actual
                    or trabajador[i + 3: i + 6] == STRING_DESCANSO
                    or trabajador[i + 3: i + 6] == STRING_NO_TURNO
                ):
                    fin.append(i + 3)

    # Unión para crear los distintos intervalos
    for ini in inicio:
        if not fin:
            continue
        f_cand = [fe for fe in fin if fe > ini]
        if f_cand:
            f = min(f_cand)
            intervalo.append([ini, f])

    return intervalo


def _crear_list_g(longdescansos: int, granularidad_max: int) -> list[int]:
    """Genera la lista de granularidades posibles según Move6.crearListG()."""
    list_g: list[int] = []
    if longdescansos in (3, 6, 9, 12, 0):
        for i in range(9, granularidad_max + 1, 9):
            list_g.append(i)
    elif longdescansos in (4, 8):
        for i in range(12, granularidad_max + 1, 12):
            list_g.append(i)
    elif longdescansos in (5, 10):
        for i in range(15, granularidad_max + 1, 15):
            list_g.append(i)
    else:
        list_g.append(longdescansos * 9)

    if not list_g:
        list_g = [9]
    return list_g


def _comprobar_nucleos(cad: str, con_p: str, entrada) -> bool:
    """Comprueba que los slots de `cad` y `con_p` pertenezcan a los sectores abiertos.

    Equivalente exacto de Move6.comprobarNucleos().
    """
    if len(entrada.getNucleosAbiertos()) == 1:
        return True
    sectores_abiertos = entrada.getListaSectoresAbiertos()
    for cadena in (cad, con_p):
        correcto = False
        for _nucleo in entrada.getNucleosAbiertos():
            ok = True
            for i in range(0, len(cadena), 3):
                slot = cadena[i: i + 3]
                if slot.lower() not in {STRING_DESCANSO.lower(), STRING_NO_TURNO.lower()}:
                    if not any(slot.lower() == s.id.lower() for s in sectores_abiertos):
                        ok = False
                        break
            if ok:
                correcto = True
                break
        if not correcto:
            return False
    return True


def _change_cont(
    ind: Solucion,
    mov: _Movimiento,
    entrada,
) -> Optional[list[str]]:
    """Comprueba si el traspaso entre dador y receptor es válido (Move6.ChangeCont).

    Devuelve [turno_dador_nuevo, turno_receptor_nuevo] o None.
    """
    turnos = ind.getTurnos()
    controlador_vago = turnos[mov.dador]
    controlador_p = turnos[mov.receptor]
    cadena = controlador_vago[mov.inicio: mov.fin]
    cadena_p = controlador_p[mov.inicio: mov.fin]

    if STRING_NO_TURNO in cadena or STRING_NO_TURNO in cadena_p:
        return None

    if not _comprobar_nucleos(cadena, controlador_p, entrada):
        return None
    if not _comprobar_nucleos(controlador_vago, cadena_p, entrada):
        return None

    controlador_vago2 = controlador_vago[: mov.inicio] + cadena_p + controlador_vago[mov.fin:]
    controlador_p2 = controlador_p[: mov.inicio] + cadena + controlador_p[mov.fin:]

    return [controlador_vago2, controlador_p2]


def _do_change1(
    dos_ind: list[str],
    individuo: Solucion,
    mov: _Movimiento,
    parametros_alg=None,
) -> Solucion:
    """Aplica el intercambio a la solución y gestiona turnos vacíos (Move6.DoChange1)."""
    turnos = list(individuo.getTurnos())
    turnos[mov.dador] = dos_ind[0]
    turnos[mov.receptor] = dos_ind[1]

    cs = [c.clone() for c in individuo.getControladores()]

    if len(cs) != len(individuo.getTurnos()):
        es_descanso = all(ch in ('1', '0') for ch in dos_ind[0])
        if es_descanso:
            asignado = False
            for i, ctrl in enumerate(cs):
                if ctrl.getTurnoAsignado() == mov.dador:
                    resultado = _asignar_controlador(i, mov.dador, cs, dos_ind[0], turnos)
                    if resultado is not None:
                        cs, turnos = resultado
                        asignado = True
                        break

            if not asignado:
                for ctrl in cs:
                    if ctrl.getTurnoAsignado() > mov.dador:
                        ctrl.setTurnoAsignado(ctrl.getTurnoAsignado() - 1)
                turnos.pop(mov.dador)

            result = individuo.clone()
            result.setControladores(cs)
            result.setTurnos(turnos)
            return result

    result = individuo.clone()
    result.setControladores(cs)
    result.setTurnos(turnos)
    return result


def _asignar_controlador(
    pos_ctrl: int,
    dador: int,
    cs: list,
    turno_vacio: str,
    turnos: list[str],
) -> tuple[list, list[str]] | None:
    """Equivalente a Move6.asignarControlador() en Java."""
    posiciones_zeros = [
        i for i in range(0, len(turno_vacio), 3)
        if turno_vacio[i: i + 3].upper() == STRING_NO_TURNO.upper()
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
            if turno[p: p + 3].upper() in {STRING_NO_TURNO.upper(), STRING_DESCANSO.upper()}
        )
        if cnt == len(posiciones_zeros):
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


def _modificar_sin_zeros(
    cs: list,
    dador: int,
    aux: list,
    turnos: list[str],
    pos_ctrl: int,
) -> tuple[list, list[str]]:
    """Equivalente a Move6.modificarSinZeros() en Java."""
    for ctrl in cs:
        if ctrl.getTurnoAsignado() > dador:
            ctrl.setTurnoAsignado(ctrl.getTurnoAsignado() - 1)
    for j in range(len(cs)):
        if j not in aux:
            cs[pos_ctrl].setTurnoAsignado(j)
            break
    return cs, [t for i, t in enumerate(turnos) if i != dador]


def _repartir_trabajo(
    pos_aceptador: int,
    posiciones_zeros: list,
    turnos_orig: list[str],
    pos_vacio: int,
) -> list[str] | None:
    """Equivalente a Move6.repartirTrabajo() en Java."""
    turnos = list(turnos_orig)
    ta = list(turnos[pos_aceptador])

    for i, turno_str in enumerate(turnos):
        if i == pos_aceptador or i == pos_vacio:
            continue
        t = list(turno_str)
        for p in posiciones_zeros:
            seg_a = "".join(ta[p: p + 3])
            seg_t = "".join(t[p: p + 3])
            if seg_a.upper() == STRING_DESCANSO.upper():
                ta[p: p + 3] = list(STRING_NO_TURNO)
            if (
                seg_a.upper() not in {STRING_NO_TURNO.upper(), STRING_DESCANSO.upper()}
                and seg_t.upper() == STRING_DESCANSO.upper()
            ):
                t[p: p + 3] = list(seg_a)
                ta[p: p + 3] = list(STRING_NO_TURNO)
                turnos[i] = "".join(t)

    for p in posiciones_zeros:
        if "".join(ta[p: p + 3]).upper() not in {STRING_NO_TURNO.upper(), STRING_DESCANSO.upper()}:
            return None

    turnos[pos_aceptador] = "".join(ta)
    return turnos


# ---------------------------------------------------------------------------
# Operador elemental de intervalos pseudo-aleatorios (Move6.java)
# ---------------------------------------------------------------------------

def movimiento_trabajo_intervalos_pseudo_aleatorios(
    individuo1: Solucion,
    granularidad_max: int,
    granularidad_min: int,
    entrada,
    parametros,
    parametros_alg,
    rng: JavaRandom,
) -> Solucion:
    """Ejecuta una pasada del intercambio de intervalos de trabajo de Move6.

    Equivalente exacto de Move6.movimientoTrabajoIntervalosPseudoAleatorios().
    """
    matriz_turnos = individuo1.getTurnos()
    n_turnos = len(matriz_turnos)
    contcv: set[int] = set()
    encontrado = False
    individuo2 = individuo1.clone()

    while len(contcv) < n_turnos and not encontrado:
        cv = _turno_aleatorio(contcv, n_turnos, rng)
        contcv.add(cv)

        intervalos = _get_intervalos(matriz_turnos[cv], entrada.getSlotMomentoActual())
        if not intervalos:
            continue

        # Seleccionar un intervalo al azar
        pos = list(intervalos[rng.nextInt(len(intervalos))])
        list_g = _crear_list_g(individuo1.getLongdescansos(), granularidad_max)

        while not encontrado and list_g:
            idx_g = rng.nextInt(len(list_g))
            granularidad = list_g.pop(idx_g)
            tmn_intervalo = pos[1] - pos[0]

            if granularidad >= tmn_intervalo:
                list_g = [g for g in list_g if g < tmn_intervalo]

            if pos[1] >= pos[0] + granularidad:
                pos_fin = pos[0] + granularidad
            else:
                pos_fin = pos[1]
                granularidad = pos_fin - pos[0]

            contcs: set[int] = {cv}
            while len(contcs) < n_turnos:
                cs = _turno_aleatorio(contcs, n_turnos, rng)
                contcs.add(cs)
                if cs != cv:
                    mov = _Movimiento(cv, cs, pos[0], pos_fin)
                    dos_ind = _change_cont(individuo1, mov, entrada)
                    if dos_ind is not None:
                        individuo2 = _do_change1(dos_ind, individuo1, mov, parametros_alg)
                        encontrado = True
                        break

    return individuo2


# ---------------------------------------------------------------------------
# Función pública principal (DeciderMove.java case "movimiento6")
# ---------------------------------------------------------------------------

def movimiento(
    individuo: Solucion,
    g_max: int,
    g_min: int,
    entrada,
    parametros,
    parametros_alg,
    rng: JavaRandom,
) -> Solucion:
    """Función de movimiento 6 completa según DeciderMove.java.

    En Java:
        Solucion mov1 = Move6.movimientoTrabajoIntervalosPseudoAleatorios(individuo, gMax, gMin, ...);
        mov = Move6.movimientoTrabajoIntervalosPseudoAleatorios(mov1, gMax, gMin, ...);
    """
    mov1 = movimiento_trabajo_intervalos_pseudo_aleatorios(
        individuo, g_max, g_min, entrada, parametros, parametros_alg, rng
    )
    mov2 = movimiento_trabajo_intervalos_pseudo_aleatorios(
        mov1, g_max, g_min, entrada, parametros, parametros_alg, rng
    )
    return mov2
