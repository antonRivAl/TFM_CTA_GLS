"""Paquete GLS – Guided Local Search para la Fase 2 y 3 del proyecto ABACO.

Punto de entrada público: ``bucle_gls()``.

Uso desde __main__.py:
    from .GLS import bucle_gls
    soluciones_fase3 = bucle_gls(soluciones_fase2, parametros_alg, parametros, entrada)
"""

from .gls import bucle_gls

__all__ = ["bucle_gls", "bucle_sls", "augmented_fitness"]
