"""
src/interpolation.py
=====================
Interpolación espacial (Inverse Distance Weighting, IDW) para estimar
contaminación (NO2, PM10, PM2.5) y ruido (SPL en dB) en cualquier punto de
Valencia a partir de los valores conocidos en las estaciones fijas.

¿Por qué IDW y no Kriging?
IDW es más simple, no requiere ajustar un variograma, y con ~10 estaciones
(pocos puntos) el beneficio de Kriging es marginal frente a su complejidad.
Si en el futuro quieres mejorar el proyecto, sustituir esta función por
pykrige.OrdinaryKriging es el upgrade natural y se puede justificar muy bien
en la memoria como "trabajo futuro".
"""

import numpy as np
import pandas as pd
from geopy.distance import geodesic


def idw_interpolate(target_lat, target_lon, known_points, power=2, n_neighbors=None):
    """
    Interpola un valor en (target_lat, target_lon) usando IDW.

    Parameters
    ----------
    target_lat, target_lon : float
        Coordenadas del punto donde queremos estimar el valor.
    known_points : list of dict
        Cada dict debe tener: {"lat": float, "lon": float, "value": float}
        (p.ej. una estación con su valor medido de NO2).
    power : float
        Exponente de la ponderación por distancia (2 es el valor estándar).
    n_neighbors : int or None
        Si se especifica, solo se usan los N puntos más cercanos.

    Returns
    -------
    float
        Valor interpolado. Si target coincide exactamente con un punto
        conocido (distancia ~0), devuelve el valor de ese punto.
    """
    if not known_points:
        raise ValueError("known_points está vacío: no hay estaciones con datos para interpolar.")

    distances = []
    for p in known_points:
        d = geodesic((target_lat, target_lon), (p["lat"], p["lon"])).meters
        distances.append(d)

    distances = np.array(distances)
    values = np.array([p["value"] for p in known_points], dtype=float)

    # Si el punto coincide casi exactamente con una estación, devolvemos su valor
    if distances.min() < 1.0:
        return float(values[distances.argmin()])

    if n_neighbors is not None and n_neighbors < len(distances):
        idx = np.argsort(distances)[:n_neighbors]
        distances = distances[idx]
        values = values[idx]

    weights = 1.0 / (distances ** power)
    weights /= weights.sum()

    return float(np.sum(weights * values))


def build_known_points(stations_df, value_column, lat_col="lat", lon_col="lon"):
    """
    Convierte un DataFrame de estaciones en la lista de dicts que espera
    idw_interpolate(). Filtra filas con NaN en el valor.

    Parameters
    ----------
    stations_df : pd.DataFrame
        Debe contener columnas lat, lon y value_column.
    value_column : str
        Nombre de la columna con el valor a interpolar (p.ej. "no2", "ruido_db").
    """
    df = stations_df.dropna(subset=[lat_col, lon_col, value_column])
    return [
        {"lat": row[lat_col], "lon": row[lon_col], "value": row[value_column]}
        for _, row in df.iterrows()
    ]


def estimate_environmental_profile(lat, lon, stations_df, pollutant_cols=None):
    """
    Devuelve un diccionario con la estimación interpolada de cada
    contaminante en el punto (lat, lon), a partir de las estaciones reales
    de contaminación atmosférica de Valencia.

    pollutant_cols : dict
        Mapeo {"clave_salida": "nombre_columna_en_df"}. Por defecto:
        {"no2": "no2", "pm10": "pm10", "pm25": "pm25"}
        Estos son los nombres de columna reales tras normalizarlos en
        src/data_loader.py (_normalize_column_name).

    NOTA: el ruido NO se interpola aquí. El dataset de ruido de Valencia
    da pocas estaciones (4) sin valores numéricos descargables de forma
    simple, así que se trata por separado — ver
    src/data_helpers.get_estaciones_ruido_con_valor() y la nota de
    honestidad metodológica en pages/.
    """
    if pollutant_cols is None:
        pollutant_cols = {"no2": "no2", "pm10": "pm10", "pm25": "pm25"}

    profile = {}
    for out_key, col in pollutant_cols.items():
        if col not in stations_df.columns:
            profile[out_key] = None
            continue
        known_points = build_known_points(stations_df, col)
        if not known_points:
            profile[out_key] = None
            continue
        profile[out_key] = round(idw_interpolate(lat, lon, known_points), 2)

    return profile


def build_interpolation_grid(stations_df, value_column, bounds, resolution=50):
    """
    Genera una rejilla (grid) de valores interpolados sobre toda la ciudad,
    útil para pintar un mapa de calor (heatmap) en vez de calcular punto a
    punto cada vez que el usuario mueve el mapa.

    Parameters
    ----------
    bounds : tuple
        (lat_min, lat_max, lon_min, lon_max) — el bounding box de Valencia.
    resolution : int
        Número de celdas por eje (resolution x resolution puntos en total).

    Returns
    -------
    pd.DataFrame con columnas lat, lon, value
    """
    lat_min, lat_max, lon_min, lon_max = bounds
    lats = np.linspace(lat_min, lat_max, resolution)
    lons = np.linspace(lon_min, lon_max, resolution)

    known_points = build_known_points(stations_df, value_column)

    rows = []
    for lat in lats:
        for lon in lons:
            val = idw_interpolate(lat, lon, known_points, n_neighbors=4)
            rows.append({"lat": lat, "lon": lon, "value": val})

    return pd.DataFrame(rows)


# Bounding box aproximado del término municipal de Valencia ciudad
VALENCIA_BOUNDS = (39.41, 39.51, -0.43, -0.31)
