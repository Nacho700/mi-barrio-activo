"""
src/data_helpers.py
=====================
Funciones de carga de datos compartidas entre las páginas de Streamlit, con
@st.cache_data para no recargar los CSV/GeoJSON en cada interacción.
"""

import json
from pathlib import Path

import pandas as pd
import streamlit as st

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"


@st.cache_data
def load_estaciones_contaminacion():
    """Carga ubicación de estaciones desde el GeoJSON descargado."""
    path = RAW_DIR / "estaciones_contaminacion.geojson"
    if not path.exists():
        return pd.DataFrame(columns=["nombre", "lat", "lon"])

    with open(path, "r", encoding="utf-8") as f:
        geo = json.load(f)

    rows = []
    for feature in geo.get("features", []):
        coords = feature["geometry"]["coordinates"]
        props = feature.get("properties", {})
        rows.append(
            {
                "nombre": props.get("nombre") or props.get("estacio") or "Estación",
                "lat": coords[1],
                "lon": coords[0],
                **props,
            }
        )
    return pd.DataFrame(rows)


@st.cache_data
def load_calidad_aire_historico():
    """Carga el histórico de calidad del aire/ruido por estación."""
    path = RAW_DIR / "calidad_aire_historico.csv"
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


@st.cache_data
def load_geojson_points(filename, nombre_col_candidates=("nombre", "denominacio", "nom"), max_points=5000):
    """
    Carga un GeoJSON de puntos/líneas/polígonos y lo convierte en lista de
    dicts {"lat":, "lon":, "nombre":}. Útil para accessibility.py.

    max_points : int
        Si el dataset tiene más puntos que este límite (p.ej. el arbolado
        de Valencia tiene ~159.000 árboles), se hace un MUESTREO ALEATORIO
        a max_points. Esto es necesario por rendimiento: accessibility.py
        calcula distancia real por el grafo de calles a los candidatos más
        cercanos, y con 159k puntos el pre-filtro por distancia euclídea ya
        sería lento en cada consulta. Un muestreo de ~5000 puntos sigue
        dando muy buena cobertura espacial para estimar "¿hay un árbol/zona
        verde cerca?" sin sacrificar rendimiento perceptible.
    """
    path = RAW_DIR / filename
    if not path.exists():
        return []

    with open(path, "r", encoding="utf-8") as f:
        geo = json.load(f)

    features = geo.get("features", [])

    if len(features) > max_points:
        import random

        random.seed(42)  # reproducible
        features = random.sample(features, max_points)

    points = []
    for feature in features:
        geom = feature["geometry"]
        props = feature.get("properties", {})
        nombre = "Sin nombre"
        for c in nombre_col_candidates:
            if c in props and props[c]:
                nombre = props[c]
                break

        if geom["type"] == "Point":
            lon, lat = geom["coordinates"][:2]
            points.append({"lat": lat, "lon": lon, "nombre": nombre})
        elif geom["type"] in ("LineString",):
            # Para carril bici (líneas): usamos cada vértice como "punto accesible"
            for lon, lat in geom["coordinates"]:
                points.append({"lat": lat, "lon": lon, "nombre": nombre})
        elif geom["type"] in ("MultiLineString", "Polygon", "MultiPolygon"):
            # Tomamos solo el primer anillo/línea como aproximación razonable
            coords = geom["coordinates"][0]
            if geom["type"] == "MultiPolygon":
                coords = coords[0]
            for lon, lat in coords:
                points.append({"lat": lat, "lon": lon, "nombre": nombre})

    return points


@st.cache_data
def load_instalaciones_deportivas():
    """
    Carga instalaciones deportivas filtrando el GeoJSON de Equipamientos
    Municipales (que incluye también bibliotecas, mercados, centros de
    salud, etc.) por su campo de categoría.

    Columna real confirmada en el geoportal de Valencia: 'clase' (valores
    de texto como 'Instalaciones deportivas', 'Bibliotecas', 'Mercados',
    etc.), con 'idclase' como su código numérico equivalente y 'equipamien'
    como el nombre del lugar.

    NOTA histórica: una versión anterior de esta función detectaba la
    columna de categoría buscando automáticamente la palabra "deport" en
    cualquier columna de texto. Esto tenía un bug: el nombre del propio
    lugar (columna 'equipamien', p.ej. "Polideportivo Petxina") también
    contiene "deport", así que el detector se quedaba con la columna
    equivocada y solo encontraba instalaciones cuyo NOMBRE mencionaba la
    palabra, perdiendo las demás (p.ej. "Pista Atletismo Turia"). Ahora se
    usa directamente la columna 'clase' confirmada, con un fallback de
    detección solo si esa columna no existiera en el futuro.
    """
    path = RAW_DIR / "equipamientos_municipales.geojson"
    if not path.exists():
        return []

    with open(path, "r", encoding="utf-8") as f:
        geo = json.load(f)

    features = geo.get("features", [])
    if not features:
        return []

    sample_props = features[0].get("properties", {})

    if "clase" in sample_props:
        categoria_col = "clase"
    else:
        # Fallback: buscar una columna cuyo NOMBRE (no su valor) sugiera
        # que es la categoría, evitando columnas de nombre propio como
        # 'equipamien'/'nombre'.
        categoria_col = None
        candidatos_nombre_columna = ["clase", "categoria", "tipo", "idclase", "idsubclase"]
        for candidato in candidatos_nombre_columna:
            if candidato in sample_props:
                categoria_col = candidato
                break

    if categoria_col is None:
        print(
            "[AVISO] No se encontró una columna de categoría reconocible en "
            "equipamientos_municipales.geojson (se esperaba 'clase'). "
            "Revisa las propiedades del GeoJSON y ajusta "
            "load_instalaciones_deportivas() en src/data_helpers.py."
        )
        return []

    points = []
    for feature in features:
        props = feature.get("properties", {})
        valor_categoria = str(props.get(categoria_col, ""))
        if not any(kw in valor_categoria.lower() for kw in ["deport", "esport"]):
            continue
        geom = feature.get("geometry")
        if not geom or geom.get("type") != "Point":
            continue
        lon, lat = geom["coordinates"][:2]
        nombre = props.get("equipamien") or props.get("nombre") or "Instalación deportiva"
        points.append({"lat": lat, "lon": lon, "nombre": nombre})

    if not points:
        print(
            "[AVISO] No se encontraron instalaciones deportivas en "
            "equipamientos_municipales.geojson usando la columna "
            f"'{categoria_col}'. Revisa manualmente las propiedades del "
            "GeoJSON y ajusta load_instalaciones_deportivas() en "
            "src/data_helpers.py si el valor de categoría cambió."
        )

    return points


@st.cache_data
def load_estaciones_ruido():
    """Carga ubicación de estaciones de ruido desde su GeoJSON propio."""
    path = RAW_DIR / "estaciones_ruido.geojson"
    if not path.exists():
        return pd.DataFrame(columns=["nombre", "lat", "lon"])

    with open(path, "r", encoding="utf-8") as f:
        geo = json.load(f)

    rows = []
    for feature in geo.get("features", []):
        coords = feature["geometry"]["coordinates"]
        props = feature.get("properties", {})
        rows.append(
            {
                "nombre": props.get("nombre") or props.get("nom") or "Estación de ruido",
                "lat": coords[1],
                "lon": coords[0],
                **props,
            }
        )
    return pd.DataFrame(rows)


def get_latest_pollution_by_station(historico_df=None, estaciones_df=None):
    """
    Devuelve el DataFrame de estaciones de contaminación listo para
    interpolation.py.

    IMPORTANTE — esto cambió respecto a versiones anteriores: la capa
    'estaciones_contaminacion.geojson' del geoportal de Valencia YA TRAE
    los valores ACTUALES de no2, pm10 y pm25 directamente en sus
    propiedades (confirmado: columnas 'no2', 'pm10', 'pm25', además de
    'calidad_am' con interpretación textual y 'fecha_carg' con timestamp
    de la última actualización). No hace falta combinar con ningún CSV
    histórico para tener un valor por estación — por eso esta función
    ahora solo valida y devuelve estaciones_df tal cual.

    Se mantienen los parámetros 'historico_df' y 'estaciones_df' (en vez
    de cambiar la firma a un solo argumento) para no romper las llamadas
    existentes en pages/*.py; 'historico_df' simplemente se ignora ahora.

    Si en el futuro quieres usar el CSV histórico (p.ej. para series
    temporales o para más estaciones con histórico), usa
    src/data_loader.py download_calidad_aire_csv() y construye tu propia
    función de combinación — esta ya no lo necesita para el caso de uso
    principal de la app (valor actual por estación).
    """
    if estaciones_df is None or estaciones_df.empty:
        return pd.DataFrame()

    columnas_esperadas = ["no2", "pm10", "pm25"]
    faltantes = [c for c in columnas_esperadas if c not in estaciones_df.columns]
    if faltantes:
        print(
            f"[AVISO] estaciones_contaminacion no tiene las columnas {faltantes}. "
            "Revisa que el GeoJSON se haya descargado correctamente y que el "
            "geoportal no haya cambiado los nombres de campo."
        )

    return estaciones_df


def get_estaciones_ruido_con_valor(ruido_df, valor_por_defecto=55.0):
    """
    El dataset de estaciones de ruido de Valencia (4 estaciones) da solo
    ubicación + un enlace a un CSV externo de mediciones
    (mapas.valencia.es/.../ruido.csv), no un valor en dB ya en el GeoJSON.

    Como aproximación HONESTA Y DOCUMENTADA para el MVP, se asigna un
    valor de referencia fijo (55 dB, nivel típico de tráfico urbano
    moderado según la OMS) a todas las estaciones, hasta que se procese
    ese CSV externo de mediciones reales.

    Esto se expone explícitamente en la UI (ver pages/) para que el
    usuario sepa que el componente de ruido es una aproximación, no una
    medición real.
    """
    if ruido_df.empty:
        return pd.DataFrame()
    df = ruido_df.copy()
    df["ruido_db"] = valor_por_defecto
    return df
