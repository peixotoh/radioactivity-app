import os
from datetime import date
import tempfile
import requests
from bs4 import BeautifulSoup
import folium
from streamlit_folium import st_folium
import streamlit as st
from urllib.parse import urljoin
import fiona
import kml2geojson
from kml2geojson import convert
from io import BytesIO
import json
import re
import matplotlib.cm as cm
import matplotlib.colors as mcolors
from branca.colormap import linear
import pandas as pd
import matplotlib.pyplot as plt
import plotly.graph_objects as go

# ================== FUNCTIONS ==================

def style_function(feature):
    return {
        'fillColor': feature["properties"].get("fillColor", "#ff0000"),
        'color': "black",
        'weight': 1,
        'fillOpacity': 0.6,
    }
def get_contour_value(name):
    match = re.search(r"([\d.]+)", name)
    return float(match.group(1)) if match else 0

def extract_polygons_from_feature(feature):
    """Extract individual polygon features from various geometry types."""
    geometry = feature.get("geometry")
    props = feature.get("properties", {})
    extracted = []

    if not geometry:
        return extracted

    if geometry["type"] == "Polygon" or geometry["type"] == "MultiPolygon":
        extracted.append({
            "type": "Feature",
            "geometry": geometry,
            "properties": props
        })

    elif geometry["type"] == "GeometryCollection":
        for geom in geometry.get("geometries", []):
            if geom["type"] == "Polygon" or geom["type"] == "MultiPolygon":
                extracted.append({
                    "type": "Feature",
                    "geometry": geom,
                    "properties": props
                })

    return extracted

# =====================================================

# set up page configuration
st.set_page_config(page_title="Radioactive Cloud Viewer", page_icon=":radioactive:", layout="wide")

# create three columns
#col1, col2, col3 = st.columns([5,1,5])

# --------------------------------------------   select nuclear power plant
# option for nuclear power plant
central_options = st.sidebar.selectbox(
    "🏭 Choose Nuclear power  :red[_plant_]",
    ("Zarnowiec", "Tricastin", "Cattenon")
)

base_url = "https://nrisk.institutbiosphere.ch/"

if central_options == "Zarnowiec":
    page_url = urljoin(base_url, "kpcZA2_E31-en.html")
    central_name = "Zarnowiec"
    table_name = pd.read_html(page_url)[0]
elif central_options == "Tricastin":
    page_url = urljoin(base_url, "kpcTRI_E51-fr.html")
    central_name = "Tricastin"   
    table_name = pd.read_html(page_url)[0] 
else:
    page_url = urljoin(base_url, "kpcCAT_E51-en.html")
    central_name = "Cattenon"  
    table_name = pd.read_html(page_url)[0]  
    
# -----------------------------------------------------  Select date

# set interval for date input
default_date = date(2017, 1, 1)
min_date = date(2017, 1, 1)
max_date = date(2019, 12, 31)
selected_date = st.sidebar.date_input("📅 Choose Simulation Date (2017-2019)", value=default_date, min_value=min_date, max_value=max_date)
if not selected_date:
    st.stop()
date_str = selected_date.strftime("%Y-%m-%d")


# Get the page and find KML links
page = requests.get(page_url)
soup = BeautifulSoup(page.content, "html.parser")
links = soup.find_all("a", href=True)
matching_link = next((a["href"] for a in links if date_str in a.text), None)

if not matching_link:
    st.error(f"No KML file found for {date_str}")
    st.stop()

kml_url = urljoin(base_url, matching_link)

with tempfile.NamedTemporaryFile(suffix=".kml", delete=False) as tmp_file:
    tmp_file.write(requests.get(kml_url).content)
    local_kml_path = tmp_file.name


try:
    layers = fiona.listlayers(local_kml_path)
    geojson_files = convert(local_kml_path)

    # Find relevant layer
    concentration_layer = next(
        (layer for layer in geojson_files if any(
            "Contour" in feat["properties"].get("name", "") for feat in layer["features"]
        )),
        None
    )
    if not concentration_layer:
        st.error("No 'Contour Level' layer found.")
        st.stop()

    # Extract features source point
    point = concentration_layer["features"][0]
    
    # Filter polygons with valid geometry
    # Flatten all polygon-containing features
    polygons = []
    for f in concentration_layer["features"]:
        name = f.get("properties", {}).get("name", "")
        if "Contour Level" in name:
            extracted = extract_polygons_from_feature(f)
            polygons.extend(extracted)

    # ===============color polygons ================
    # Custom color map based on thresholds
    threshold_colors = [
        (500, "#FC0200"),
        (100, "#FFA000"),
        (50, "#FFFF01"),
        (20, "#BEFF00"),
        (6, "#00A300"),
        (1, "#00FF5B"),
        (0.1, "#02FDFF"),
    ]
    
    for f in polygons:
        level = get_contour_value(f["properties"].get("name", ""))
        f["properties"]["level"] = level
        
    # Normalize and apply colormap
    levels = [f["properties"]["level"] for f in polygons]
    norm = mcolors.Normalize(vmin=min(levels), vmax=max(levels))
    colormap = cm.get_cmap("YlOrRd")
    
    # Assign level and color to each polygon
    for f in polygons:
        name = f["properties"].get("name", "")
        level = get_contour_value(name)
        f["properties"]["level"] = level

        # Find the matching color based on the threshold
        for threshold, color in threshold_colors:
            if level >= threshold:
                f["properties"]["fillColor"] = color
                break
        else:
            # If level is less than the smallest threshold
            f["properties"]["fillColor"] = "#02FDFF"
    
    # ======================================================
        
    # Build GeoJSON for Folium
    contour_layer = {
        "type": "FeatureCollection",
        "features": polygons
    }
        
    # Download button for filtered polygons
    geojson_bytes = BytesIO()
    geojson_bytes.write(json.dumps(contour_layer).encode("utf-8"))
    geojson_bytes.seek(0)

     
        
    if polygons:
        # Build GeoJSON
        contour_layer = {
            "type": "FeatureCollection",
            "features": polygons
        }

        # Convert to bytes
        geojson_bytes = BytesIO()
        geojson_bytes.write(json.dumps(contour_layer).encode("utf-8"))
        geojson_bytes.seek(0)

        # Show download button in the sidebar
        st.sidebar.markdown("#### 🗂️ Export KML file")
        st.sidebar.download_button(
            label="📥 Download filtered polygons",
            data=geojson_bytes,
            file_name=f"simulation_{date_str}.geojson",
            mime="application/geo+json"
        )       
        
        st.sidebar.header("", divider="gray")
        
        # Sidebar legend after the download button
        st.sidebar.markdown("""
            <br>
            <b>Contour Level (mSv)</b>
            <div style="display: flex; align-items: center; padding: 5px;">
                <span style="display:inline-block; width:20px; height:15px; background-color:#FC0200;"></span><span style="margin-left: 8px;">≥ 500</span>
            </div>
            <div style="display: flex; align-items: center; padding: 5px;">
                <span style="display:inline-block; width:20px; height:15px; background-color:#FFA000;"></span><span style="margin-left: 8px;">≥ 100</span>
            </div>
            <div style="display: flex; align-items: center; padding: 5px;">
                <span style="display:inline-block; width:20px; height:15px; background-color:#FFFF01;"></span><span style="margin-left: 8px;">≥ 50</span>
            </div>
            <div style="display: flex; align-items: center; padding: 5px;">
                <span style="display:inline-block; width:20px; height:15px; background-color:#BEFF00;"></span><span style="margin-left: 8px;">≥ 20</span>
            </div>
            <div style="display: flex; align-items: center; padding: 5px;">
                <span style="display:inline-block; width:20px; height:15px; background-color:#00A300;"></span><span style="margin-left: 8px;">≥ 6</span>
            </div>
            <div style="display: flex; align-items: center; padding: 5px;">
                <span style="display:inline-block; width:20px; height:15px; background-color:#00FF5B;"></span><span style="margin-left: 8px;">≥ 1</span>
            </div>
            <div style="display: flex; align-items: center; padding: 5px;">
                <span style="display:inline-block; width:20px; height:15px; background-color:#02FDFF;"></span><span style="margin-left: 8px;">≥ 0.1</span>
            </div>
        """, unsafe_allow_html=True)

    
    # Display map
    m = folium.Map(location=[55, 22], zoom_start=4)
    folium.GeoJson(contour_layer, name="Contours", style_function=style_function).add_to(m)
    folium.GeoJson(point, name="Source").add_to(m)        
    
    # add layer control    
    folium.LayerControl().add_to(m)

    # title map
    st.header(f"☢️ Radioactive Cloud Simulation")
    st.subheader(f":red[_{central_name}_] - :blue[_{date_str}_]")
    
    # display map
    _ = st_folium(m, width=1000, height=600)

        
    # Change column names
    table_name.columns = [
        "Simulation Date", "≥ 1", "≥ 6", "≥ 20", "≥ 100", "≥ 500", "Collective Dose (persSv)"
    ]
    
    labels_cor = table_name.columns[1:-1]  # Skip first and last column
    
    
    # Loop through rows to find selected date
    for date_sel in table_name["Simulation Date"]:
        selected_date = str(date_sel)
        if date_str in selected_date:
            # Extract selected row
            selected_row = table_name.loc[table_name["Simulation Date"] == date_sel]

            # Convert values to integers
            values = [
                int(str(val).replace(" ", "").replace("\xa0", "")) 
                for val in selected_row.values[0][1:-1]
            ]

            # Generate different colors for each bar (you can customize this list)
            colors = ['#00FF5B', '#00A300', '#BEFF00', '#FFA000', '#FC0200']

            # Ensure colors match the number of bars (fill any excess with a default color if needed)
            while len(colors) < len(values):
                colors.append('#02FDFF')  # A default color for extra bars if needed

            st.subheader(f"Number of persons affected by the radioactive cloud in Europe for :blue[_{date_str}_]")

            # Only show button if polygons were successfully extracted
            #col1, col2 = st.columns([1,1])
            
            
        
            # Display the data as a table
            chart_data = pd.DataFrame({
                'Individual dose (mSv)': labels_cor,
                'Number of persons affected': values
            })
            st.write(chart_data)            
           
            
            # Create Plotly interactive bar chart with different colors for each bar
            fig = go.Figure(data=go.Bar(x=labels_cor, y=values, marker_color=colors))
            fig.update_layout(
                xaxis_title="Individual dose (mSv)",
                yaxis_title="Number of persons affected",
                xaxis_tickangle=-45
            )
            st.plotly_chart(fig)               
                    
            break
        
    # ==================== TABLE WITH 1096 SIMULATIONS ====================
    
    #st.header("", divider="gray")
    
    # title table
    st.subheader(f"Table with the results of 1096 meteorological simulations for :orange[_Europe_] ")
    
    # display table to download
    st.write(table_name) 
    
    # additional info
    st.markdown(f"This visualisation is based on the simulation of radioactive cloud released from the :red[_{central_name}_] on :blue[_{date_str}_]. For detailed information, maps and data, visit the Intitut Biosphèere web site: https://nrisk.institutbiosphere.ch/in-en.html")
          
               
finally:
    os.remove(local_kml_path)
