import requests
import sqlite3
import datetime

# --- Configuration ---
# Your OpenWeatherMap API Key
WEATHER_API_KEY = '635de7bfe00eba979c1a5d58fbaf271f'

# Fourways Coordinates
LAT = -26.0270
LON = 28.0137

BASE_URL = "https://api.openweathermap.org/data/2.5/weather"
DB_NAME = 'vuka_data.db'
TARGET_AREA = 'Fourways'

def fetch_weather():
    """Pulls current weather for the target coordinates."""
    url = f"{BASE_URL}?lat={LAT}&lon={LON}&appid={WEATHER_API_KEY}&units=metric"
    print(f"Fetching weather for {TARGET_AREA}...")
    
    response = requests.get(url)
    
    if response.status_code == 200:
        return response.json()
    elif response.status_code == 401:
        print("Error 401: API Key is still inactive. Try again in 10-15 minutes.")
        return None
    else:
        print(f"Error fetching weather: {response.status_code} - {response.text}")
        return None

def save_to_db(weather_data):
    """Normalizes the weather data into the context_signals table."""
    if not weather_data:
        return

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Ensure the table exists
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS context_signals (
            area_cell TEXT,
            timestamp TEXT,
            signal_type TEXT,
            value TEXT
        )
    ''')
    
    current_time = datetime.datetime.now(datetime.timezone.utc).isoformat()
    
    # Extract core signals
    # e.g., 'Rain', 'Clear', 'Clouds'
    main_condition = weather_data.get('weather', [{}])[0].get('main', 'Unknown') 
    # e.g., 18.5 (Celsius)
    temperature = weather_data.get('main', {}).get('temp', 0)
    
    # Insert weather condition (Crucial for the audio Whisper model context)
    cursor.execute(
        "INSERT INTO context_signals (area_cell, timestamp, signal_type, value) VALUES (?, ?, ?, ?)",
        (TARGET_AREA, current_time, 'weather_condition', str(main_condition))
    )
    
    # Insert temperature
    cursor.execute(
        "INSERT INTO context_signals (area_cell, timestamp, signal_type, value) VALUES (?, ?, ?, ?)",
        (TARGET_AREA, current_time, 'weather_temp_celsius', str(temperature))
    )

    conn.commit()
    conn.close()
    
    print(f"✅ Successfully logged weather to database:")
    print(f"   - Condition: {main_condition}")
    print(f"   - Temperature: {temperature}°C")

def main():
    data = fetch_weather()
    save_to_db(data)

if __name__ == '__main__':
    main()