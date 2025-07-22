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

# Configuration
API_KEY = "api_weather_key"
DEFAULT_CITY = "Dallas"
UNITS = "metric"
MAX_HISTORY = 168
HISTORY_FILE = "weather_history.json"

# Metric labels for display
METRIC_LABELS = {
    "temperature": "Temperature (°C)",
    "humidity": "Humidity (%)",
    "pressure": "Pressure (hPa)",
    "wind_speed": "Wind Speed (m/s)"
}

# Function to fetch weather data
def fetch_weather(city):
    url = f"https://api.openweathermap.org/data/2.5/weather?q={city}&appid={API_KEY}&units={UNITS}"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        return {
            "city": city,
            "temperature": data['main']['temp'],
            "humidity": data['main']['humidity'],
            "pressure": data['main']['pressure'],
            "wind_speed": data['wind']['speed'],
            "weather_condition": data['weather'][0]['main'],
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
    except (requests.RequestException, KeyError) as e:
        print(f"Error fetching weather: {e}")
        return None

# Initialize with test data
weather_data = fetch_weather(DEFAULT_CITY)
print(weather_data)

# UI Setup
ui.page_opts(title="Live Weather Dashboard", fillable=True)

# Sidebar
with ui.sidebar(open="open"):
    ui.h2("Weather Controls")
    ui.input_text("city_input", "Enter City", DEFAULT_CITY)
    ui.input_action_button("update_btn", "Get Weather", class_="btn-primary")
    
    ui.hr()
    ui.input_selectize(
        "selected_metric",
        "Select Metric to Visualize",
        choices=list(METRIC_LABELS.keys()),
        selected="temperature"
    )
    ui.input_numeric("history_hours", "History Hours", 24, min=1, max=MAX_HISTORY)
    ui.a("OpenWeatherMap API", href="https://openweathermap.org/api", target="_blank")

# Reactive data storage with file persistence
weather_history = reactive.Value(deque(maxlen=MAX_HISTORY))

# Load initial history from file
@reactive.Effect
def load_initial_history():
    if Path(HISTORY_FILE).exists():
        with open(HISTORY_FILE, "r") as f:
            history = json.load(f)
            weather_history.set(deque(history, maxlen=MAX_HISTORY))

# Custom file reader with polling
@reactive.calc
def file_reader():
    if Path(HISTORY_FILE).exists():
        with open(HISTORY_FILE, "r") as f:
            return json.load(f)
    return []

# Reactive effect to check for file changes
@reactive.Effect
def check_file_updates():
    file_reader()
    time.sleep(1)
    reactive.invalidate_later(1)

# Reactive calculation for filtered history
@reactive.calc
def filtered_history():
    history = list(weather_history.get())
    hours = input.history_hours()
    return history[-hours:] if hours <= len(history) else history

# Reactive effect for fetching and saving data
@reactive.Effect
@reactive.event(input.update_btn)
def update_weather():
    city = input.city_input()
    if city:
        new_data = fetch_weather(city)
        if new_data:
            current_history = weather_history.get()
            current_history.append(new_data)
            
            with open(HISTORY_FILE, "w") as f:
                json.dump(list(current_history), f)
            
            weather_history.set(current_history)

# Reactive calculations for DataFrames
@reactive.calc
def current_weather_df():
    history = weather_history.get()
    return pd.DataFrame([history[-1]]) if history else pd.DataFrame()

@reactive.calc
def history_df():
    return pd.DataFrame(filtered_history())

# Loading spinner
@render.ui
def loading_spinner():
    if not weather_history.get():
        return ui.tags.div(
            ui.tags.span(class_="spinner-border spinner-border-sm"),
            "Loading data...",
            class_="text-center my-5"
        )

# Main layout
with ui.layout_columns():
    with ui.card(full_screen=True):
        ui.h2("Current Weather")
        @render.data_frame
        def current_weather():
            return render.DataTable(current_weather_df())

    with ui.card(full_screen=True):
        ui.h2("Weather History")
        @render.data_frame
        def weather_history_table():
            return render.DataGrid(history_df())

# Visualization cards with full reactivity
with ui.layout_columns():
    @render_plotly
    def weather_trend():
        df = history_df()
        selected_metric = input.selected_metric()
        
        if df.empty:
            return px.scatter(title="No data available").update_layout(showlegend=False)
        
        return px.line(
            df,
            x="timestamp",
            y=selected_metric,
            color="city",
            title=f"{METRIC_LABELS[selected_metric]} Trend Over Time",
            labels={
                "timestamp": "Time",
                selected_metric: METRIC_LABELS[selected_metric]
            }
        ).update_traces(mode="lines+markers")

    @render_plotly
    def weather_conditions():
        df = history_df()
        selected_metric = input.selected_metric()
        
        if df.empty:
            return px.scatter(title="No data available").update_layout(showlegend=False)
        
        return px.pie(
            df,
            names="weather_condition",
            values=selected_metric,
            title=f"{METRIC_LABELS[selected_metric]} Distribution by Weather Condition",
            hole=0.4
        )

with ui.card(full_screen=True):
    ui.card_header("Detailed Weather Metrics")
    @render_plotly
    def weather_correlation():
        df = history_df()
        selected_metric = input.selected_metric()
        
        if df.empty:
            return px.scatter(title="No data available").update_layout(showlegend=False)
        
        return px.scatter_matrix(
            df,
            dimensions=list(METRIC_LABELS.keys()),
            color=selected_metric,
            title=f"Metrics Correlation (Colored by {METRIC_LABELS[selected_metric]})",
            labels=METRIC_LABELS
        )

# Update available metrics based on data
@reactive.Effect
def update_metric_filter():
    df = history_df()
    if not df.empty:
        available_metrics = [col for col in METRIC_LABELS.keys() if col in df.columns]
        ui.update_selectize("selected_metric", choices=available_metrics)