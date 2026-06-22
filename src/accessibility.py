"""
src/accessibility.py
=====================
Calcula accesibilidad real "a pie" (no en línea recta) desde un punto hasta
la instalación deportiva, carril bici o zona verde más cercana, usando el
grafo de calles de Valencia descargado con OSMnx.
"""

import gzip
import shutil
import tempfile
from pathlib import Path
from functools import lru_cache

import networkx as nx
import osmnx as ox
import pandas as pd

PROCESSED_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"
GRAPH_PATH = PROCESSED_DIR / "grafo_valencia.graphml"
GRAPH_PATH_GZ = PROCESSED_DIR / "grafo_valencia.graphml.gz"

WALKING_SPEED_M_PER_MIN = 80  # ~4.8 km/h, ritmo de paseo urbano


@lru_cache(maxsize=1)
def load_graph():
    """
    Carga el grafo de calles cacheado. Soporta tanto el .graphml normal
    como una versión comprimida .graphml.gz (necesaria porque el grafo sin
    comprimir de Valencia supera el límite de 25MB de subida vía la
    interfaz web de GitHub; comprimido baja a ~5MB).
    """
    if GRAPH_PATH.exists():
        return ox.load_graphml(GRAPH_PATH)

    if GRAPH_PATH_GZ.exists():
        # Descomprimir a un archivo temporal y cargarlo desde ahí
        with tempfile.NamedTemporaryFile(suffix=".graphml", delete=False) as tmp:
            with gzip.open(GRAPH_PATH_GZ, "rb") as f_in:
                shutil.copyfileobj(f_in, tmp)
            tmp_path = tmp.name
        return ox.load_graphml(tmp_path)

    raise FileNotFoundError(
        f"No se encontró el grafo en {GRAPH_PATH} ni en {GRAPH_PATH_GZ}.\n"
        "Ejecuta primero: python src/data_loader.py --download-all"
    )


def nearest_node(G, lat, lon):
    return ox.distance.nearest_nodes(G, X=lon, Y=lat)


def _ranked_walking_times(lat, lon, target_points, max_candidates=8):
    """
    Función interna: calcula el tiempo a pie real hasta cada uno de los
    `max_candidates` puntos más cercanos (por distancia euclídea) de
    target_points, y devuelve la lista completa ordenada de más cercano a
    más lejano (en tiempo real por calle, no en línea recta).

    Esto evita duplicar la lógica de pre-filtro + cálculo de ruta entre
    walking_time_to_nearest() (que solo necesita el mejor) y
    top_n_nearest() (que necesita varios).
    """
    if not target_points:
        return []

    G = load_graph()
    origin_node = nearest_node(G, lat, lon)

    # Pre-filtro rápido por distancia euclídea para no calcular rutas de más
    df = pd.DataFrame(target_points)
    df["dist_aprox"] = ((df["lat"] - lat) ** 2 + (df["lon"] - lon) ** 2) ** 0.5
    df = df.sort_values("dist_aprox").head(max_candidates)

    columnas_base = {"lat", "lon", "nombre", "dist_aprox"}
    columnas_extra = [c for c in df.columns if c not in columnas_base]

    resultados = []
    for _, row in df.iterrows():
        try:
            dest_node = nearest_node(G, row["lat"], row["lon"])
            length_m = nx.shortest_path_length(G, origin_node, dest_node, weight="length")
            minutos = length_m / WALKING_SPEED_M_PER_MIN
            resultados.append(
                {
                    "minutos": round(minutos, 1),
                    "metros": round(length_m, 0),
                    "nombre": row.get("nombre", "Sin nombre"),
                    "lat": row["lat"],
                    "lon": row["lon"],
                    "extra": {c: row.get(c) for c in columnas_extra},
                }
            )
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            continue

    resultados.sort(key=lambda r: r["minutos"])
    return resultados


def walking_time_to_nearest(lat, lon, target_points, max_candidates=8):
    """
    Calcula el tiempo a pie (en minutos) desde (lat, lon) hasta el punto más
    cercano de target_points, usando distancias reales por la red de calles.

    Parameters
    ----------
    target_points : list of dict
        [{"lat": .., "lon": .., "nombre": .., ...propiedades_extra}, ...]
        Cualquier propiedad adicional presente en el dict (p.ej.
        'n_elementos_fitness', 'sup_total' para zonas verdes) se conserva
        y se devuelve en el resultado bajo la clave 'extra'.

    Returns
    -------
    dict con {"minutos": float, "metros": float, "nombre": str, "extra": dict}
    del punto más cercano, o None si target_points está vacío.
    """
    ranked = _ranked_walking_times(lat, lon, target_points, max_candidates=max_candidates)
    return ranked[0] if ranked else None


def top_n_nearest(lat, lon, target_points, n=5, max_candidates=15):
    """
    Devuelve los N puntos más cercanos (por tiempo real a pie), en vez de
    solo el mejor. Útil para mostrar un ranking tipo "Top 5 zonas verdes
    cerca de ti" o "Top 5 instalaciones deportivas cerca de ti".

    max_candidates se sube respecto a walking_time_to_nearest (8 -> 15)
    porque para un ranking de 5 conviene tener más candidatos de partida
    por si alguno no tiene ruta válida en el grafo.

    Returns
    -------
    list of dict (puede tener menos de n elementos si no hay suficientes
    target_points o candidatos con ruta válida), ordenados de más cercano
    a más lejano.
    """
    ranked = _ranked_walking_times(lat, lon, target_points, max_candidates=max_candidates)
    return ranked[:n]


def count_within_minutes(lat, lon, target_points, minutos_max=15, max_candidates=25):
    """
    Cuenta cuántos elementos de target_points están a menos de
    `minutos_max` a pie real, en vez de devolver solo el más cercano.

    Útil para una métrica más intuitiva tipo "3 parques, 2 polideportivos
    a menos de 15 min" en vez de solo "el parque más cercano está a 8 min".

    max_candidates se sube respecto a top_n_nearest porque aquí interesa
    contar TODOS los que caen dentro del radio, no solo un ranking corto —
    si hay muchos elementos densos cerca (p.ej. zonas verdes en el centro),
    conviene partir de más candidatos para no subestimar el conteo.

    Returns
    -------
    dict con {"conteo": int, "elementos": list of dict} — los elementos
    son los mismos dicts que devuelve _ranked_walking_times, ya filtrados
    a los que están dentro del radio.
    """
    ranked = _ranked_walking_times(lat, lon, target_points, max_candidates=max_candidates)
    dentro_del_radio = [r for r in ranked if r["minutos"] <= minutos_max]
    return {"conteo": len(dentro_del_radio), "elementos": dentro_del_radio}


def compute_accessibility_profile(lat, lon, carril_bici_points, deporte_points, verde_points):
    """
    Devuelve el perfil de accesibilidad completo de un punto: tiempo a pie
    hasta carril bici, instalación deportiva y zona verde más cercanos.
    """
    return {
        "carril_bici": walking_time_to_nearest(lat, lon, carril_bici_points),
        "deporte": walking_time_to_nearest(lat, lon, deporte_points),
        "verde": walking_time_to_nearest(lat, lon, verde_points),
    }
