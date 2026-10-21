from __future__ import annotations

# =============================================================================
# CORRESPONDENCIA CON CÓDIGO JAVA
# =============================================================================
# Sin equivalente Java directo como clase propia.
# Replica el algoritmo de java.util.Random (LCG de 48 bits), de forma que
# con la misma semilla numérica produce exactamente la misma secuencia de
# números aleatorios que java.util.Random en Java.
#
# Usado para sustituir SplitRnd (java.util.SplittableRandom / SplitMix64)
# y Math.random() en el flujo SA, de modo que Python y Java sean reproducibles
# con la misma semilla.
#
# Archivos Java que se sincronizan con este módulo:
#   - src/main/herramientas/random/SplitRnd.java      (movimientos en Move15)
#   - src/main/algorithms/simulatedAnnealing/SimulatedAnnealing.java (criterio de aceptación)
# =============================================================================


class JavaRandom:
    """
    Replica exacta del generador java.util.Random (LCG de 48 bits).

    Con la misma semilla que java.util.Random produce la misma secuencia
    de números aleatorios, permitiendo comparar Python y Java de forma
    reproducible.

    Algoritmo:
        seed_nuevo = (seed_viejo * MULTIPLIER + ADDEND) & MASK
        donde MULTIPLIER = 0x5DEECE66D, ADDEND = 0xB, MASK = 2^48 - 1
    """

    MULTIPLIER: int = 0x5DEECE66D
    ADDEND: int = 0xB
    MASK: int = (1 << 48) - 1

    def __init__(self, seed: int) -> None:
        # Java aplica XOR con MULTIPLIER al inicializar la semilla
        self._seed: int = (seed ^ self.MULTIPLIER) & self.MASK

    def _next(self, bits: int) -> int:
        """Genera los siguiente `bits` bits del LCG."""
        self._seed = (self._seed * self.MULTIPLIER + self.ADDEND) & self.MASK
        return self._seed >> (48 - bits)

    def nextInt(self, bound: int) -> int:
        """
        Equivalente a java.util.Random.nextInt(bound).
        Devuelve un entero en [0, bound).
        """
        if bound <= 0:
            raise ValueError("bound must be positive")
        # Optimización para potencias de 2 (idéntica a Java)
        if bound & -bound == bound:
            return (bound * self._next(31)) >> 31
        # Rechazo para evitar sesgo (idéntico a Java)
        while True:
            bits = self._next(31)
            val = bits % bound
            if bits - val + (bound - 1) >= 0:
                return val

    def nextDouble(self) -> float:
        """
        Equivalente a java.util.Random.nextDouble().
        Devuelve un double en [0.0, 1.0).
        """
        return ((self._next(26) << 27) + self._next(27)) / float(1 << 53)

    # -------------------------------------------------------------------------
    # Métodos con interfaz compatible con random.Random de Python
    # (usados por move15.py y simulated_annealing.py sin cambios adicionales)
    # -------------------------------------------------------------------------

    def randint(self, a: int, b: int) -> int:
        """
        Devuelve un entero en [a, b] inclusive.
        Compatible con random.Random.randint(a, b).
        Internamente usa nextInt(b - a + 1) + a.
        """
        return a + self.nextInt(b - a + 1)

    def choice(self, seq):
        """
        Elige un elemento de seq al azar.
        Compatible con random.Random.choice(seq).
        """
        if not seq:
            raise IndexError("Cannot choose from an empty sequence")
        return seq[self.nextInt(len(seq))]

    def random(self) -> float:
        """
        Devuelve un float en [0.0, 1.0).
        Compatible con random.Random.random() y usado para el criterio
        de aceptación del SA (equivale al Math.random() / rnd.nextDouble() de Java).
        """
        return self.nextDouble()
