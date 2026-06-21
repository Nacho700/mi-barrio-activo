"""
pages/2_mi_rutina.py
======================
Calcula la exposición acumulada a lo largo de una rutina diaria (varias
direcciones en orden) o de una ruta GPX subida por el usuario (p.ej.
exportada de Garmin/Strava).

NOTA sobre ruido: el dataset de ruido de Valencia (4 estaciones) solo da
ubicación, sin valores en dB descargables de forma simple por esta vía.
Esta página usa NO2, PM10 y PM2.5 (con datos reales e interpolados), que sí
están disponibles.

NOTA TÉCNICA sobre session_state: st_folium (el mapa interactivo) dispara
un re-run completo del script en cuanto se renderiza. Si los resultados
solo existieran dentro del bloque "if st.button(...):", ese re-run los
borraría de inmediato (síntoma: "los resultados aparecen 1 segundo y
desaparecen"). Por eso aquí los resultados se guardan en
st.session_state y el bloque que los muestra es independiente del botón.
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

import streamlit as st
import pandas as pd
import plotly.express as px
import folium
from streamlit_folium import st_folium
import gpxpy

from src.geocoding import geocode_address
from src.data_helpers import load_estaciones_contaminacion
from src.interpolation import estimate_environmental_profile

st.set_page_config(page_title="Mi rutina | Mi Barrio Activo", page_icon="🗺️", layout="wide")
st.title("🗺️ Exposición de mi rutina")
st.markdown(
    "Calcula tu exposición acumulada a contaminación a lo largo de tu día, "
    "no solo en un punto. Puedes introducir tu rutina como una lista de "
    "paradas, o subir un archivo **GPX** de un entreno real (por ejemplo "
    "exportado de Garmin Connect o Strava)."
)
st.caption(
    "ℹ️ Se muestran NO2, PM10 y PM2.5 (con datos reales del Ayuntamiento). "
    "El ruido todavía no está disponible: el dataset de Valencia solo da "
    "ubicación de estaciones, sin valores en dB accesibles de forma simple."
)

modo = st.radio("¿Cómo quieres introducir tu recorrido?", ["Rutina diaria (direcciones)", "Subir GPX"])

stations_with_values = load_estaciones_contaminacion()


def evaluar_puntos(puntos):
    """puntos: lista de dicts {"lat":, "lon":, "etiqueta":}"""
    filas = []
    for p in puntos:
        perfil = estimate_environmental_profile(p["lat"], p["lon"], stations_with_values)
        filas.append({**p, **perfil})
    return pd.DataFrame(filas)


def mostrar_resultados_rutina(df, titulo):
    st.divider()
    st.subheader(titulo)
    st.dataframe(df[["etiqueta", "no2", "pm10", "pm25"]])

    st.markdown("##### Exposición acumulada (media)")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("NO2 medio (µg/m³)", f"{df['no2'].mean():.1f}")
    with col2:
        st.metric("PM10 medio (µg/m³)", f"{df['pm10'].mean():.1f}")
    with col3:
        st.metric("PM2.5 medio (µg/m³)", f"{df['pm25'].mean():.1f}")

    fig = px.line(df, x="etiqueta" if "etiqueta" in df.columns else None,
                   y=["no2", "pm10", "pm25"], markers=True,
                   title="Evolución de exposición a lo largo de tu recorrido")
    st.plotly_chart(fig, width="stretch")

    mapa = folium.Map(location=[df["lat"].mean(), df["lon"].mean()], zoom_start=13)
    coords = df[["lat", "lon"]].values.tolist()
    folium.PolyLine(coords, color="blue", weight=3, opacity=0.6).add_to(mapa)
    max_no2 = df["no2"].max() or 1
    for _, row in df.iterrows():
        color = "red" if row["no2"] and row["no2"] / max_no2 > 0.66 else (
            "orange" if row["no2"] and row["no2"] / max_no2 > 0.33 else "green"
        )
        folium.CircleMarker(
            [row["lat"], row["lon"]], radius=5, color=color, fill=True, fill_opacity=0.8,
            tooltip=f"{row.get('etiqueta', '')} — NO2: {row['no2']}, PM2.5: {row['pm25']}",
        ).add_to(mapa)
    st_folium(mapa, width=900, height=450, key="mapa_rutina")


if modo == "Rutina diaria (direcciones)":
    st.markdown("##### Introduce tu rutina en orden")
    n_paradas = st.slider("Número de paradas", 2, 6, 3)

    direcciones = []
    for i in range(n_paradas):
        d = st.text_input(f"Parada {i+1}", key=f"parada_{i}", placeholder="Ej: Casa, Facultad, Gimnasio...")
        direcciones.append(d)

    if st.button("Calcular exposición de mi rutina", type="primary"):
        direcciones_validas = [d for d in direcciones if d.strip()]
        if len(direcciones_validas) < 2:
            st.warning("Introduce al menos 2 paradas.")
            st.stop()

        if stations_with_values.empty:
            st.error("No hay datos de estaciones cargados. Ejecuta data_loader.py primero.")
            st.stop()

        puntos = []
        with st.spinner("Geocodificando direcciones..."):
            for d in direcciones_validas:
                geo = geocode_address(d)
                if geo is None:
                    st.warning(f"No se pudo localizar: '{d}'")
                    continue
                puntos.append({"lat": geo["lat"], "lon": geo["lon"], "etiqueta": d})

        if len(puntos) < 2:
            st.session_state.pop("rutina_df", None)
            st.stop()

        df = evaluar_puntos(puntos)
        st.session_state["rutina_df"] = df
        st.session_state["rutina_titulo"] = "Resultado por parada"

    if "rutina_df" in st.session_state:
        mostrar_resultados_rutina(st.session_state["rutina_df"], st.session_state["rutina_titulo"])

else:
    st.markdown("##### Sube tu archivo GPX")
    st.caption(
        "Puedes exportar tus entrenos desde Garmin Connect (Actividad → ⚙️ → "
        "Exportar a GPX) o desde Strava (Exportar GPX en el menú de la "
        "actividad)."
    )
    gpx_file = st.file_uploader("Archivo .gpx", type=["gpx"])

    sample_every_n = st.slider(
        "Frecuencia de muestreo (cada cuántos puntos del GPX evaluar)",
        5, 100, 20,
        help="Un GPX puede tener miles de puntos; evaluamos 1 de cada N para no saturar la API de interpolación.",
    )

    if gpx_file is not None and st.button("Calcular exposición de mi ruta", type="primary"):
        if stations_with_values.empty:
            st.error("No hay datos de estaciones cargados. Ejecuta data_loader.py primero.")
            st.stop()

        gpx = gpxpy.parse(gpx_file)
        puntos_gpx = []
        for track in gpx.tracks:
            for segment in track.segments:
                for i, point in enumerate(segment.points):
                    if i % sample_every_n == 0:
                        puntos_gpx.append(
                            {"lat": point.latitude, "lon": point.longitude, "etiqueta": f"Punto {i}"}
                        )

        if not puntos_gpx:
            st.warning("No se encontraron puntos de track en el GPX. ¿El archivo tiene una traza válida?")
            st.session_state.pop("rutina_df", None)
            st.stop()

        with st.spinner(f"Evaluando {len(puntos_gpx)} puntos de tu ruta..."):
            df = evaluar_puntos(puntos_gpx)

        st.session_state["rutina_df"] = df
        st.session_state["rutina_titulo"] = f"Resultado de tu ruta ({len(df)} puntos evaluados)"

    if "rutina_df" in st.session_state:
        mostrar_resultados_rutina(st.session_state["rutina_df"], st.session_state["rutina_titulo"])
        st.info(
            "💡 Compara esta ruta con una alternativa (p.ej. por el cauce del "
            "Turia en vez de por una avenida con tráfico) subiendo otro GPX y "
            "viendo qué media de NO2/PM2.5 te da.",
            icon="💡",
        )
