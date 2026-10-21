# TFM_CTA_GLS

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Este repositorio contiene la implementación en **Python** del algoritmo metaheurístico **Guided Local Search (GLS)** para la resolución del problema de planificación pre-táctica de turnos de controladores de tráfico aéreo (CTA) en el Centro de Control de Área (ACC) de Madrid, desarrollado en el marco del proyecto **ABACO**.

---

## 1. Descripción del Problema

El problema consiste en asignar los turnos y posiciones operativas de los controladores de tráfico aéreo en intervalos temporales de 5 minutos a lo largo de un horizonte operativo (un turno o jornada completa), garantizando la cobertura de la demanda de apertura de sectores de control de tráfico aéreo.

Los principales condicionantes del problema son:
* **Demanda sectorial**: Requerimiento dinámico de apertura y cierre de sectores elementales y colapsados.
* **Plantilla limitada y habilitaciones**: Asignación exclusiva a los controladores disponibles respetando sus acreditaciones operativas vigentes.
* **14 restricciones laborales duras ($R_1$ a $R_{14}$)**: En España, la planificación está sujeta a una estricta normativa de seguridad aérea (AESA) y al convenio colectivo, que imponen 14 restricciones legales ineludibles (tiempos máximos de trabajo continuo en frecuencia de 2 horas en turno diurno y 1,5 horas en nocturno, descansos obligatorios mínimos de entre 20 y 45 minutos, descansos post-turno, turnicidad, entre otras).
* **Criterios de calidad**: Distribución equitativa de la carga de trabajo entre controladores, asignación de descansos en franjas horarias óptimas y estabilidad en la asignación de posiciones.

---

## 2. Algoritmo Utilizado

Para resolver este problema se emplea la metaheurística **Guided Local Search (GLS)**:

1. **Punto de partida**: Se parte de una solución inicial generada por una heurística constructiva que satisface toda la demanda de apertura sectorial a costa de introducir **controladores imaginarios** (plantilla sobredimensionada).
2. **Optimización con GLS**: El algoritmo reduce progresivamente los controladores ficticios y repara las infracciones de las restricciones laborales. Cuando la búsqueda cae en un óptimo local, GLS penaliza aquellas características indeseadas de la solución (infracciones o presencia de controladores ficticios) aumentando dinámicamente la función objetivo evaluada, lo que fuerza al algoritmo a diversificar y escapar del estancamiento hasta alcanzar soluciones legalmente factibles ($R^* = 1$).

---

## 3. Manual de Usuario

### 3.1. Estructura de directorios principales

El desarrollo se articula en torno a la carpeta `proyecto-abaco`:

* **`entrada/`**: Esta carpeta **no contiene las instancias utilizadas en la memoria**. Los archivos proceden del material heredado de la tesis doctoral de Faustino Tello Caballo y no se publican porque este trabajo no dispone de autorización expresa para redistribuirlos. Para ejecutar el programa debe disponer legítimamente de esos CSV y copiarlos localmente con la estructura y nombres exactos siguientes:

```text
entrada/
├── Casos/
│   ├── madN_M1/
│   │   ├── AperturaSectorizaciones_madN_M1-2019-02-12.csv
│   │   ├── DistribucionInicial_madN_M1-2019-02-12.csv
│   │   ├── ListaSectoresElementales_madN_M1-2019-02-12.csv
│   │   ├── RecursosDisponibles_madN_M1-2019-02-12.csv
│   │   ├── SectoresNucleosMadrid_madN_M1-2019-02-12.csv
│   │   ├── SectorizacionesSectoresVolumenes_madN_M1-2019-02-12.csv
│   │   └── Turno_madN_M1-2019-02-12.csv
│   └── madN_M2/
│       ├── AperturaSectorizaciones_madN_M2-2019-02-16.csv
│       ├── DistribucionInicial_madN_M2-2019-02-16.csv
│       ├── ListaSectoresElementales_madN_M2-2019-02-16.csv
│       ├── RecursosDisponibles_madN_M2-2019-02-16.csv
│       ├── SectoresNucleosMadrid_madN_M2-2019-02-16.csv
│       ├── SectorizacionesSectoresVolumenes_madN_M2-2019-02-16.csv
│       └── Turno_madN_M2-2019-02-16.csv
└── Matrices de afinidad/
    ├── MatrizAfinidad_Madrid_20190212.csv
    └── MatrizAfinidad_Madrid_20190216.csv
```

* **`resources/`**: Aloja los ficheros de configuración y parametrización del sistema, entre los que destaca especialmente `algorithm.properties`. En este fichero se definen las propiedades operativas del algoritmo: parámetros de la metaheurística GLS (factor de penalización $\lambda$, paciencia para la detección de óptimos locales y probabilidad de diversificación $p_{\text{div}}$), parámetros de convergencia para la condición de parada entre otros.
* **`abaco_python/`**: Directorio principal que contiene la migración completa del sistema a Python:
  * **`src_python/`**: Paquete principal con el código fuente del algoritmo (bucle metaheurístico GLS, operadores de vecindario, evaluador de restricciones, cálculo de calidad y módulo CLI de ejecución).
  * **`logs_gls/`**: Carpeta donde se escriben de manera progresiva las trazas detalladas de la ejecución (evolución iteración a iteración del fitness real $g$, de la función aumentada $h$ y del índice de cumplimiento $R^*$).
  * **`resultados_py/`**: Directorio donde se almacena la solución final obtenida tras la detención del algoritmo, incluyendo la distribución final de los controladores de tráfico aéreo en los diferentes sectores.

### 3.2. Instalación y preparación del entorno

Para asegurar la reproducibilidad experimental y evitar conflictos entre versiones de librerías, se recomienda crear y activar un entorno virtual de Python. Como referencia del entorno de ejecución, todas las pruebas y experimentos reportados a lo largo de esta memoria se llevaron a cabo utilizando **Python 3.14.0** sobre el sistema operativo **macOS** (versión 26.6.2, *build* 25G83).

La preparación del entorno se efectúa mediante los siguientes comandos desde la raíz del proyecto:

1. Creación del entorno virtual aislado:
```bash
python3 -m venv .venv
```

2. Activación del entorno virtual:
```bash
source .venv/bin/activate
```
*(En Windows: `.venv\Scripts\activate`)*

3. Instalación de las dependencias requeridas del proyecto:
```bash
python3 -m pip install -r requirements.txt
```

### 3.3. Ejecución de experimentos

Una vez preparado el entorno virtual y satisfechas las dependencias, sitúese en el directorio de trabajo `abaco_python` y lance el proceso de optimización mediante el módulo principal:

```bash
cd proyecto-abaco/abaco_python
python3 -m src_python run-gls --case madN_M1 --seed 1 --prueba M4_1
```

Los argumentos principales aceptados por la interfaz de línea de comandos son:
* `--case`: Define el escenario operativo a ejecutar (por ejemplo, `madN_M1` o `madN_M2`). El sistema leerá de forma automática los ficheros de demanda y plantilla inicial desde el directorio `entrada/`.
* `--seed`: Fija la semilla del generador pseudoaleatorio de Python, permitiendo replicar con total determinismo cualquiera de las ejecuciones evaluadas en la memoria.
* `--prueba`: Asigna un identificador alfanumérico a la ejecución (por ejemplo, `M4_1`). Dicho identificador determina la denominación de los ficheros de log generados en `logs_gls/` y de los informes almacenados en `resultados_py/`.

---

## 4. Agradecimientos

Esta investigación forma parte de los proyectos de I+D+i **PID2024-155179NB-C22**, financiado por **MCIU/AEI/10.13039/501100011033**.

