"""
src/data_loader.py
===================
Descarga y cachea todos los datos necesarios desde:
  - El Geoportal del Ayuntamiento de València (servicios ArcGIS REST,
    MapServer, formato GeoJSON) — esta es la fuente real de los datos,
    el portal opendata.vlci.valencia.es (CKAN) solo los enlaza.
  - Un CSV directo por estación para los valores de contaminación.
  - OpenStreetMap (via OSMnx) para el grafo de calles.

IMPORTANTE — historial de esta función:
El portal de Valencia migró de Opendatasoft (valencia.opendatasoft.com,
ya CAÍDO) a un portal CKAN (opendata.vlci.valencia.es) que actúa solo como
catálogo/índice. Los datos reales se sirven desde geoportal.valencia.es
(servicios ArcGIS REST). Las URLs de abajo se verificaron consultando
opendata.vlci.valencia.es/api/3/action/package_show para cada dataset.

Si en el futuro alguna URL deja de funcionar:
    1. Ve a https://opendata.vlci.valencia.es/dataset/<slug>
    2. Mira los "Recursos" del dataset y copia la URL del formato GeoJSON
    3. Actualiza la URL correspondiente en ARCGIS_LAYERS o CSV_SOURCES

Uso:
    python src/data_loader.py --download-all
"""

import os
import json
import argparse
import time
from pathlib import Path

import requests
import pandas as pd

# ---------------------------------------------------------------------------
# CONFIGURACIÓN
# ---------------------------------------------------------------------------

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
PROCESSED_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"

RAW_DIR.mkdir(parents=True, exist_ok=True)
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

HEADERS = {"User-Agent": "MiBarrioActivo/1.0 (proyecto universitario UPV)"}

# Capas servidas por geoportal.valencia.es (ArcGIS REST / MapServer).
# Verificadas vía opendata.vlci.valencia.es (CKAN) el 21/06/2026.
ARCGIS_LAYERS = {
    "estaciones_contaminacion": (
        "https://geoportal.valencia.es/server/rest/services/OPENDATA/"
        "MedioAmbiente/MapServer/156/query"
    ),
    "estaciones_ruido": (
        "https://geoportal.valencia.es/server/rest/services/OPENDATA/"
        "MedioAmbiente/MapServer/160/query"
    ),
    "arbolado": (
        "https://geoportal.valencia.es/server/rest/services/OPENDATA/"
        "MedioAmbiente/MapServer/151/query"
    ),
    "zonas_verdes_actuales": (
        "https://geoportal.valencia.es/server/rest/services/OPENDATA/"
        "MedioAmbiente/MapServer/8/query"
    ),
    "carril_bici": (
        "https://geoportal.valencia.es/server/rest/services/OPENDATA/"
        "Trafico/MapServer/189/query"
    ),
    "equipamientos_municipales": (
        "https://geoportal.valencia.es/server/rest/services/OPENDATA/"
        "SociedadBienestar/MapServer/1/query"
    ),  # Capa "Equipamients municipals / Equipamientos municipales", verificada listando
    # las capas del MapServer SociedadBienestar (GetCapabilities devolvía solo GML/WFS,
    # pero la capa también se sirve vía REST MapServer estándar, igual que las demás).
    "intensidad_trafico": (
        "https://geoportal.valencia.es/server/rest/services/OPENDATA/"
        "Trafico/MapServer/188/query"
    ),  # Capa "Intensitat transit trams" — intensidad media de vehículos (IMV)
    # por tramo de calle. Se usa para inferir ruido (ver src/noise_inference.py),
    # ya que el dataset de ruido de Valencia (4 estaciones) no da valores en dB.
}

# CSV directos de contaminación por estación (un archivo por estación,
# actualizado por el Ayuntamiento con los datos del último mes).
CSV_ESTACIONES_CONTAMINACION = {
    "centro_8a": "https://mapas.valencia.es/WebsMunicipales/uploads/atmosferica/8A.csv",
    # Si quieres más estaciones, busca su CSV siguiendo el mismo patrón:
    # ve a https://opendata.vlci.valencia.es/dataset/dades-de-l-estacio-de-...
    # y copia la URL del recurso CSV. El patrón observado es:
    # https://mapas.valencia.es/WebsMunicipales/uploads/atmosferica/<CODIGO>.csv
    # Códigos vistos en el catálogo: 8A (Centro), 6A (Avda Francia),
    # 7A (Boulevar Sur), 3A (Moli del Sol), 4A (Pista de Silla),
    # 5A (Vivers), 1A (Universidad Politécnica).
}


def _get(url, params=None, retries=3, timeout=30):
    """GET con reintentos simples; lanza error claro si falla del todo."""
    last_err = None
    r = None
    for attempt in range(retries):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=timeout)
            r.raise_for_status()
            return r
        except requests.exceptions.HTTPError as e:
            last_err = e
            if r is not None and r.status_code == 404:
                raise RuntimeError(
                    f"\n[ERROR 404] No existe esa URL:\n  {r.url}\n"
                    "La URL puede haber cambiado en el geoportal. Revisa\n"
                    "ARCGIS_LAYERS / CSV_ESTACIONES_CONTAMINACION en\n"
                    "src/data_loader.py siguiendo las instrucciones del\n"
                    "docstring de este archivo."
                )
            time.sleep(2 * (attempt + 1))
        except requests.exceptions.RequestException as e:
            last_err = e
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"Fallo tras {retries} intentos llamando a {url}: {last_err}")


def download_arcgis_layer_as_geojson(layer_url: str, out_path: Path, page_size: int = 1000):
    """
    Descarga una capa completa de un servicio ArcGIS MapServer/query en
    formato GeoJSON, paginando con resultOffset (los servicios ArcGIS suelen
    limitar a 1000-2000 registros por petición vía MaxRecordCount).
    """
    print(f"  -> Descargando capa ArcGIS: {layer_url}")
    all_features = []
    offset = 0
    base_geojson = None

    while True:
        params = {
            "where": "1=1",
            "outFields": "*",
            "f": "geojson",
            "resultOffset": offset,
            "resultRecordCount": page_size,
        }
        r = _get(layer_url, params=params)
        data = r.json()

        if "error" in data:
            raise RuntimeError(f"Error de la API ArcGIS: {data['error']}")

        features = data.get("features", [])
        if base_geojson is None:
            base_geojson = {k: v for k, v in data.items() if k != "features"}

        if not features:
            break

        all_features.extend(features)
        offset += page_size

        if len(features) < page_size:
            break  # última página
        time.sleep(0.2)

    result = dict(base_geojson or {"type": "FeatureCollection"})
    result["features"] = all_features

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False)

    print(f"     Guardado en {out_path} ({len(all_features)} features)")
    return len(all_features)


def _normalize_column_name(col: str) -> str:
    """
    Convierte nombres de columna como 'NO2(µg/m³)' en 'no2', o 'Fecha' en
    'fecha', para que el resto del pipeline (data_helpers.py, interpolation.py)
    pueda referirse a ellos de forma consistente sin depender de símbolos
    Unicode que pueden venir mal codificados según el encoding del CSV.
    """
    col = col.strip().lower()
    # quitar cualquier paréntesis y su contenido, p.ej. "(µg/m³)", "(ug/m3)"
    col = col.split("(")[0].strip()
    # normalizar variantes conocidas
    replacements = {
        "pm2.5": "pm25",
        "pm2,5": "pm25",
    }
    return replacements.get(col, col)


def download_calidad_aire_csv():
    """
    Descarga el/los CSV de estaciones de contaminación atmosférica y los
    combina en un único calidad_aire_historico.csv con una columna
    'estacion_id' añadida para identificar el origen de cada fila.

    NOTA sobre encoding: estos CSV municipales vienen codificados en
    latin-1/cp1252 (típico de archivos generados desde Windows en
    administraciones españolas), NO en UTF-8. Si se leen como UTF-8 los
    símbolos especiales (µ, ³) se corrompen en caracteres "�". Por eso aquí
    se prueba primero latin-1.
    """
    print("  -> Descargando CSV de estaciones de contaminación...")
    dfs = []
    for nombre_estacion, url in CSV_ESTACIONES_CONTAMINACION.items():
        try:
            r = _get(url)
            from io import StringIO

            texto = None
            for encoding in ("latin-1", "cp1252", "utf-8"):
                try:
                    texto = r.content.decode(encoding)
                    break
                except UnicodeDecodeError:
                    continue
            if texto is None:
                raise ValueError("No se pudo decodificar el CSV con ningún encoding probado")

            df = pd.read_csv(StringIO(texto), sep=None, engine="python")
            df.columns = [_normalize_column_name(c) for c in df.columns]
            df["estacion_id"] = nombre_estacion
            dfs.append(df)
            print(f"     {nombre_estacion}: {len(df)} filas, columnas: {list(df.columns)}")
        except Exception as e:
            print(f"     [AVISO] No se pudo descargar {nombre_estacion}: {e}")

    if not dfs:
        print("     [AVISO] No se descargó ningún CSV de contaminación.")
        return

    combined = pd.concat(dfs, ignore_index=True)
    out_path = RAW_DIR / "calidad_aire_historico.csv"
    combined.to_csv(out_path, index=False, encoding="utf-8")
    print(f"     Guardado combinado en {out_path} ({len(combined)} filas totales)")
    print(f"     Columnas finales: {list(combined.columns)}")
    print(
        "     NOTA: este CSV NO incluye ruido (SPL) — el ruido se obtiene\n"
        "     por separado de estaciones_ruido.geojson. Si quieres ruido por\n"
        "     estación con valores históricos, revisa los datasets\n"
        "     'mapa-soroll-*' en opendata.vlci.valencia.es (mapas de ruido\n"
        "     24h/día/noche), que dan un índice por zona en vez de por\n"
        "     estación puntual — requeriría un tratamiento distinto."
    )


def download_all():
    print("=" * 70)
    print("Descargando datasets de Open Data València (geoportal ArcGIS)...")
    print("=" * 70)

    download_arcgis_layer_as_geojson(
        ARCGIS_LAYERS["estaciones_contaminacion"],
        RAW_DIR / "estaciones_contaminacion.geojson",
    )

    download_arcgis_layer_as_geojson(
        ARCGIS_LAYERS["estaciones_ruido"],
        RAW_DIR / "estaciones_ruido.geojson",
    )

    download_arcgis_layer_as_geojson(
        ARCGIS_LAYERS["arbolado"],
        RAW_DIR / "arbolado.geojson",
        page_size=1000,
    )

    download_arcgis_layer_as_geojson(
        ARCGIS_LAYERS["zonas_verdes_actuales"],
        RAW_DIR / "zonas_verdes.geojson",
    )

    download_arcgis_layer_as_geojson(
        ARCGIS_LAYERS["carril_bici"],
        RAW_DIR / "carril_bici.geojson",
    )

    download_arcgis_layer_as_geojson(
        ARCGIS_LAYERS["equipamientos_municipales"],
        RAW_DIR / "equipamientos_municipales.geojson",
    )

    download_arcgis_layer_as_geojson(
        ARCGIS_LAYERS["intensidad_trafico"],
        RAW_DIR / "intensidad_trafico.geojson",
    )

    download_street_graph()

    print("=" * 70)
    print("Descarga completa. Revisa data/raw/ y data/processed/")
    print("=" * 70)


def download_street_graph(place="Valencia, Spain"):
    """Descarga y cachea el grafo de calles peatonal de Valencia via OSMnx."""
    out_path = PROCESSED_DIR / "grafo_valencia.graphml"
    if out_path.exists():
        print(f"  -> Grafo ya existe en {out_path}, no se vuelve a descargar.")
        return

    print(f"  -> Descargando grafo de calles peatonal de '{place}' via OSMnx...")
    print("     (esto puede tardar 1-3 minutos la primera vez)")
    try:
        import osmnx as ox

        G = ox.graph_from_place(place, network_type="walk", simplify=True)
        ox.save_graphml(G, out_path)
        print(f"     Grafo guardado en {out_path} ({len(G.nodes)} nodos)")

        # Generar también una versión comprimida .gz: el .graphml de
        # Valencia sin comprimir supera el límite de 25MB que GitHub
        # permite subir vía su interfaz web; comprimido baja a ~5MB.
        # src/accessibility.py sabe cargar cualquiera de las dos versiones.
        import gzip
        import shutil

        gz_path = out_path.with_suffix(out_path.suffix + ".gz")
        with open(out_path, "rb") as f_in, gzip.open(gz_path, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)
        print(f"     Versión comprimida guardada en {gz_path} (para subir a GitHub si pesa más de 25MB)")
    except ImportError:
        print("     [ERROR] osmnx no está instalado. Ejecuta: pip install osmnx")
    except Exception as e:
        print(f"     [ERROR] No se pudo descargar el grafo: {e}")
        print("     Puede que 'Valencia, Spain' sea ambiguo en OSM; prueba con")
        print("     place='València, Comunitat Valenciana, Spain' si falla.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Descarga datos para Mi Barrio Activo y Sano")
    parser.add_argument("--download-all", action="store_true", help="Descarga todos los datasets")
    parser.add_argument(
        "--historico-csv",
        action="store_true",
        help="(Opcional) Descarga también el CSV histórico de la estación Centro (8A), por si quieres análisis temporal además de los valores actuales que ya trae estaciones_contaminacion.geojson",
    )
    args = parser.parse_args()

    if args.download_all:
        download_all()
        if args.historico_csv:
            download_calidad_aire_csv()
    elif args.historico_csv:
        download_calidad_aire_csv()
    else:
        print("Usa --download-all para descargar todos los datasets.")
        print("Ejemplo: python src/data_loader.py --download-all")
