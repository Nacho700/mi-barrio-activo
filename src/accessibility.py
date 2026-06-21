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


def walking_time_to_nearest(lat, lon, target_points, max_candidates=8):
    """
    Calcula el tiempo a pie (en minutos) desde (lat, lon) hasta el punto más
    cercano de target_points, usando distancias reales por la red de calles.

    Para no calcular contra TODOS los puntos (que puede ser lento si hay
    miles, p.ej. árboles), primero se filtra a los `max_candidates` más
    cercanos en línea recta, y solo sobre esos se calcula la ruta real.

    Parameters
    ----------
    target_points : list of dict
        [{"lat": .., "lon": .., "nombre": ..}, ...]

    Returns
    -------
    dict con {"minutos": float, "metros": float, "nombre": str} del punto
    más cercano, o None si target_points está vacío.
    """
    if not target_points:
        return None

    G = load_graph()
    origin_node = nearest_node(G, lat, lon)

    # Pre-filtro rápido por distancia euclídea para no calcular rutas de más
    df = pd.DataFrame(target_points)
    df["dist_aprox"] = ((df["lat"] - lat) ** 2 + (df["lon"] - lon) ** 2) ** 0.5
    df = df.sort_values("dist_aprox").head(max_candidates)

    best = None
    for _, row in df.iterrows():
        try:
            dest_node = nearest_node(G, row["lat"], row["lon"])
            length_m = nx.shortest_path_length(G, origin_node, dest_node, weight="length")
            minutos = length_m / WALKING_SPEED_M_PER_MIN
            if best is None or minutos < best["minutos"]:
                best = {
                    "minutos": round(minutos, 1),
                    "metros": round(length_m, 0),
                    "nombre": row.get("nombre", "Sin nombre"),
                }
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            continue

    return best


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
