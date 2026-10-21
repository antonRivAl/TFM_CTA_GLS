
from __future__ import annotations

import csv
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Parámetros de visualización
# ---------------------------------------------------------------------------

_ROLLING_WINDOW = 200   # Puntos para la media móvil (sobre los puntos muestreados)
_RAW_ALPHA      = 0.18  # Opacidad de la línea cruda (muy transparente con millones de pts)
_RAW_LW         = 0.25  # Grosor de la línea cruda
_MEAN_LW        = 1.4   # Grosor de la media móvil


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def _load_csv(path: Path) -> tuple[list[int], list[float], list[float], list[float]]:
    """Devuelve (iteraciones, R_star, g_actual, h_actual) desde el CSV."""
    iters, R_star, R_act, h_act = [], [], [], []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            iters.append(int(row["iteracion"]))
            R_star.append(float(row["R_star"]))
            R_act.append(float(row["R_actual"]))
            h_act.append(float(row["h_actual"]))
    return iters, R_star, R_act, h_act


def _rolling_mean(values: list[float], window: int) -> list[float]:
    """Media móvil simple con ventana adaptativa en los extremos."""
    n = len(values)
    result = []
    half = window // 2
    for i in range(n):
        lo = max(0, i - half)
        hi = min(n, i + half + 1)
        result.append(sum(values[lo:hi]) / (hi - lo))
    return result


def _improvement_points(
    iters: list[int], g_star: list[float]
) -> tuple[list[int], list[float]]:
    """Devuelve los puntos donde g* mejora por primera vez."""
    xs, ys = [], []
    prev = -1.0
    for it, g in zip(iters, g_star):
        if g > prev:
            xs.append(it)
            ys.append(g)
            prev = g
    return xs, ys


def _setup_ax(ax, fmt_x):
    ax.grid(True, linestyle="--", linewidth=0.35, alpha=0.45, color="#888")
    ax.xaxis.set_major_formatter(fmt_x)
    ax.tick_params(labelsize=9)
    for spine in ax.spines.values():
        spine.set_linewidth(0.6)


# ---------------------------------------------------------------------------
# Generación de los tres PNG
# ---------------------------------------------------------------------------
def _plot_R_star(iters, R_star, stem: str, out_dir: Path, save: bool, plt, ticker):
    import matplotlib.gridspec as gridspec

    fmt_x = ticker.FuncFormatter(lambda x, _: f"{int(x):,}")

    # ── Layout: gráfica ancha + panel de tabla estrecho a la derecha ──────────
    fig, ax = plt.subplots(figsize=(14, 4))

    # ── Gráfica principal ─────────────────────────────────────────────────────
    # Usamos colores azules (del original) pero con el estilo step de g_star
    ax.step(iters, R_star, color="#3A7ECF", lw=0.7, where="post", alpha=0.85)

    ax.set_title("Mayor cumplimiento de restricciones $R^*$ encontrado", fontsize=12)
    ax.set_ylabel("$R^*$", fontsize=10)
    ax.set_xlabel("Iteración", fontsize=10)
    _setup_ax(ax, fmt_x)
    fig.tight_layout()

    if save:
        out = out_dir / f"{stem}_R_star.png"
        fig.savefig(out, dpi=150, bbox_inches="tight")
        print(f"[plot_fitness] → {out}")
    else:
        plt.show()
    plt.close(fig)


def _plot_R_actual(iters, R_act, stem: str, out_dir: Path, save: bool, plt, ticker):
    import matplotlib.gridspec as gridspec

    fmt_x = ticker.FuncFormatter(lambda x, _: f"{int(x):,}")
    imp_x, imp_y = _improvement_points(iters, R_act)
    n_imp = len(imp_x)

    # ── Layout: gráfica ancha + panel de tabla estrecho a la derecha ──────────
    '''
    fig = plt.figure(figsize=(16, max(4, min(4 + n_imp * 0.18, 11))))
    gs  = gridspec.GridSpec(1, 2, width_ratios=[3.2, 1], figure=fig)
    gs.update(wspace=0.06)

    ax  = fig.add_subplot(gs[0])
    ax_t = fig.add_subplot(gs[1])
    ax_t.axis("off")

    # ── Gráfica principal ─────────────────────────────────────────────────────
    ax.step(iters, g_star, color="#C55A11", lw=0.7, where="post", alpha=0.85)
    if imp_x:
        ax.scatter(imp_x, imp_y, color="#FF8C00", s=18, zorder=5)
    '''
    fig, ax = plt.subplots(figsize=(14, 4))
    ax.step(iters, R_act, color="#C55A11", lw=0.7, where="post", alpha=0.85)

    ax.set_title("Cumplimiento de restricciones $R$ en la solución actual $h(t)$", fontsize=12)
    ax.set_ylabel("$R(t)$", fontsize=10)
    ax.set_xlabel("Iteración", fontsize=10)
    _setup_ax(ax, fmt_x)
    fig.tight_layout()

    '''
    # ── Tabla de mejoras ──────────────────────────────────────────────────────
    if imp_x:
        font_size = max(5.5, 8.5 - max(0, n_imp - 20) * 0.12)

        col_labels = ["#", "Iteración", "g*"]
        table_data = [
            [str(i + 1), f"{x:,}", f"{y:.6f}"]
            for i, (x, y) in enumerate(zip(imp_x, imp_y))
        ]

        tbl = ax_t.table(
            cellText=table_data,
            colLabels=col_labels,
            loc="upper left",
            cellLoc="right",
        )
        tbl.auto_set_font_size(False)
        tbl.set_fontsize(font_size)
        tbl.auto_set_column_width([0, 1, 2])

        # Cabecera en gris oscuro
        for col in range(3):
            cell = tbl[(0, col)]
            cell.set_facecolor("#404040")
            cell.set_text_props(color="white", fontsize=font_size, fontweight="bold")

        # Filas alternas
        for row in range(1, n_imp + 1):
            fc = "#F2F2F2" if row % 2 == 0 else "#FFFFFF"
            for col in range(3):
                tbl[(row, col)].set_facecolor(fc)
                tbl[(row, col)].set_edgecolor("#CCCCCC")

        ax_t.set_title(f"Mejoras ({n_imp})", fontsize=9, pad=4)
    '''

    if save:
        out = out_dir / f"{stem}_R_actual.png"
        fig.savefig(out, dpi=150, bbox_inches="tight")
        print(f"[plot_fitness] → {out}")
    else:
        plt.show()
    plt.close(fig)



def _plot_h_actual(iters, h_act, stem: str, out_dir: Path, save: bool, plt, ticker):
    fig, ax = plt.subplots(figsize=(14, 4))
    fmt_x = ticker.FuncFormatter(lambda x, _: f"{int(x):,}")

    # Línea principal (ahora visible y sólida, sin media móvil)
    ax.plot(iters, h_act, color="#4CAF6A", lw=1.0, alpha=0.85)

    ax.set_title(
        r"Función objetivo aumentada $h(t) = g(t) - \lambda\, \Sigma\,\wp_i I_i c_i$",
        fontsize=12,
    )
    ax.set_ylabel("$h(t)$", fontsize=10)
    ax.set_xlabel("Iteración", fontsize=10)
    _setup_ax(ax, fmt_x)
    fig.tight_layout()

    if save:
        out = out_dir / f"{stem}_h_actual.png"
        fig.savefig(out, dpi=150, bbox_inches="tight")
        print(f"[plot_fitness] → {out}")
    else:
        plt.show()
    plt.close(fig)


# ---------------------------------------------------------------------------
# Punto de entrada por CSV
# ---------------------------------------------------------------------------

def plot_fitness_csv(csv_path: Path, save: bool = True) -> None:
    """Genera tres PNG independientes (g_actual, g_star, h_actual) para el CSV dado."""
    try:
        import matplotlib.pyplot as plt
        import matplotlib.ticker as ticker
    except ImportError:
        print("[plot_fitness] matplotlib no está instalado. Ejecuta: pip install matplotlib")
        return

    iters, R_star, R_act, h_act = _load_csv(csv_path)

    if not iters:
        print(f"[plot_fitness] El archivo {csv_path} está vacío.")
        return

    stem = csv_path.stem          # e.g. "fitness_fase2_ind0"
    out_dir = csv_path.parent

    _plot_R_star(iters, R_star,  stem, out_dir, save, plt, ticker)
    _plot_R_actual(iters, R_act, stem, out_dir, save, plt, ticker)
    _plot_h_actual(iters, h_act,  stem, out_dir, save, plt, ticker)


# ---------------------------------------------------------------------------
# Entrada principal
# ---------------------------------------------------------------------------

def main() -> None:
    if len(sys.argv) > 1:
        paths = [Path(p) for p in sys.argv[1:]]
    else:
        logs_dir = Path("logs_gls")
        if not logs_dir.exists() and Path("logs_sls").exists():
            logs_dir = Path("logs_sls")
        if not logs_dir.exists():
            print("[plot_fitness] No se encontró el directorio logs_gls/. "
                  "Ejecuta primero el algoritmo GLS.")
            return
        paths = sorted(logs_dir.glob("fitness_*.csv"))
        if not paths:
            print(f"[plot_fitness] No se encontraron archivos fitness_*.csv en {logs_dir}/.")
            return

    for p in paths:
        print(f"[plot_fitness] Procesando: {p}")
        plot_fitness_csv(p)


if __name__ == "__main__":
    main()
