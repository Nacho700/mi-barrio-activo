"""
pages/3_simulador_incidencia.py
==================================
Simula el efecto de una mejora de infraestructura (carril bici, instalación
deportiva, arbolado) cerca de una dirección, y genera un informe PDF de
incidencia ciudadana con la evidencia cuantificada.

NOTA TÉCNICA sobre session_state: tanto st_folium como un segundo
st.button() anidado dentro de un bloque "if primer_boton:" provocan que ese
bloque exterior deje de cumplirse en el siguiente re-run (el botón ya no
está "recién pulsado"), borrando los resultados. Por eso el resultado de
la simulación se guarda en st.session_state y se muestra en un bloque
independiente del botón "Simular impacto".
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium

from src.geocoding import geocode_address
from src.data_helpers import (
    load_estaciones_contaminacion,
    load_geojson_points,
    load_instalaciones_deportivas,
)
from src.interpolation import estimate_environmental_profile
from src.accessibility import compute_accessibility_profile
from src.simulator import simulate_improvement, MEJORA_TIPOS
from src.report import generar_informe_incidencia, COMPONENTE_LABELS

st.set_page_config(page_title="Simulador de incidencia | Mi Barrio Activo", page_icon="📄", layout="wide")
st.title("📄 Simulador de incidencia ciudadana")
st.markdown(
    """
¿Crees que a tu zona le falta un carril bici, una pista deportiva o más
arbolado? Esta herramienta **no construye nada** — eso depende del
Ayuntamiento — pero te da **evidencia cuantificada** de cuánto mejoraría
objetivamente tu Índice de Bienestar Urbano Personal, lista para incluir en
una petición a tu asociación de vecinos, una instancia municipal o una
propuesta de presupuestos participativos.
"""
)

st.divider()

col_a, col_b = st.columns(2)
with col_a:
    direccion = st.text_input("📍 Dirección de referencia (tu piso o zona)", placeholder="Calle, número, Valencia")
with col_b:
    tipo_mejora = st.selectbox(
        "🏗️ Tipo de mejora a simular",
        options=list(MEJORA_TIPOS.keys()),
        format_func=lambda k: MEJORA_TIPOS[k]["nombre"],
    )

st.markdown(
    "Pincha en el mapa para indicar **dónde** se ubicaría la mejora "
    "(por ejemplo, la calle donde te gustaría que pusieran el carril bici)."
)

mapa_click = folium.Map(location=[39.4699, -0.3763], zoom_start=13)
mapa_click.add_child(folium.LatLngPopup())
click_result = st_folium(mapa_click, width=900, height=450, key="mapa_simulador")

punto_mejora = None
if click_result and click_result.get("last_clicked"):
    punto_mejora = {
        "lat": click_result["last_clicked"]["lat"],
        "lon": click_result["last_clicked"]["lng"],
    }
    st.success(f"Punto seleccionado: {punto_mejora['lat']:.5f}, {punto_mejora['lon']:.5f}")
    # Guardamos también el punto en session_state por si el re-run del
    # propio mapa lo necesitara más adelante en el mismo ciclo.
    st.session_state["punto_mejora"] = punto_mejora
elif "punto_mejora" in st.session_state:
    punto_mejora = st.session_state["punto_mejora"]

ejecutar = st.button("🔬 Simular impacto", type="primary")

if ejecutar:
    if not direccion.strip():
        st.warning("Introduce una dirección de referencia.")
        st.stop()
    if punto_mejora is None:
        st.warning("Pincha en el mapa para indicar dónde iría la mejora.")
        st.stop()

    with st.spinner("Cargando datos y calculando..."):
        geo = geocode_address(direccion)
        if geo is None:
            st.error(f"No se pudo localizar la dirección '{direccion}'.")
            st.stop()

        lat, lon = geo["lat"], geo["lon"]

        stations_with_values = load_estaciones_contaminacion()

        if stations_with_values.empty:
            st.error("No hay datos de estaciones cargados. Ejecuta data_loader.py primero.")
            st.stop()

        carril_bici_points = load_geojson_points("carril_bici.geojson")
        verde_points = load_geojson_points("zonas_verdes.geojson") + load_geojson_points("arbolado.geojson")
        deporte_points = load_instalaciones_deportivas()

        perfil_ambiental = estimate_environmental_profile(lat, lon, stations_with_values)

        try:
            perfil_acceso = compute_accessibility_profile(
                lat, lon, carril_bici_points, deporte_points, verde_points
            )
        except FileNotFoundError as e:
            st.error(str(e))
            st.stop()

        raw_values_actuales = {
            "no2": perfil_ambiental.get("no2"),
            "pm10": perfil_ambiental.get("pm10"),
            "pm25": perfil_ambiental.get("pm25"),
            # Ruido no disponible: ver nota de metodología en el informe
            "tiempo_deporte_min": perfil_acceso["deporte"]["minutos"] if perfil_acceso["deporte"] else None,
            "tiempo_bici_min": perfil_acceso["carril_bici"]["minutos"] if perfil_acceso["carril_bici"] else None,
            "tiempo_verde_min": perfil_acceso["verde"]["minutos"] if perfil_acceso["verde"] else None,
        }

        resultado = simulate_improvement(
            lat=lat,
            lon=lon,
            tipo_mejora=tipo_mejora,
            punto_mejora=punto_mejora,
            raw_values_actuales=raw_values_actuales,
            carril_bici_points=carril_bici_points,
            deporte_points=deporte_points,
            verde_points=verde_points,
        )

    # Guardamos en session_state para que sobreviva a cualquier re-run
    # posterior (p.ej. al pulsar el botón de generar PDF más abajo).
    st.session_state["simulacion_resultado"] = resultado
    st.session_state["simulacion_direccion"] = geo["direccion_completa"]

# ---------------------------------------------------------------------------
# Mostrar resultados (independiente del botón "Simular impacto", para que
# no desaparezcan al interactuar con el botón de generar PDF)
# ---------------------------------------------------------------------------
if "simulacion_resultado" in st.session_state:
    resultado = st.session_state["simulacion_resultado"]
    direccion_simulada = st.session_state["simulacion_direccion"]

    st.divider()
    st.subheader("Resultado de la simulación")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("IBUP antes", f"{resultado['antes']['ibup']}/100")
    with col2:
        st.metric("IBUP después", f"{resultado['despues']['ibup']}/100")
    with col3:
        diff = resultado["diferencia_ibup"]
        st.metric("Diferencia", f"{'+' if diff and diff > 0 else ''}{diff} pts")

    st.markdown("##### Detalle por componente")

    filas = []
    for k, label in COMPONENTE_LABELS.items():
        a = resultado["antes"]["componentes"].get(k)
        d = resultado["despues"]["componentes"].get(k)
        diff_c = resultado["diferencia_componentes"].get(k)
        if a is None and d is None:
            continue
        filas.append({"Componente": label, "Antes": a, "Después": d, "Diferencia": diff_c})

    st.dataframe(pd.DataFrame(filas), width="stretch")

    st.warning(
        "⚠️ Esta simulación estima accesibilidad/exposición con los métodos "
        "descritos en la metodología del informe. No modela tráfico inducido "
        "ni garantiza que el Ayuntamiento ejecute la obra — es evidencia de "
        "apoyo a una petición ciudadana, no una predicción oficial.",
        icon="⚠️",
    )

    st.divider()
    st.subheader("📄 Generar informe de incidencia")
    if st.button("Generar PDF descargable"):
        with st.spinner("Generando informe..."):
            pdf_path = generar_informe_incidencia(direccion_simulada, resultado)
        with open(pdf_path, "rb") as f:
            st.session_state["pdf_bytes"] = f.read()
            st.session_state["pdf_name"] = pdf_path.name
        st.success("Informe generado. Puedes descargarlo abajo.")

    if "pdf_bytes" in st.session_state:
        st.download_button(
            "⬇️ Descargar informe PDF",
            data=st.session_state["pdf_bytes"],
            file_name=st.session_state["pdf_name"],
            mime="application/pdf",
        )
