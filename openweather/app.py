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
API_KEY = "d7ba80b2c6ccc315ff2d4e3948a80b2b"
DEFAULT_CITY = "Dallas"
MAX_HISTORY = 168
HISTORY_FILE = "weather_history.json"

# Unit systems
UNITS = {
    "metric": {
        "temperature": "°C",
        "speed": "m/s",
        "pressure": "hPa",
        "label": "Celsius"
    },
    "imperial": {
        "temperature": "°F",
        "speed": "mph",
        "pressure": "inHg",
        "label": "Fahrenheit"
    }
}

# Function to fetch weather data
def fetch_weather(city, unit_system="metric"):
    url = f"https://api.openweathermap.org/data/2.5/weather?q={city}&appid={API_KEY}&units={unit_system}"
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
            "unit_system": unit_system,  # Store the unit system used
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
    except (requests.RequestException, KeyError) as e:
        print(f"Error fetching weather: {e}")
        return None

# Conversion functions with default unit handling
def convert_temperature(temp, from_unit="metric", to_unit="metric"):
    if from_unit == to_unit:
        return temp
    if from_unit == "metric" and to_unit == "imperial":
        return (temp * 9/5) + 32
    else:
        return (temp - 32) * 5/9

def convert_speed(speed, from_unit="metric", to_unit="metric"):
    if from_unit == to_unit:
        return speed
    if from_unit == "metric" and to_unit == "imperial":
        return speed * 2.237
    else:
        return speed / 2.237

def convert_pressure(pressure, from_unit="metric", to_unit="metric"):
    if from_unit == to_unit:
        return pressure
    if from_unit == "metric" and to_unit == "imperial":
        return pressure * 0.02953
    else:
        return pressure / 0.02953

# UI Setup
ui.page_opts(title="Live Weather Dashboard", fillable=True)

# Sidebar with unit toggle
with ui.sidebar(open="open"):
    ui.h2("Weather Controls")
    ui.input_text("city_input", "Enter City", DEFAULT_CITY)
    ui.input_action_button("update_btn", "Get Weather", class_="btn-primary")
    
    ui.hr()
    ui.input_switch("unit_toggle", "Use Fahrenheit", False)
    
    ui.input_selectize(
        "selected_metric",
        "Select Metric to Visualize",
        ["temperature", "humidity", "pressure", "wind_speed"],
        selected="temperature"
    )
    ui.input_numeric("history_hours", "History Hours", 24, min=1, max=MAX_HISTORY)
    ui.a("OpenWeatherMap API", href="https://openweathermap.org/api", target="_blank")

# Reactive data storage
weather_history = reactive.Value(deque(maxlen=MAX_HISTORY))

# Get current unit system
@reactive.calc
def current_unit_system():
    return "imperial" if input.unit_toggle() else "metric"

# Load initial history with error handling
@reactive.Effect
def load_initial_history():
    try:
        if Path(HISTORY_FILE).exists():
            with open(HISTORY_FILE, "r") as f:
                history = json.load(f)
                # Ensure all entries have unit_system
                for entry in history:
                    if "unit_system" not in entry:
                        entry["unit_system"] = "metric"  # Default to metric for old entries
                weather_history.set(deque(history, maxlen=MAX_HISTORY))
    except Exception as e:
        print(f"Error loading history: {e}")

# Convert historical data to current units with error handling
@reactive.calc
def converted_history():
    history = list(weather_history.get())
    current_units = current_unit_system()
    
    converted = []
    for entry in history:
        try:
            # Ensure entry has unit_system, default to metric if missing
            entry_units = entry.get("unit_system", "metric")
            
            if entry_units == current_units:
                converted.append(entry)
            else:
                converted.append({
                    "city": entry["city"],
                    "temperature": convert_temperature(
                        entry["temperature"],
                        entry_units,
                        current_units
                    ),
                    "humidity": entry["humidity"],
                    "pressure": convert_pressure(
                        entry["pressure"],
                        entry_units,
                        current_units
                    ),
                    "wind_speed": convert_speed(
                        entry["wind_speed"],
                        entry_units,
                        current_units
                    ),
                    "weather_condition": entry["weather_condition"],
                    "unit_system": current_units,
                    "timestamp": entry["timestamp"]
                })
        except KeyError as e:
            print(f"Skipping invalid entry: {e}")
            continue
            
    return converted

# Get current weather DataFrame
@reactive.calc
def current_weather_df():
    history = converted_history()
    if history:
        df = pd.DataFrame([history[-1]])
        df["Units"] = UNITS[current_unit_system()]["label"]
        return df
    return pd.DataFrame()

# Get history DataFrame
@reactive.calc
def history_df():
    history = converted_history()
    hours = input.history_hours()
    filtered = history[-hours:] if hours <= len(history) else history
    return pd.DataFrame(filtered)

# Get unit labels
@reactive.calc
def current_units():
    return UNITS[current_unit_system()]

# Reactive effect for fetching data
@reactive.Effect
@reactive.event(input.update_btn)
def update_weather():
    city = input.city_input()
    if city:
        unit_system = current_unit_system()
        new_data = fetch_weather(city, unit_system)
        if new_data:
            current_history = weather_history.get()
            current_history.append(new_data)
            
            try:
                with open(HISTORY_FILE, "w") as f:
                    json.dump(list(current_history), f)
            except Exception as e:
                print(f"Error saving history: {e}")
            
            weather_history.set(current_history)

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

# Visualization cards
with ui.layout_columns():
    @render_plotly
    def weather_trend():
        df = history_df()
        selected_metric = input.selected_metric()
        
        if df.empty:
            return px.scatter(title="No data available").update_layout(showlegend=False)
        
        y_label = f"{selected_metric.title()} ({current_units()[selected_metric]})"
        
        return px.line(
            df,
            x="timestamp",
            y=selected_metric,
            color="city",
            title=f"{selected_metric.title()} Trend Over Time",
            labels={
                "timestamp": "Time",
                selected_metric: y_label
            }
        ).update_traces(mode="lines+markers")

    @render_plotly
    def weather_conditions():
        df = history_df()
        if df.empty:
            return px.scatter(title="No data available").update_layout(showlegend=False)
        
        return px.pie(
            df,
            names="weather_condition",
            title="Weather Condition Distribution",
            hole=0.4
        )

with ui.card(full_screen=True):
    ui.card_header("Detailed Weather Metrics")
    @render_plotly
    def weather_correlation():
        df = history_df()
        if df.empty:
            return px.scatter(title="No data available").update_layout(showlegend=False)
        
        dimensions = ["temperature", "humidity", "pressure", "wind_speed"]
        labels = {
            "temperature": f"Temperature ({current_units()['temperature']})",
            "humidity": "Humidity (%)",
            "pressure": f"Pressure ({current_units()['pressure']})",
            "wind_speed": f"Wind Speed ({current_units()['speed']})"
        }
        
        return px.scatter_matrix(
            df,
            dimensions=dimensions,
            color="city",
            title="Weather Metrics Correlation",
            labels=labels
        )