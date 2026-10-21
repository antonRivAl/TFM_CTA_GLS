from __future__ import annotations

from .fitness import slots_classification

# =============================================================================
# CORRESPONDENCIA CON CÓDIGO JAVA
# =============================================================================
# Archivo Java:
#   - src/main/algorithms/MetaheuristicUtil.java
#       → order_by_lazy_criteria()  ≡  MetaheuristicUtil.orderByLazyCriteria()
#
# NOTA: MetaheuristicUtil.java contiene también métodos auxiliares para VNS
# (reordenarYEliminarTurnos, esTrabajo, esDescanso, etc.) que no están
# implementados aquí por no ser necesarios para SA.
# =============================================================================

def order_by_lazy_criteria(solution):
    controladores = solution.getControladores()
    turnos = solution.getTurnos()
    work_order = []
    max_work = 0
    for turno in turnos:
        work = slots_classification(turno)[1]
        work_order.append(work)
        max_work = max(max_work, work)

    imaginary = set(range(len(turnos)))
    for controlador in controladores:
        imaginary.discard(controlador.turno_asignado)
    for idx in imaginary:
        if 0 <= idx < len(work_order):
            work_order[idx] -= max_work

    new_turnos = []
    controller_ids = []
    mutable_order = list(work_order)
    for _ in range(len(mutable_order)):
        r = min(range(len(mutable_order)), key=lambda i: mutable_order[i])
        lazy_value = mutable_order[r]
        mutable_order[r] = 300
        new_turnos.append(turnos[r])
        if lazy_value >= 0:
            for controlador in controladores:
                if controlador.turno_asignado == r:
                    controller_ids.append(controlador.id)
                    break

    for idx, controller_id in enumerate(controller_ids):
        for controlador in controladores:
            if controlador.id == controller_id:
                controlador.turno_asignado = idx + len(imaginary)
                break
    solution.setTurnos(new_turnos)
    solution.setControladores(controladores)
    return solution

