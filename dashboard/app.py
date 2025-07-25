import requests
import plotly.express as px
import pandas as pd
from shiny.express import input, render, ui
from shiny import reactive
from shinywidgets import render_plotly
import datetime
from collections import deque
import json
from pathlib import Path
import time
from shiny import express
import matplotlib.pyplot as plt
import seaborn as sns

# Configuration
API_KEY = "api_weather_key"
TEXAS_CITIES = [
    "Houston", "San Antonio", "Dallas", "Austin", "Fort Worth",
    "El Paso", "Arlington", "Corpus Christi", "Plano", "Laredo",
    "Lubbock", "Garland", "Irving", "Amarillo", "Grand Prairie"
]
UNITS = "metric"
MAX_HISTORY = 1000  # Increased to accommodate multiple cities
HISTORY_FILE = "weather_history.json"

# Metric labels for display
METRIC_LABELS = {
    "temperature": "Temperature (°C)",
    "humidity": "Humidity (%)",
    "pressure": "Pressure (hPa)",
    "wind_speed": "Wind Speed (m/s)"
}

# Function to fetch weather data for all Texas cities
def fetch_all_texas_weather():
    weather_data = []
    for city in TEXAS_CITIES:
        url = f"https://api.openweathermap.org/data/2.5/weather?q={city},TX,US&appid={API_KEY}&units={UNITS}"
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            weather_data.append({
                "city": city,
                "temperature": data['main']['temp'],
                "humidity": data['main']['humidity'],
                "pressure": data['main']['pressure'],
                "wind_speed": data['wind']['speed'],
                "weather_condition": data['weather'][0]['main'],
                "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
        except (requests.RequestException, KeyError) as e:
            print(f"Error fetching weather for {city}: {e}")
    return weather_data

# UI Setup
ui.page_opts(title="Texas Weather Dashboard", fillable=True)

# Sidebar
with express.ui.sidebar(open="open"):
    ui.h2("Texas Weather Controls")
    express.ui.input_selectize(
        "selected_city",
        "Select City to Focus",
        choices=TEXAS_CITIES,
        selected="Plano"
    )
    express.ui.input_action_button("update_btn", "Refresh All Texas Cities", class_="btn-primary")
    
    ui.hr()
    express.ui.input_selectize(
        "selected_metric",
        "Select Metric to Visualize",
        choices=list(METRIC_LABELS.keys()),
        selected="temperature"
    )
    ui.input_numeric("history_hours", "History Hours", 24, min=1, max=MAX_HISTORY)
    ui.a("OpenWeatherMap API", href="https://openweathermap.org/api", target="_blank")

# Reactive data storage with file persistence
weather_history = reactive.Value(deque(maxlen=MAX_HISTORY))

# Load initial history from file or fetch initial data
@reactive.Effect
def load_initial_history():
    if Path(HISTORY_FILE).exists():
        with open(HISTORY_FILE, "r") as f:
            history = json.load(f)
            weather_history.set(deque(history, maxlen=MAX_HISTORY))
    else:
        initial_data = fetch_all_texas_weather()
        weather_history.set(deque(initial_data, maxlen=MAX_HISTORY))
        with open(HISTORY_FILE, "w") as f:
            json.dump(initial_data, f)

# Reactive calculation for filtered history
@reactive.calc
def filtered_history():
    history = list(weather_history.get())
    hours = input.history_hours()
    return history[-hours:] if hours <= len(history) else history

# Reactive effect for fetching and saving data for all cities
@reactive.Effect
@reactive.event(input.update_btn)
def update_weather():
    new_data = fetch_all_texas_weather()
    if new_data:
        current_history = weather_history.get()
        current_history.extend(new_data)  # Add all new data points
        
        with open(HISTORY_FILE, "w") as f:
            json.dump(list(current_history), f)
        
        weather_history.set(current_history)

# Reactive calculations for DataFrames
@reactive.calc
def current_weather_df():
    history = weather_history.get()
    # Get most recent entry for each city
    if history:
        df = pd.DataFrame(history)
        return df.sort_values('timestamp').groupby('city').last().reset_index()
    return pd.DataFrame()

@reactive.calc
def history_df():
    return pd.DataFrame(filtered_history())

@reactive.calc
def focused_city_df():
    df = history_df()
    if not df.empty:
        return df[df['city'] == input.selected_city()]
    return pd.DataFrame()

# Loading spinner
@render.ui
def loading_spinner():
    if not weather_history.get():
        return ui.tags.div(
            ui.tags.span(class_="spinner-border spinner-border-sm"),
            "Loading Texas weather data...",
            class_="text-center my-5"
        )

# Main layout
# Main layout
with ui.layout_columns():
    with ui.card(full_screen=True):
        ui.h2("Current Weather - All Texas Cities")
        @render.data_frame
        def current_weather():
            return express.render.DataTable(current_weather_df())

    with ui.card(full_screen=True):
        @render.ui
        def weather_history_header():
            return ui.h2(f"Weather History - {input.selected_city()}")
        
        @render.data_frame
        def weather_history_table():
            return express.render.DataGrid(focused_city_df())

# Visualization cards with full reactivity
with express.ui.layout_columns():
    @render_plotly
    def weather_trend():
        df = focused_city_df()
        selected_metric = input.selected_metric()
        
        if df.empty:
            return px.scatter(title="No data available").update_layout(showlegend=False)
        
        return px.line(
            df,
            x="timestamp",
            y=selected_metric,
            color="city",
            title=f"Texas Cities: {METRIC_LABELS[selected_metric]} Trend",
            labels={
                "timestamp": "Time",
                selected_metric: METRIC_LABELS[selected_metric]
            }
        ).update_traces(mode="lines+markers")

    @render.ui
    def weather_conditions():
        df = focused_city_df()
        selected_metric = input.selected_metric()
        
        if df.empty:
            return ui.tags.div("No data available", class_="text-muted")
        
        current = df.iloc[-1]
        metric_config = {
            "temperature": {
                "title": f"Temperature in {current['city']}",
                "value": f"{current['temperature']}°C",
                "icon": "bi-thermometer",
                "theme": "primary"
            },
            "humidity": {
                "title": f"Humidity in {current['city']}",
                "value": f"{current['humidity']}%",
                "icon": "bi-droplet",
                "theme": "info"
            },
            "pressure": {
                "title": f"Pressure in {current['city']}",
                "value": f"{current['pressure']} hPa",
                "icon": "bi-speedometer2",
                "theme": "warning"
            },
            "wind_speed": {
                "title": f"Wind Speed in {current['city']}",
                "value": f"{current['wind_speed']} m/s",
                "icon": "bi-wind",
                "theme": "success"
            }
        }
        
        config = metric_config.get(selected_metric, {
            "title": selected_metric.capitalize(),
            "value": str(current.get(selected_metric, "N/A")),
            "icon": "bi-question-circle",
            "theme": "secondary"
        })
        
        return ui.value_box(
            title=config["title"],
            value=config["value"],
            showcase=ui.tags.i(class_=f"bi {config['icon']}"),
            theme=config["theme"],
            full_screen=True
        )

with express.ui.card(full_screen=True):
    express.ui.card_header("Texas Cities: Metrics Correlation")
    @render_plotly
    def weather_correlation():
        df = focused_city_df()
        selected_metric = input.selected_metric()
        
        if df.empty:
            return px.scatter(title="No data available").update_layout(showlegend=False)
        
        return px.scatter_matrix(
            df,
            dimensions=list(METRIC_LABELS.keys()),
            color="city",
            title="Texas Cities: Metrics Correlation",
            labels=METRIC_LABELS
        )

# Update available metrics based on data
@reactive.Effect
def update_metric_filter():
    df = history_df()
    if not df.empty:
        available_metrics = [col for col in METRIC_LABELS.keys() if col in df.columns]
        express.ui.update_selectize("selected_metric", choices=available_metrics)