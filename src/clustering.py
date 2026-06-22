"""
src/clustering.py
====================
Agrupa zonas de Valencia en "tipos de barrio" según su perfil ambiental y
de accesibilidad (contaminación, ruido estimado, acceso a deporte/verde),
usando K-means sobre un grid de puntos que cubre la ciudad.

Diseño: el clustering se calcula UNA VEZ de forma offline (ver el notebook
de Colab equivalente) y se guarda como un GeoJSON con cada punto del grid
etiquetado con su cluster. La app en producción NO ejecuta K-means en
cada petición — solo consulta qué cluster tiene el punto del grid más
cercano a la dirección del usuario. Esto es necesario porque K-means
sobre todo el grid (cientos de puntos, cada uno con cálculo de
accesibilidad real vía grafo de calles) tardaría demasiado para
ejecutarse en cada clic del usuario.

¿Por qué K-means?
- Es el algoritmo de clustering más simple e interpretable para esta
  escala de problema (pocas features, no hay estructura jerárquica clara
  que justifique alternativas como clustering jerárquico o DBSCAN).
- El número de clusters (k) se elige con el método del codo (elbow method)
  sobre la inercia, no arbitrariamente.
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
CLUSTERS_PATH = RAW_DIR / "barrios_clusters.geojson"

# Features usadas para el clustering — deben coincidir con las columnas
# que genera el script de generación (ver generar_clusters_colab.ipynb)
CLUSTER_FEATURES = ["no2", "pm10", "ruido_db", "tiempo_deporte_min", "tiempo_verde_min"]

# Etiquetas descriptivas por cluster. Como K-means no da nombres
# semánticos a los clusters (solo números 0, 1, 2...), estas etiquetas se
# asignan A MANO tras inspeccionar el centroide de cada cluster (ver
# generar_clusters_colab.ipynb, celda de inspección de centroides). Si se
# regenera el clustering con datos distintos, estas etiquetas pueden
# necesitar revisión.
CLUSTER_LABELS = {
    0: "🌳 Verde y tranquilo",
    1: "🏙️ Céntrico y dinámico",
    2: "🚗 Bien conectado, más tráfico",
    3: "🏘️ Residencial equilibrado",
}


def fit_kmeans(features_df: pd.DataFrame, k: int, feature_cols=None, random_state=42):
    """
    Ajusta K-means sobre features_df (una fila por punto del grid).

    Las features se estandarizan (media 0, varianza 1) antes de ajustar,
    porque K-means usa distancia euclídea y las variables de este problema
    tienen escalas muy distintas (NO2 en µg/m³ ~10-40, minutos ~0-25) —
    sin estandarizar, la variable de mayor escala dominaría la distancia.

    Returns
    -------
    (modelo_kmeans, scaler, labels) — labels es un array con el cluster
    asignado a cada fila de features_df.
    """
    if feature_cols is None:
        feature_cols = CLUSTER_FEATURES

    X = features_df[feature_cols].copy()
    X = X.fillna(X.mean())  # imputación simple por media para huecos puntuales

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    modelo = KMeans(n_clusters=k, random_state=random_state, n_init=10)
    labels = modelo.fit_predict(X_scaled)

    return modelo, scaler, labels


def elbow_method(features_df: pd.DataFrame, k_range=range(2, 9), feature_cols=None):
    """
    Calcula la inercia de K-means para cada k en k_range, para decidir el
    número de clusters por el método del codo en vez de a ojo.

    Returns
    -------
    dict {k: inercia} — se espera que el "codo" (donde la inercia deja de
    bajar mucho) indique un buen k.
    """
    if feature_cols is None:
        feature_cols = CLUSTER_FEATURES

    X = features_df[feature_cols].copy()
    X = X.fillna(X.mean())
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    inercias = {}
    for k in k_range:
        modelo = KMeans(n_clusters=k, random_state=42, n_init=10)
        modelo.fit(X_scaled)
        inercias[k] = modelo.inertia_

    return inercias


def describe_clusters(features_df: pd.DataFrame, labels, feature_cols=None):
    """
    Devuelve el centroide (media de cada feature) de cada cluster en
    UNIDADES ORIGINALES (no estandarizadas), para poder interpretar qué
    caracteriza a cada cluster al asignarle una etiqueta descriptiva a mano.
    """
    if feature_cols is None:
        feature_cols = CLUSTER_FEATURES

    df = features_df[feature_cols].copy()
    df["cluster"] = labels
    return df.groupby("cluster").mean().round(1)


def load_cluster_grid():
    """
    Carga el grid precalculado de clusters (generado offline). Devuelve un
    DataFrame con columnas lat, lon, cluster y las features originales, o
    un DataFrame vacío si todavía no se ha generado.
    """
    if not CLUSTERS_PATH.exists():
        return pd.DataFrame()

    with open(CLUSTERS_PATH, "r", encoding="utf-8") as f:
        geo = json.load(f)

    rows = []
    for feature in geo.get("features", []):
        coords = feature["geometry"]["coordinates"]
        props = feature.get("properties", {})
        rows.append({"lat": coords[1], "lon": coords[0], **props})

    return pd.DataFrame(rows)


def get_cluster_for_point(lat, lon, cluster_grid: pd.DataFrame):
    """
    Encuentra el cluster del punto del grid más cercano a (lat, lon) por
    distancia euclídea simple (suficiente para esta escala — no necesita
    distancia real por calle, solo "a qué zona homogénea pertenece").

    Returns
    -------
    dict con {"cluster": int, "etiqueta": str, "distancia_grid_deg": float}
    o None si el grid está vacío.
    """
    if cluster_grid.empty:
        return None

    distancias = ((cluster_grid["lat"] - lat) ** 2 + (cluster_grid["lon"] - lon) ** 2) ** 0.5
    idx_mas_cercano = distancias.idxmin()
    fila = cluster_grid.loc[idx_mas_cercano]

    cluster_id = int(fila["cluster"])
    return {
        "cluster": cluster_id,
        "etiqueta": CLUSTER_LABELS.get(cluster_id, f"Cluster {cluster_id}"),
        "distancia_grid_deg": round(float(distancias[idx_mas_cercano]), 4),
    }
