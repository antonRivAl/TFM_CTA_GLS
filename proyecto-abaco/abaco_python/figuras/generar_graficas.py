#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import json
import math

try:
    import matplotlib.pyplot as plt
    import matplotlib.ticker as ticker
except ImportError:
    print("ERROR: matplotlib no está instalado. Instálalo ejecutando: pip install matplotlib")
    exit(1)


# Configuración estética profesional para documentos académicos / LaTeX
plt.rcParams.update({
    'font.family': 'sans-serif',
    'font.size': 11,
    'axes.labelsize': 12,
    'axes.titlesize': 13,
    'xtick.labelsize': 10,
    'ytick.labelsize': 10,
    'legend.fontsize': 10,
    'figure.titlesize': 14,
    'figure.autolayout': True,
    'axes.grid': True,
    'grid.alpha': 0.35,
    'grid.linestyle': '--',
    'axes.edgecolor': '#333333',
    'axes.linewidth': 0.9,
})

# Paleta de colores armoniosa
COLOR_PRIMARY = '#1f77b4'      # Azul acero (madN_M1)
COLOR_SECONDARY = '#e66101'    # Naranja cobrizo (madN_M2)
COLOR_FEASIBLE = '#2ca02c'     # Verde
COLOR_INFEASIBLE = '#d62728'   # Rojo
COLOR_ACCENT = '#5e3c99'       # Morado elegante


def cargar_datos(ruta_json="resultados_estadisticos.json", ruta_txt="Resultados.txt"):
    """Carga los datos desde JSON si existe; en caso contrario, los parsea directamente desde Resultados.txt."""
    if os.path.exists(ruta_json):
        with open(ruta_json, "r", encoding="utf-8") as f:
            datos = json.load(f)
            return datos["madN_M1"], datos["madN_M2"]
            
    if not os.path.exists(ruta_txt):
        raise FileNotFoundError(f"No se encontró ni {ruta_json} ni {ruta_txt}")

    with open(ruta_txt, "r", encoding="utf-8") as f:
        content = f.read()

    blocks = re.split(r"--------------------------------------------------------------------------------------------", content)
    m4_runs, m5_runs = [], []

    for b in blocks:
        b = b.strip()
        if not b:
            continue
        m_name = re.search(r"=>\s*(M[45]_\d+)", b)
        if not m_name:
            continue
        run_id = m_name.group(1)
        seed = int(run_id.split("_")[1])

        sls_lines = re.findall(r"\[(?:SLS|GLS)\] iter=(\d+) \| g_best=([0-9.]+) \| .*? \| R_star=([0-9.]+) \| .*? \| Tamano Ind: (\d+) \| t=([0-9.]+)min", b)
        last_sls = sls_lines[-1] if sls_lines else None

        raw_m = re.search(r"\"raw_restrictions\":\s*([0-9.]+)", b)
        weighted_m = re.search(r"\"weighted_restrictions\":\s*([0-9.]+)", b)
        raw_val = float(raw_m.group(1)) if raw_m else 0.0
        weighted_val = float(weighted_m.group(1)) if weighted_m else 0.0

        fit_m = re.search(r"\"fitnessF2\":\s*\[\s*([0-9.]+),\s*([0-9.]+),\s*([0-9.]+),\s*([0-9.]+),\s*([0-9.]+),\s*([0-9.]+)\s*\]", b)
        if fit_m:
            g, R_fit, o1, o2, o3, o4 = [float(x) for x in fit_m.groups()]
        else:
            g, R_fit, o1, o2, o3, o4 = None, None, None, None, None, None

        restr_breakdown = {}
        restr_m = re.search(r"Restricciones incumplidas\s*=\s*\[(.*?)\]", b)
        if restr_m:
            pairs = re.findall(r"(R\d+):\s*([0-9.]+)", restr_m.group(1))
            for r_code, r_val in pairs:
                val = float(r_val)
                if val > 0:
                    m = re.match(r"R(\d+)", r_code)
                    new_code = f"R{int(m.group(1)) + 1}" if m else r_code
                    restr_breakdown[new_code] = val

        iters = int(last_sls[0]) if last_sls else None
        g_best = float(last_sls[1]) if last_sls else g
        R_star = float(last_sls[2]) if last_sls else R_fit
        n_ctrl = int(last_sls[3]) if last_sls else 22
        t_min = float(last_sls[4]) if last_sls else None

        is_feasible = (raw_val == 0.0 and (R_star == 1.0 or R_fit == 1.0))

        item = {
            "id": run_id,
            "seed": seed,
            "iters": iters,
            "n_ctrl": n_ctrl,
            "t_min": t_min,
            "R_star": R_star if R_star is not None else 1.0,
            "raw_restrictions": raw_val,
            "weighted_restrictions": weighted_val,
            "feasible": is_feasible,
            "g": g,
            "o1": o1,
            "o2": o2,
            "o3": o3,
            "o4": o4,
            "violated_restrictions": restr_breakdown
        }
        if run_id.startswith("M4_"):
            m4_runs.append(item)
        elif run_id.startswith("M5_"):
            m5_runs.append(item)

    m4_runs.sort(key=lambda x: x["seed"])
    m5_runs.sort(key=lambda x: x["seed"])
    return m4_runs, m5_runs


def calcular_estadisticos(valores):
    """Calcula estadísticos descriptivos básicos."""
    if not valores:
        return {}
    v_ord = sorted(valores)
    n = len(v_ord)
    media = sum(v_ord) / n
    var = sum((x - media) ** 2 for x in v_ord) / (n - 1) if n > 1 else 0.0
    desv = math.sqrt(var)
    mediana = v_ord[n // 2] if n % 2 == 1 else (v_ord[n // 2 - 1] + v_ord[n // 2]) / 2.0
    q1 = v_ord[int(0.25 * n)]
    q3 = v_ord[int(0.75 * n)]
    return {
        "n": n,
        "media": media,
        "desv": desv,
        "mediana": mediana,
        "iqr": q3 - q1,
        "min": min(v_ord),
        "max": max(v_ord)
    }


def graficar_boxplot_calidad(m4_runs, m5_runs, out_dir="figuras"):
    """Gráfica 1: Boxplots de calidad multiobjetivo en ejecuciones factibles."""
    m4_feas = [r for r in m4_runs if r["feasible"]]
    m5_feas = [r for r in m5_runs if r["feasible"]]

    data_m4 = [
        [r["g"] for r in m4_feas],
        [r["o1"] for r in m4_feas],
        [r["o2"] for r in m4_feas],
        [r["o3"] for r in m4_feas],
        [r["o4"] for r in m4_feas]
    ]
    
    labels = [
        r'$g_{\mathrm{Calidad}}$' + '\n(Global)',
        r'$O_1$' + '\n(Ópt. Posición\n' + r'$w=0{,}52$)',
        r'$O_2$' + '\n(Compacidad\n' + r'$w=0{,}27$)',
        r'$O_3$' + '\n(Descansos\n' + r'$w=0{,}15$)',
        r'$O_4$' + '\n(Reparto Carga\n' + r'$w=0{,}06$)'
    ]

    fig, ax = plt.subplots(figsize=(8.5, 5.2))
    
    bp = ax.boxplot(data_m4, patch_artist=True, labels=labels,
                    showmeans=True,
                    meanprops=dict(marker='^', markeredgecolor='black', markerfacecolor='#2ca02c', markersize=8),
                    medianprops=dict(color='#d62728', linewidth=2),
                    boxprops=dict(facecolor='#d0e1f9', edgecolor='#1f77b4', linewidth=1.3),
                    whiskerprops=dict(color='#1f77b4', linewidth=1.2),
                    capprops=dict(color='#1f77b4', linewidth=1.2))

    # Puntos individuales superpuestos (jitter)
    for i, d in enumerate(data_m4):
        x = [i + 1 + (hash(str(val)) % 100 - 50) * 0.0015 for val in d]
        ax.scatter(x, d, color='#1f77b4', alpha=0.65, s=28, zorder=3, edgecolors='none')

    # Añadir el punto de la única solución factible de madN_M2 como referencia
    if m5_feas:
        m5_pt = [m5_feas[0]["g"], m5_feas[0]["o1"], m5_feas[0]["o2"], m5_feas[0]["o3"], m5_feas[0]["o4"]]
        ax.scatter([1, 2, 3, 4, 5], m5_pt, color=COLOR_SECONDARY, marker='D', s=60, zorder=4,
                   label='Única factible madN_M2 (Semilla 4)')

    ax.set_ylabel("Valor del Fitness [0, 1]")
    ax.set_title("Distribución de los Objetivos en Soluciones Factibles (madN_M1, N=11)", pad=14)
    ax.set_ylim(0.36, 1.15)
    ax.set_yticks([0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0])
    
    # Leyenda horizontal en la parte superior (zona libre por encima del valor máximo de fitness)
    legend_elements = [
        plt.Line2D([0], [0], color='#d62728', lw=2, label='Mediana'),
        plt.Line2D([0], [0], marker='^', color='w', markerfacecolor='#2ca02c', markeredgecolor='black', markersize=8, label='Media'),
        plt.Line2D([0], [0], marker='o', color='w', markerfacecolor='#1f77b4', markersize=6, label='madN_M1 (N=11)'),
    ]
    if m5_feas:
        legend_elements.append(plt.Line2D([0], [0], marker='D', color='w', markerfacecolor=COLOR_SECONDARY, markersize=7, label='madN_M2 (Semilla 4)'))
    ax.legend(handles=legend_elements, loc='upper center', ncol=4, framealpha=0.95, edgecolor='#cccccc', fontsize=9.0)

    os.makedirs(out_dir, exist_ok=True)
    pdf_path = os.path.join(out_dir, "fig_boxplot_calidad.pdf")
    png_path = os.path.join(out_dir, "fig_boxplot_calidad.png")
    fig.savefig(pdf_path, dpi=300, bbox_inches='tight')
    fig.savefig(png_path, dpi=300, bbox_inches='tight')
    plt.close(fig)
    print(f"[OK] Generada Figura 1: {pdf_path} y {png_path}")


def graficar_histograma_infracciones(m4_runs, m5_runs, out_dir="figuras"):
    """Gráfica 2: Histograma del número de restricciones incumplidas (raw) en infactibles."""
    m4_infeas_raw = [r["raw_restrictions"] for r in m4_runs if not r["feasible"]]
    m5_infeas_raw = [r["raw_restrictions"] for r in m5_runs if not r["feasible"]]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10.5, 4.5), sharey=True)

    bins = [0.5, 1.5, 2.5, 3.5, 4.5, 5.5, 6.5, 7.5, 8.5]

    ax1.hist(m4_infeas_raw, bins=bins, color=COLOR_PRIMARY, edgecolor='black', alpha=0.75, rwidth=0.85)
    ax1.set_title(f"madN_M1 (N={len(m4_infeas_raw)} infactibles)")
    ax1.set_xlabel(r"Número de infracciones ($r_{\mathrm{raw}}$)")
    ax1.set_ylabel("Frecuencia (Nº de ejecuciones)")
    ax1.set_xticks(range(1, 9))
    ax1.axvline(sum(m4_infeas_raw)/len(m4_infeas_raw), color='#d62728', linestyle='--', linewidth=1.5,
                label=f"Media: {sum(m4_infeas_raw)/len(m4_infeas_raw):.2f}")
    ax1.legend(loc='upper right')

    ax2.hist(m5_infeas_raw, bins=bins, color=COLOR_SECONDARY, edgecolor='black', alpha=0.75, rwidth=0.85)
    ax2.set_title(f"madN_M2 (N={len(m5_infeas_raw)} infactibles)")
    ax2.set_xlabel(r"Número de infracciones ($r_{\mathrm{raw}}$)")
    ax2.set_xticks(range(1, 9))
    ax2.axvline(sum(m5_infeas_raw)/len(m5_infeas_raw), color='#d62728', linestyle='--', linewidth=1.5,
                label=f"Media: {sum(m5_infeas_raw)/len(m5_infeas_raw):.2f}")
    ax2.legend(loc='upper right')

    fig.suptitle(r"Distribución del Grado de Infactibilidad ($r_{\mathrm{raw}}$) en Semillas No Factibles", fontsize=13)
    fig.tight_layout()

    pdf_path = os.path.join(out_dir, "fig_histograma_infracciones.pdf")
    png_path = os.path.join(out_dir, "fig_histograma_infracciones.png")
    fig.savefig(pdf_path, dpi=300, bbox_inches='tight')
    fig.savefig(png_path, dpi=300, bbox_inches='tight')
    plt.close(fig)
    print(f"[OK] Generada Figura 2: {pdf_path} y {png_path}")


def graficar_frecuencia_restricciones(m4_runs, m5_runs, out_dir="figuras"):
    """Gráfica 3: Frecuencia de aparición de restricciones específicas que impiden la factibilidad."""
    restr_nombres = {
        "R3": r"$R_3$ (Descanso Diurno)",
        "R5": r"$R_5$ (Trabajo Máx. Puesto)",
        "R7": r"$R_7$ (Ventana Móvil 2h30m)",
        "R8": r"$R_8$ (Cambio Posición)",
        "R10": r"$R_{10}$ (Descanso Mínimo)",
        "R11": r"$R_{11}$ (Permanencia Mínima)",
        "R12": r"$R_{12}$ (Límite Sectores Distintos)",
        "R13": r"$R_{13}$ (Asignación Completa)"
    }
    
    # Contar ocurrencias en infactibles
    conteo_m4 = {k: 0 for k in restr_nombres}
    conteo_m5 = {k: 0 for k in restr_nombres}

    for r in m4_runs:
        if not r["feasible"]:
            for k in r.get("violated_restrictions", {}):
                if k in conteo_m4:
                    conteo_m4[k] += 1
            if not r.get("violated_restrictions"):
                conteo_m4["R11"] += 1

    for r in m5_runs:
        if not r["feasible"]:
            for k in r.get("violated_restrictions", {}):
                if k in conteo_m5:
                    conteo_m5[k] += 1
            if not r.get("violated_restrictions"):
                conteo_m5["R11"] += 1

    claves = list(restr_nombres.keys())
    etiquetas = [restr_nombres[k] for k in claves]
    vals_m4 = [conteo_m4[k] for k in claves]
    vals_m5 = [conteo_m5[k] for k in claves]

    # Ordenar por frecuencia total descendente
    orden = sorted(range(len(claves)), key=lambda i: vals_m4[i] + vals_m5[i], reverse=True)
    etiquetas = [etiquetas[i] for i in orden]
    vals_m4 = [vals_m4[i] for i in orden]
    vals_m5 = [vals_m5[i] for i in orden]

    fig, ax = plt.subplots(figsize=(9.2, 5.0))
    y = list(range(len(etiquetas)))
    altura = 0.38

    ax.barh([p - altura/2 for p in y], vals_m4, height=altura, color=COLOR_PRIMARY, label='madN_M1 (19 infactibles)', alpha=0.85)
    ax.barh([p + altura/2 for p in y], vals_m5, height=altura, color=COLOR_SECONDARY, label='madN_M2 (29 infactibles)', alpha=0.85)

    ax.set_yticks(y)
    ax.set_yticklabels(etiquetas)
    ax.invert_yaxis()
    ax.set_xlabel("Número de ejecuciones en las que se incumple la restricción")
    ax.set_title("Frecuencia de Cuellos de Botella por Restricción en Soluciones Infactibles")
    ax.legend(loc='lower right', framealpha=0.9)

    fig.tight_layout()
    pdf_path = os.path.join(out_dir, "fig_frecuencia_restricciones.pdf")
    png_path = os.path.join(out_dir, "fig_frecuencia_restricciones.png")
    fig.savefig(pdf_path, dpi=300, bbox_inches='tight')
    fig.savefig(png_path, dpi=300, bbox_inches='tight')
    plt.close(fig)
    print(f"[OK] Generada Figura 3: {pdf_path} y {png_path}")


def graficar_tiempos_ejecucion(m4_runs, m5_runs, out_dir="figuras"):
    """Gráfica 4: Comparativa de tiempos de cómputo según factibilidad."""
    m4_feas_t = [r["t_min"] for r in m4_runs if r["feasible"] and r["t_min"]]
    m4_inf_t = [r["t_min"] for r in m4_runs if not r["feasible"] and r["t_min"]]
    m5_feas_t = [r["t_min"] for r in m5_runs if r["feasible"] and r["t_min"]]
    m5_inf_t = [r["t_min"] for r in m5_runs if not r["feasible"] and r["t_min"]]

    data = [m4_feas_t, m4_inf_t, m5_feas_t, m5_inf_t]
    labels = [
        f'madN_M1\nFactibles\n(N={len(m4_feas_t)})',
        f'madN_M1\nInfactibles\n(N={len(m4_inf_t)})',
        f'madN_M2\nFactible\n(N={len(m5_feas_t)})',
        f'madN_M2\nInfactibles\n(N={len(m5_inf_t)})'
    ]

    fig, ax = plt.subplots(figsize=(8.5, 4.8))
    colors = ['#2ca02c', '#1f77b4', '#2ca02c', '#e66101']
    
    bp = ax.boxplot(data, patch_artist=True, labels=labels, showmeans=True,
                    meanprops=dict(marker='^', markeredgecolor='black', markerfacecolor='#2ca02c', markersize=8),
                    medianprops=dict(color='#d62728', linewidth=2))

    for patch, color in zip(bp['boxes'], colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.35)
        patch.set_edgecolor(color)
        patch.set_linewidth(1.3)

    for i, d in enumerate(data):
        x = [i + 1 + (hash(str(val)) % 100 - 50) * 0.0015 for val in d]
        ax.scatter(x, d, color=colors[i], alpha=0.75, s=32, zorder=3)

    ax.set_ylabel("Tiempo de Cómputo hasta Convergencia (minutos)")
    ax.set_title("Distribución del Tiempo de Ejecución por Escenario y Estado de Factibilidad")

    fig.tight_layout()
    pdf_path = os.path.join(out_dir, "fig_tiempos_ejecucion.pdf")
    png_path = os.path.join(out_dir, "fig_tiempos_ejecucion.png")
    fig.savefig(pdf_path, dpi=300, bbox_inches='tight')
    fig.savefig(png_path, dpi=300, bbox_inches='tight')
    plt.close(fig)
    print(f"[OK] Generada Figura 4: {pdf_path} y {png_path}")


if __name__ == "__main__":
    print("================================================================")
    print("Generador de Gráficas y Análisis Estadístico para Memoria TFM")
    print("================================================================")
    m4, m5 = cargar_datos()
    graficar_boxplot_calidad(m4, m5)
    graficar_histograma_infracciones(m4, m5)
    graficar_frecuencia_restricciones(m4, m5)
    graficar_tiempos_ejecucion(m4, m5)
    print("Proceso finalizado con éxito.")
