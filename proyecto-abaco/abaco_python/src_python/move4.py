"""move4.py – Port de Move4.java al flujo Python del algoritmo.

Corresponde a:
    src/main/algorithms/simulatedAnnealing/moves/Move4.java

Move4 implementa dos movimientos distintos seleccionados aleatoriamente:

1. movimiento_trabajo_intervalos  (≡ movimientoTrabajoIntervalosPseudoAleatorios)
   Elige un intervalo de trabajo (bloque entre descansos) del turno dador,
   trunca su longitud a un múltiplo de 9 chars (= 3 slots × tamano_slot)
   aleatorio dentro de [9, granularidad_max], y lo intercambia con el mismo
   rango del turno receptor. Solo acepta el cambio si comprobar_nucleos
   lo valida.

2. movimiento_cruce_controladores (≡ movimientoTrabajoCruceControladores)
   Elige un punto de corte aleatorio (múltiplo de 3) dentro del turno y hace
   un crossover: primera_parte_dador + segunda_parte_receptor y viceversa.
   También valida comprobar_nucleos.

3. movimiento (≡ doblemovimiento)
   Función pública principal. Con probabilidad `porcent_eleccion_mov` usa el
   cruce; en caso contrario usa los intervalos. Equivalente exacto del
   Java original salvo que el RNG Java se sustituye por JavaRandom.

Notas de traducción:
    - Java `Math.floor(Math.random() * (fin - ini + 1)) + ini`
      → Python `rng.nextInt(fin - ini + 1) + ini`  (usa JavaRandom).
    - `Movimiento` es una dataclass local (dador, receptor, inicio, fin)
      que sustituye a la clase Java del mismo nombre.
    - `DoChange1` / `asignarControlador` se replican fielmente de move15.py
      ya que la lógica es idéntica a la de ese módulo.
    - El parámetro `iteracion` (trazas de depuración Java) se omite porque
      en el flujo Python no existe ese mecanismo de logging externo.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .constants import STRING_DESCANSO, STRING_NO_TURNO
from .java_random import JavaRandom
from .models import Solucion
from . import restrictions as restr


# ---------------------------------------------------------------------------
# Estructura auxiliar Movimiento (sustituye a estructurasDatos.Movimiento)
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

def _turno_aleatorio(excluidos: set[int], n_turnos: int, rng: JavaRandom) -> int:
    """Elige un índice de turno al azar que no esté en `excluidos`.

    Equivalente a Move4.TurnoAleatorio(), pero usa JavaRandom en lugar de
    Math.random() y trabaja con un set en vez de una ArrayList.
    """
    while True:
        c = rng.nextInt(n_turnos)
        if c not in excluidos:
            return c


def _get_intervalos(trabajador: str) -> list[list[int]]:
    """Calcula los intervalos de trabajo (bloques sin descanso) de un turno.

    Equivalente exacto de Move4.GetIntervalos().

    Retorna lista de [inicio_char, fin_char] donde:
        - inicio_char : primer char del primer slot no-descanso del bloque
        - fin_char    : char siguiente al último slot no-descanso del bloque

    Los slots STRING_NO_TURNO ('000') se tratan como separadores igual que
    STRING_DESCANSO en este contexto (no son trabajo activo).
    """
    inicio: list[int] = []
    fin: list[int] = []

    # Buscar inicios de bloque de trabajo (char previo es descanso o es el comienzo)
    for i in range(0, len(trabajador), 3):
        slot = trabajador[i: i + 3]
        if slot != STRING_DESCANSO and slot != STRING_NO_TURNO:
            if i == 0 or trabajador[i - 3: i] == STRING_DESCANSO or trabajador[i - 3: i] == STRING_NO_TURNO:
                inicio.append(i)

    # Buscar fines de bloque de trabajo (char siguiente es descanso o es el final)
    for i in range(len(trabajador) - 3, -1, -3):
        slot = trabajador[i: i + 3]
        if slot != STRING_DESCANSO and slot != STRING_NO_TURNO:
            if i == len(trabajador) - 3 or trabajador[i + 3: i + 6] == STRING_DESCANSO or trabajador[i + 3: i + 6] == STRING_NO_TURNO:
                fin.append(i + 3)

    # Emparejar cada inicio con su fin más cercano (mayor inicio < fin)
    intervalos: list[list[int]] = []
    for ini in inicio:
        # El fin válido para este inicio es el menor fin que sea > ini
        f = next(
            (fe for fe in sorted(fin) if fe > ini),
            None,
        )
        if f is not None:
            intervalos.append([ini, f])

    return intervalos


def _comprobar_nucleos(cad: str, con_p: str, entrada) -> bool:
    """Comprueba que los slots de `cad` y `con_p` pertenecen a sectores abiertos.

    Equivalente exacto de Move4.comprobarNucleos() / move15.comprobar_nucleos().
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


def _do_change1(
    dos_ind: list[str],
    individuo: Solucion,
    mov: _Movimiento,
) -> Solucion:
    """Aplica el intercambio a la solución y gestiona la eliminación del turno vacío.

    Equivalente exacto de Move4.DoChange1().
    Si nControladores != nTurnos y el turno del dador queda solo con '1'
    (descanso/no-turno), se reasigna su controlador y se elimina ese turno.
    """
    turnos = list(individuo.getTurnos())
    turnos[mov.dador] = dos_ind[0]
    turnos[mov.receptor] = dos_ind[1]

    cs = [c.clone() for c in individuo.getControladores()]

    if len(cs) != len(individuo.getTurnos()):
        es_descanso = all(ch == '1' or ch == '0' for ch in dos_ind[0])
        if es_descanso:
            for i, ctrl in enumerate(cs):
                if ctrl.getTurnoAsignado() == mov.dador:
                    cs = _asignar_controlador(i, mov.dador, cs)
                    break
            turnos.pop(mov.dador)

    result = individuo.clone()
    result.setControladores(cs)
    result.setTurnos(turnos)
    return result


def _asignar_controlador(pos_ctrl: int, dador: int, cs: list) -> list:
    """Reasigna el controlador en pos_ctrl cuando su turno queda vacío.

    Equivalente exacto de Move4.asignarControlador().
    """
    # Decrementar índices de turno superiores al eliminado
    for ctrl in cs:
        if ctrl.getTurnoAsignado() > dador:
            ctrl.setTurnoAsignado(ctrl.getTurnoAsignado() - 1)

    # Encontrar el primer índice de turno no asignado
    asignados = {ctrl.getTurnoAsignado() for ctrl in cs}
    for j in range(len(cs)):
        if j not in asignados:
            cs[pos_ctrl].setTurnoAsignado(j)
            break

    return cs


def _change_cont(
    ind: Solucion,
    mov: _Movimiento,
    entrada,
    parametros,
    parametros_alg,
) -> Optional[list[str]]:
    """Comprueba si el intercambio es válido y retorna los dos turnos modificados.

    Equivalente exacto de Move4.ChangeCont().
    Retorna None si el movimiento no es válido (comprobar_nucleos falla o
    hay restricciones incumplidas en modos distintos a reduccionCtrl...).
    """
    turnos = ind.getTurnos()
    ctrl_vago = turnos[mov.dador]
    ctrl_p = turnos[mov.receptor]
    cadena = ctrl_vago[mov.inicio: mov.fin]
    cadena_p = ctrl_p[mov.inicio: mov.fin]

    if not _comprobar_nucleos(cadena, ctrl_p, entrada):
        return None
    if not _comprobar_nucleos(cadena_p, ctrl_vago, entrada):
        return None

    ctrl_vago2 = ctrl_vago[: mov.inicio] + cadena_p + ctrl_vago[mov.fin:]
    ctrl_p2 = ctrl_p[: mov.inicio] + cadena + ctrl_p[mov.fin:]

    # En Java se comprueba restricciones solo si la función fitness NO es
    # "reduccionControladoresYRestricciones". En Python replicamos ese check:
    fun = parametros_alg.getFuncionFitnessFase2()
    if fun.lower() != "reduccioncontroladoresyrestricciones":
        dos_ind_tmp = [ctrl_vago2, ctrl_p2]
        ind_tmp = _do_change1(dos_ind_tmp, ind, mov)
        if restr.penalizacion_por_restricciones(ind_tmp, entrada, parametros) != 0:
            return None

    return [ctrl_vago2, ctrl_p2]


# ---------------------------------------------------------------------------
# Movimiento 1: intervalos pseudo-aleatorios
# ---------------------------------------------------------------------------

def movimiento_trabajo_intervalos(
    individuo: Solucion,
    granularidad_max: int,
    granularidad_min: int,
    entrada,
    parametros,
    parametros_alg,
    rng: JavaRandom,
) -> Solucion:
    """Intercambia un bloque de trabajo entre dos turnos.

    Equivalente de Move4.movimientoTrabajoIntervalosPseudoAleatorios().

    Algoritmo:
        1. Elige un turno dador al azar.
        2. Obtiene sus intervalos de trabajo (_get_intervalos).
        3. Elige un intervalo al azar y un tamaño múltiplo de 9 chars al azar.
        4. Recorta el intervalo al tamaño elegido.
        5. Busca un receptor al azar y valida con _change_cont.
        6. Si es válido, aplica _do_change1 y devuelve la nueva solución.

    Returns:
        Nueva Solucion si se encontró un movimiento válido;
        clon sin cambios en caso contrario.
    """
    matriz_turnos = individuo.getTurnos()
    n_turnos = len(matriz_turnos)
    excluidos_dador: set[int] = set()
    encontrado = False
    individuo2 = individuo.clone()

    while len(excluidos_dador) < n_turnos and not encontrado:
        cv = _turno_aleatorio(excluidos_dador, n_turnos, rng)
        excluidos_dador.add(cv)

        intervalos = _get_intervalos(matriz_turnos[cv])
        if not intervalos:
            continue

        # Elegir un intervalo al azar
        pos = list(intervalos[rng.nextInt(len(intervalos))])

        # Construir lista de granularidades posibles: 9, 18, 27, ..., granularidad_max
        # (múltiplos de 9 chars = 3 slots de 3 chars cada uno)
        list_g = list(range(9, granularidad_max + 1, 9))
        if not list_g:
            list_g = [9]

        while list_g and not encontrado:
            # Elegir granularidad al azar y eliminarla de la lista
            idx_g = rng.nextInt(len(list_g))
            granularidad = list_g.pop(idx_g)

            # Ajustar fin del intervalo a la granularidad elegida
            if pos[1] >= pos[0] + granularidad:
                fin_efectivo = pos[0] + granularidad
            else:
                fin_efectivo = pos[1]
                granularidad = fin_efectivo - pos[0]

            excluidos_receptor: set[int] = {cv}
            while len(excluidos_receptor) < n_turnos:
                cs = _turno_aleatorio(excluidos_receptor, n_turnos, rng)
                excluidos_receptor.add(cs)
                if cs == cv:
                    continue

                mov = _Movimiento(cv, cs, pos[0], fin_efectivo)
                dos_ind = _change_cont(individuo, mov, entrada, parametros, parametros_alg)
                if dos_ind is not None:
                    individuo2 = _do_change1(dos_ind, individuo, mov)
                    encontrado = True
                    break

    return individuo2


# ---------------------------------------------------------------------------
# Movimiento 2: cruce de controladores (crossover en punto aleatorio)
# ---------------------------------------------------------------------------

def movimiento_cruce_controladores(
    individuo: Solucion,
    entrada,
    parametros,
    parametros_alg,
    rng: JavaRandom,
) -> Solucion:
    """Crossover entre dos turnos en un punto de corte aleatorio.

    Equivalente de Move4.movimientoTrabajoCruceControladores().

    Algoritmo:
        1. Elige un turno dador al azar.
        2. Elige un turno receptor al azar (distinto del dador).
        3. Elige un punto de corte `rand` (múltiplo de 3, dentro de la longitud del turno).
        4. Intercambia los primeros `rand` chars entre los dos turnos.
        5. Valida comprobar_nucleos y si pasa, aplica _do_change1.

    Returns:
        Nueva Solucion si se encontró un movimiento válido;
        clon sin cambios en caso contrario.
    """
    matriz_turnos = individuo.getTurnos()
    n_turnos = len(matriz_turnos)
    longitud_turno = len(matriz_turnos[0])
    n_slots = longitud_turno // 3  # número de slots por turno

    excluidos_dador: set[int] = set()
    encontrado = False
    individuo2 = individuo.clone()

    while len(excluidos_dador) < n_turnos and not encontrado:
        cv = _turno_aleatorio(excluidos_dador, n_turnos, rng)
        excluidos_dador.add(cv)

        excluidos_receptor: set[int] = {cv}
        while len(excluidos_receptor) < n_turnos:
            cs = _turno_aleatorio(excluidos_receptor, n_turnos, rng)
            excluidos_receptor.add(cs)
            if cs == cv:
                continue

            # Punto de corte: slot aleatorio × 3 chars, igual que Java:
            # (int) Math.floor(Math.random() * (length / 3)) * 3
            rand = rng.nextInt(n_slots) * 3

            ctrl_vago = matriz_turnos[cv]
            ctrl_p = matriz_turnos[cs]

            cadena = ctrl_vago[:rand]    # primera mitad del dador
            cadena_p = ctrl_p[:rand]     # primera mitad del receptor

            # Validar núcleos antes de aceptar
            if not _comprobar_nucleos(cadena, ctrl_p, entrada):
                continue
            if not _comprobar_nucleos(ctrl_vago, cadena_p, entrada):
                continue

            ctrl_vago2 = cadena_p + ctrl_vago[rand:]
            ctrl_p2 = cadena + ctrl_p[rand:]

            mov = _Movimiento(cv, cs, 0, rand)
            dos_ind = [ctrl_vago2, ctrl_p2]
            individuo2 = _do_change1(dos_ind, individuo, mov)
            encontrado = True
            break

    return individuo2


# ---------------------------------------------------------------------------
# Función principal: doblemovimiento
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
    """Despacha entre movimiento_cruce_controladores y movimiento_trabajo_intervalos.

    Equivalente exacto de Move4.doblemovimiento().

    Con probabilidad `porcent_eleccion_mov` (leída de parametros_alg.SA)
    usa el cruce; en caso contrario usa los intervalos.

    Args:
        individuo      : Solución actual.
        g_max, g_min   : Granularidad máxima/mínima en chars para el movimiento
                         de intervalos (equivalente a gMax/gMin en Java).
        entrada        : Objeto Entrada del problema.
        parametros     : Parámetros del problema.
        parametros_alg : Parámetros del algoritmo (contiene SA.porcent_eleccion_mov).
        rng            : Generador de números aleatorios.

    Returns:
        Nueva Solucion resultado del movimiento aplicado.
    """
    porcent = parametros_alg.GLS.getPorcentajeMovDiversificacion()
    rand = rng.random()  # uniform [0, 1)

    if porcent >= rand:
        return movimiento_cruce_controladores(
            individuo, entrada, parametros, parametros_alg, rng
        )
    else:
        return movimiento_trabajo_intervalos(
            individuo, g_max, g_min, entrada, parametros, parametros_alg, rng
        )