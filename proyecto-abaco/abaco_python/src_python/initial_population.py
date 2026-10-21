from __future__ import annotations

from .constants import LONGITUD_CADENAS, STRING_DESCANSO, STRING_NO_TURNO
from .entrada import java_hashset_order
from .models import Propiedades, Solucion

# =============================================================================
# CORRESPONDENCIA CON CÓDIGO JAVA
# =============================================================================
# Archivos Java:
#   - src/main/InicializarPoblacion/InicializarPoblacion.java
#       → inicializar_poblacion(), inicializar_individuo(),
#         anadir_controladores_alta(), eliminar_controladores_baja(),
#         eliminar_sectores_cerrados(), introducir_plantillas_nuevos_sectores()
#
#   - src/main/InicializarPoblacion/ArreglarSoluciones.java
#       → La lógica de reparación de trabajo mínimo (arregloTrabajoMinimo)
#         está integrada en la generación de plantillas (introducir_sector,
#         introducir_sector_noche). No existe como función separada en Python.
# =============================================================================


DESCANSO = 6


def inicializar_poblacion(entrada, parametros) -> list[Solucion]:
    min_d = parametros.getTiempoDesMin() // parametros.getTamanoSlots()
    max_t = parametros.getTiempoTrabMax() // parametros.getTamanoSlots()
    min_t = parametros.getTiempoTrabMin() // parametros.getTamanoSlots()
    individuo = inicializar_individuo(DESCANSO, max_t, min_t, min_d, entrada, parametros)
    poblacion = [individuo]
    print(f"La poblacion inicial es de: {len(poblacion)} individuos")
    return poblacion


def inicializar_individuo(descanso: int, max_t: int, min_t: int, min_d: int, entrada, parametros) -> Solucion:
    individuo = entrada.getDistribucionInicial().clone()
    if entrada.getSectorizacionModificada() is not None:
        nuevos_no_asignados = eliminar_sectores_cerrados(
            entrada.getSlotMomentoActual(),
            entrada.getSectorizacion(),
            entrada.getSectorizacionModificada(),
            entrada.getControladores(),
            entrada.getListaNuevosSectoresAbiertosTrasMomentoActual() or [],
            individuo,
            entrada.getMapaAfinidad(),
        )
        introducir_plantillas_nuevos_sectores(entrada, nuevos_no_asignados, individuo, descanso, max_t, min_t, min_d)
    eliminar_controladores_baja(entrada, individuo)
    anadir_controladores_alta(entrada, individuo)
    return individuo


def anadir_controladores_alta(entrada, individuo) -> None:
    controladores = individuo.getControladores()
    turnos = individuo.getTurnos()
    if not turnos:
        return
    base = turnos[0]
    for controlador in controladores:
        if controlador.baja_alta in {Propiedades.ALTA, Propiedades.ALTABAJA} and controlador.slot_alta != 0:
            alta = controlador.slot_alta * LONGITUD_CADENAS
            baja = controlador.slot_baja * LONGITUD_CADENAS
            turno = []
            for j in range(0, len(base), LONGITUD_CADENAS):
                if j < alta:
                    turno.append(STRING_NO_TURNO)
                elif j < baja or controlador.baja_alta == Propiedades.ALTA:
                    turno.append(STRING_DESCANSO)
                else:
                    turno.append(STRING_NO_TURNO)
            turnos.append("".join(turno))
            controlador.turno_asignado = len(turnos) - 1


def eliminar_controladores_baja(entrada, individuo) -> None:
    controladores = individuo.getControladores()
    turnos = individuo.getTurnos()
    for controlador in controladores:
        if controlador.baja_alta == Propiedades.BAJA and controlador.turno_asignado >= 0:
            baja = controlador.slot_baja
            turno = turnos[controlador.turno_asignado]
            cad_fin = turno[baja * LONGITUD_CADENAS :]
            cad_ini = turno[: baja * LONGITUD_CADENAS] + STRING_NO_TURNO * ((len(turno) // 3) - baja)
            tmp = []
            for j in range(0, baja * LONGITUD_CADENAS, LONGITUD_CADENAS):
                tmp.append(STRING_NO_TURNO if entrada.getSlotMomentoActual() * LONGITUD_CADENAS > j else STRING_DESCANSO)
            turnos[controlador.turno_asignado] = cad_ini
            turnos.append("".join(tmp) + cad_fin)


def eliminar_sectores_cerrados(slot_actual, sectorizacion, sectorizacion_modificada, controladores, sectores, distribucion, mapa_afinidad):
    nuevos_no_asignados = set(sectores)
    sectores_cerrados = None
    sectores_que_abren = None
    hay_cambio = False
    idx_inicio = slot_actual
    for slot in range(slot_actual, len(sectorizacion)):
        changed = (
            sectores_cerrados is None
            or sectorizacion_modificada[slot] != sectorizacion_modificada[slot - 1]
            or sectorizacion[slot] != sectorizacion[slot - 1]
        )
        if changed:
            if hay_cambio:
                modificar_turno(idx_inicio, slot, sectores_cerrados, sectores_que_abren, sectores, distribucion, mapa_afinidad, nuevos_no_asignados)
                hay_cambio = False
            sectores_cerrados = diferencia_conjuntos_java(sectorizacion[slot], sectorizacion_modificada[slot])
            sectores_que_abren = diferencia_conjuntos_java(sectorizacion_modificada[slot], sectorizacion[slot])
            if sectores_cerrados or sectores_que_abren:
                hay_cambio = True
                idx_inicio = slot
    if hay_cambio:
        modificar_turno(idx_inicio, len(sectorizacion), sectores_cerrados, sectores_que_abren, sectores, distribucion, mapa_afinidad, nuevos_no_asignados)
    return nuevos_no_asignados


def modificar_turno(slot_inicio, slot_fin, sectores_cerrados, sectores_que_abren, sectores, distribucion, mapa_afinidad, nuevos_no_asignados) -> None:
    for cerrado in sectores_cerrados:
        sustituir = ""
        afin = buscar_sector_afin(cerrado, sectores_que_abren, mapa_afinidad)
        sector_afin = next((sector for sector in sectores if sector.id == afin), None) if afin else None
        if sector_afin is not None:
            sustituir = afin
        for idx, turno in enumerate(distribucion.getTurnos()):
            start = slot_inicio * LONGITUD_CADENAS
            end = slot_fin * LONGITUD_CADENAS
            fragment = turno[start:end]
            if cerrado.lower() not in fragment.lower():
                continue
            if not sustituir:
                fragment = replace_ignore_case(fragment, cerrado, STRING_DESCANSO)
            else:
                fragment = fragment.replace(cerrado.lower(), sustituir.lower()).replace(cerrado.upper(), sustituir.upper())
                nuevos_no_asignados.discard(sector_afin)
                if afin in sectores_que_abren:
                    sectores_que_abren.remove(afin)
            distribucion.getTurnos()[idx] = turno[:start] + fragment + turno[end:]


def buscar_sector_afin(cerrado: str, abiertos: set[str], mapa_afinidad: dict[str, set[str]]) -> str:
    if cerrado in abiertos:
        return cerrado
    for abierto in abiertos:
        if abierto in mapa_afinidad.get(cerrado, set()):
            return abierto
    return ""


def diferencia_conjuntos_java(base, subtract) -> list[str]:
    return [value for value in java_hashset_order(base) if value not in subtract]


def replace_ignore_case(text: str, old: str, new: str) -> str:
    result = []
    i = 0
    old_lower = old.lower()
    while i < len(text):
        part = text[i : i + len(old)]
        if part.lower() == old_lower:
            result.append(new)
            i += len(old)
        else:
            result.append(text[i])
            i += 1
    return "".join(result)


def introducir_plantillas_nuevos_sectores(entrada, nuevos_sectores, distribucion, descanso, max_t, min_t, min_d) -> None:
    turnos = distribucion.getTurnos()
    sectorizacion = entrada.getSectorizacionModificada()
    sec_noc = set()
    for sector in list(nuevos_sectores):
        plantilla = [[], [], []]
        if sector.noche == 0:
            for slot, abiertos in enumerate(sectorizacion):
                if slot < entrada.getSlotMomentoActual():
                    introducir_string(plantilla, STRING_NO_TURNO)
                elif sector.id in abiertos:
                    introducir_sector(plantilla, descanso, sector.id)
                else:
                    introducir_string(plantilla, STRING_DESCANSO)
        else:
            if sector.noche in sec_noc:
                continue
            sec_noc.add(sector.noche)
            plantilla = introducir_sector_noche(plantilla, nuevos_sectores, sector.noche, sectorizacion)
        for row in plantilla:
            turnos.append("".join(row))


def introducir_string(plantilla, value: str):
    for row in plantilla[-3:]:
        row.append(value)
    return plantilla


def introducir_sector(plantilla, desc: int, sid: str):
    c1, c2, c3 = plantilla[-3], plantilla[-2], plantilla[-1]
    j = len(c1)
    while j >= desc * 3:
        j -= desc * 3
    if j < desc:
        c1.append(sid.lower())
        c2.append(sid.upper())
        c3.append(STRING_DESCANSO)
    elif j < desc * 2:
        c1.append(sid.upper())
        c2.append(STRING_DESCANSO)
        c3.append(sid.lower())
    else:
        c1.append(STRING_DESCANSO)
        c2.append(sid.lower())
        c3.append(sid.upper())
    return plantilla


def introducir_sector_noche(plantilla, sectores, noche, sectorizacion):
    plantilla.append([])
    sectores_nocturnos = [sector for sector in sectores if sector.noche == noche]
    for abiertos in sectorizacion:
        for sid in abiertos:
            for sector in sectores_nocturnos:
                if sector.id.lower() == sid.lower():
                    introducir_slot_sector_nocturno(plantilla, sector.id)
    return plantilla


def introducir_slot_sector_nocturno(plantilla, sid: str):
    desc = 9
    c1, c2, c3, c4 = plantilla[-4], plantilla[-3], plantilla[-2], plantilla[-1]
    j = len(c1)
    while j >= desc * 4:
        j -= desc * 4
    if j < desc:
        c1.append(sid.lower()); c2.append(sid.upper()); c3.append(STRING_DESCANSO); c4.append(STRING_DESCANSO)
    elif j < desc * 2:
        c1.append(STRING_DESCANSO); c2.append(STRING_DESCANSO); c3.append(sid.upper()); c4.append(sid.lower())
    elif j < desc * 3:
        c1.append(sid.upper()); c2.append(sid.lower()); c3.append(STRING_DESCANSO); c4.append(STRING_DESCANSO)
    else:
        c1.append(STRING_DESCANSO); c2.append(STRING_DESCANSO); c3.append(sid.lower()); c4.append(sid.upper())
    return plantilla
