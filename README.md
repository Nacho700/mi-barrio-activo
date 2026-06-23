
**Live app:** https://trabajoedm.streamlit.app/

A Streamlit application that helps you decide **where to live in Valencia**
using real open government data instead of guesswork. It combines air
pollution, traffic-based noise estimation, accessibility to sports/green
space/public transport, and automatic neighbourhood clustering into a single
**Personal Urban Wellbeing Index (IBUP)** — personalised through user
profiles (family, athlete, older adult, or fully custom) that automatically
reweight what matters most to each one.

Academic project — UPV, Data Science degree (EDM coursework).

---

## What the app does

- **Compare up to 3 addresses** side by side with a single wellbeing score (0-100)
- **Choose a profile** (Balanced / Family with children / Athlete / Older adult / Custom) that reweights the index automatically
- **See exactly what's driving each score** with a stacked bar chart breakdown
- **Explore a city-wide neighbourhood type map** (K-means clustering, validated with a silhouette score)
- **Check real walking-distance rankings** — Top 5 nearest green spaces, sports facilities, markets, and health centres
- **Compare value for money** by entering a real asking price per address
- **Export a PDF report** of the full comparison

## Data Science methods used

1. **Spatial interpolation (IDW)** — estimates NO2/PM10/PM2.5 at any point in
   the city from Valencia's ~11 real monitoring stations, weighting them by
   inverse squared distance.
2. **Noise inference from traffic data** — Valencia's official noise dataset
   only has 4 stations with no usable dB values, so noise is estimated from
   real-time traffic intensity (IMV) at nearby street segments, using a
   standard logarithmic relationship from traffic acoustics with distance
   attenuation. Always labelled as an *estimate* in the UI, never presented
   as a measurement.
3. **Real-network accessibility** — walking times to sports facilities, bike
   lanes, green spaces, and public transport (EMT buses, FGV metro/tram,
   Valenbisi) are computed on Valencia's actual pedestrian street graph
   (OpenStreetMap via OSMnx), not straight-line distance.
4. **K-means clustering** — a ~400-point grid covering the whole municipality
   is clustered into 4 neighbourhood types based on pollution, noise, and
   accessibility. Validated with the elbow method (choosing k) and the
   silhouette score (checking cluster quality), both shown in the app rather
   than asserted.
5. **Weighted composite index** — the final IBUP score combines all
   components with user-adjustable weights, normalised so missing data
   doesn't unfairly penalise an address.

## Requirements

- Python 3.10+
- Internet connection (the app calls Valencia's open data API and
  OpenStreetMap live)

## Installation

```bash
git clone https://github.com/Nacho700/mi-barrio-activo.git
cd mi-barrio-activo
python -m venv venv
source venv/bin/activate        # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Data setup

**Nothing needs to be downloaded by hand to run the app** — it can call the
live APIs and cache results automatically. However, this repo already ships
with the data pre-downloaded in `data/raw/` and `data/processed/`
(including the pre-computed clustering grid), so it works out of the box.

To refresh the data yourself:

```bash
python src/data_loader.py --download-all
```

This downloads, into `data/raw/`:

| File | Content |
|---|---|
| `estaciones_contaminacion.geojson` | ~11 stations with current NO2, PM10, PM2.5, air quality label, emission type |
| `estaciones_ruido.geojson` | Location of the 4 official noise stations (no accessible dB values) |
| `intensidad_trafico.geojson` | Traffic intensity (IMV) per street segment — used to **estimate noise** |
| `arbolado.geojson` | Tree inventory (sampled to 5,000 points for performance) |
| `zonas_verdes.geojson` | Parks and gardens, with surface area and fitness equipment |
| `carril_bici.geojson` | Cycling routes |
| `equipamientos_municipales.geojson` | Municipal facilities (sports facilities, markets, health centres are filtered from this) |
| `intensidad_trafico.geojson` | Traffic intensity by segment |
| `paradas_emt.geojson` | EMT bus stops with their lines |
| `estaciones_fgv.geojson` | Metro/tram stations (FGV) |
| `valenbisi.geojson` | Bike-share stations with live availability |
| `grafo_valencia.graphml` (in `data/processed/`) | Valencia's pedestrian street network (OpenStreetMap via OSMnx) |
| `barrios_clusters.geojson` | Pre-computed K-means clustering grid (generated offline, see notebooks) |

If a dataset's URL changes on the geoportal, `src/data_loader.py` keeps all
endpoints in one `ARCGIS_LAYERS` dictionary at the top of the file.

**Note on the street graph's size**: if you upload this repo via GitHub's web
interface (25MB per-file limit), compress the `.graphml` to `.graphml.gz`
first — `src/accessibility.py` automatically loads either version.

## Running the app

```bash
streamlit run app.py
```

Opens at `http://localhost:8501`.

## Deploying online (free)

1. Push this repo to GitHub.
2. Go to [share.streamlit.io](https://share.streamlit.io), connect your
   GitHub account, select the repo and `app.py` as the entry point.
3. Deploy. You'll get a public URL — that's the "online app" link.

## Project structure

```
mi-barrio-activo/
├── app.py                          # Single-page app: hero + full comparator
├── src/
│   ├── data_loader.py              # Downloads and caches data from Valencia's geoportal
│   ├── data_helpers.py             # Shared loading functions (Streamlit-cached)
│   ├── interpolation.py            # IDW for pollution + nearest-station context
│   ├── noise_inference.py          # Noise estimation from traffic intensity
│   ├── accessibility.py            # Walking distances via OSMnx graph + Top-N rankings
│   ├── clustering.py               # K-means neighbourhood clustering + validation
│   ├── index.py                    # Personal Urban Wellbeing Index + user profiles
│   ├── geocoding.py                # Address text -> coordinates (ArcGIS, Nominatim fallback)
│   └── report_export.py            # PDF export of the comparison
├── data/
│   ├── raw/                        # Downloaded datasets
│   └── processed/                  # Cached street graph
├── .streamlit/
│   └── config.toml                 # Custom colour theme
├── requirements.txt
└── README.md
```

## Honesty notes (what this app does NOT claim)

- **Noise values are estimates**, not certified measurements — inferred from
  traffic intensity, since Valencia's official noise sensors don't expose
  usable values.
- **There is no open dataset of Valencia housing prices for sale.** The
  price field is entirely optional and user-entered; the app never invents
  or scrapes market prices.
- **The clustering grid is static**, regenerated offline (see the companion
  Colab notebooks used during development), not recomputed on every request
  — recalculating K-means with real-street accessibility for ~400 points on
  every click would be far too slow for an interactive app.
