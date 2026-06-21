# Mi Barrio Activo y Sano

Aplicación Streamlit que ayuda a decidir **dónde vivir en Valencia** combinando
contaminación, ruido, acceso a deporte y zonas verdes en un único índice
personal — y genera un **informe de incidencia ciudadana** cuantificado para
defender mejoras concretas (carril bici, arbolado, instalación deportiva) en
una zona ante el ayuntamiento o la asociación de vecinos.

## 1. Requisitos

- Python 3.10+
- Conexión a internet (la app llama en vivo a la API de Open Data València
  y a OpenStreetMap; no necesitas tener los datos descargados a mano, pero
  puedes pre-descargarlos para ir más rápido — ver sección 3)

## 2. Instalación

```bash
git clone <tu-repo>
cd mi-barrio-activo
python -m venv venv
source venv/bin/activate        # En Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## 3. Datos: ¿qué te tienes que descargar?

**Buena noticia: NADA es obligatorio descargar a mano.** Toda la app llama
en vivo a las APIs públicas (Open Data València vía Opendatasoft, y
OpenStreetMap vía OSMnx) y cachea los resultados automáticamente en
`data/raw/` y `data/processed/` la primera vez que se ejecuta.

Aun así, te recomiendo **pre-descargar y cachear todo ANTES de la demo en
vídeo**, para que la app vaya rápida y no dependas de la red en directo
delante del jurado. Para eso:

```bash
python src/data_loader.py --download-all
```

Esto descarga y guarda en `data/raw/`:

| Archivo generado | Fuente | Contenido |
|---|---|---|
| `estaciones_contaminacion.geojson` | Open Data València (Opendatasoft) | Ubicación de las ~10 estaciones de calidad del aire/ruido |
| `calidad_aire_historico.csv` | Open Data València | Histórico diario de NO2, PM10, PM2.5, ruido (SPL) por estación |
| `arbolado.geojson` | Open Data València | Inventario de arbolado (puntos geolocalizados) |
| `zonas_verdes.geojson` | Open Data València | Parques y jardines actuales/planificados |
| `carril_bici.geojson` | Open Data València | Itinerarios ciclistas (líneas) |
| `instalaciones_deportivas.csv` | datos.gob.es / geoportal Ayto. Valencia | Pistas, polideportivos, piscinas municipales |
| `grafo_valencia.graphml` | OpenStreetMap (vía OSMnx) | Red de calles peatonal de Valencia, para calcular distancias a pie |

Si algún dataset cambia de nombre o de URL en el portal (Opendatasoft
actualiza sus catálogos de vez en cuando), `src/data_loader.py` tiene al
principio un diccionario `DATASET_IDS` con todos los identificadores — solo
hay que corregir ahí, no en el resto del código. Instrucciones de cómo
verificarlo están en el propio archivo.

## 4. Cómo correr la app

```bash
streamlit run app.py
```

Se abre en `http://localhost:8501`.

## 5. Desplegar online (gratis)

1. Sube el repo a GitHub (incluye `requirements.txt`, NO subas `data/raw`
   ni `data/processed` si pesan mucho — añádelos a `.gitignore`, la app los
   regenera sola).
2. Ve a [share.streamlit.io](https://share.streamlit.io), conecta tu cuenta
   de GitHub, elige el repo y `app.py` como entry point.
3. Despliega. Te da una URL pública tipo
   `https://mi-barrio-activo.streamlit.app` — esa es tu "link a la app
   online" para la entrega.

## 6. Estructura del proyecto

```
mi-barrio-activo/
├── app.py                       # Página principal / navegación
├── pages/
│   ├── 1_comparador.py          # Comparar hasta 3 direcciones candidatas
│   ├── 2_mi_rutina.py           # Rutina diaria o GPX → exposición acumulada
│   └── 3_simulador_incidencia.py # Simular mejora + generar informe PDF
├── src/
│   ├── data_loader.py            # Descarga y cachea datos de Open Data VLC
│   ├── interpolation.py          # IDW para contaminación/ruido en cualquier punto
│   ├── accessibility.py          # Distancias a pie via grafo OSMnx
│   ├── index.py                  # Cálculo del Índice de Bienestar Urbano Personal
│   ├── simulator.py              # Recalculo antes/después al simular mejora
│   ├── geocoding.py               # Dirección de texto -> coordenadas (Nominatim)
│   └── report.py                  # Generación del informe PDF de incidencia
├── data/
│   ├── raw/                      # Datos descargados (se genera solo)
│   └── processed/                 # Grafo cacheado, grids interpolados (se genera solo)
├── outputs/                       # PDFs generados por el simulador
├── requirements.txt
└── README.md
```

## 7. Metodología de Data Science (resumen para la memoria/vídeo)

1. **Interpolación espacial (IDW)** de contaminación (NO2, PM10) y ruido (SPL)
   entre las ~10 estaciones fijas de Valencia, para estimar la exposición en
   cualquier punto de la ciudad, no solo donde hay sensor.
2. **Modelo de accesibilidad** basado en grafos: usando la red de calles real
   (OSMnx/NetworkX) se calcula el tiempo a pie hasta el carril bici, parque o
   instalación deportiva más cercana — no distancia en línea recta, sino
   distancia real caminando por las calles.
3. **Índice compuesto personalizable**: el usuario pondera cuánto le importa
   cada factor (contaminación, ruido, verde, deporte) y el índice se
   recalcula con sus pesos.
4. **Exposición acumulada en rutina/ruta**: en vez de evaluar solo un punto,
   se suma la exposición a lo largo de todos los tramos de la rutina diaria
   o ruta GPX del usuario.
5. **Simulación antes/después**: al proponer una mejora de infraestructura en
   un punto, se recalcula el índice solo en el radio de influencia relevante
   y se cuantifica la diferencia — esto alimenta el informe de incidencia.
