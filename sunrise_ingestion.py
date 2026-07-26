import requests
import sqlite3
import datetime

# --- Configuration ---
# Fourways Coordinates
LAT = -26.0270
LON = 28.0137

BASE_URL = "https://api.sunrise-sunset.org/v2"
DB_NAME = 'vuka_data.db'
TARGET_AREA = 'Fourways'

def fetch_sun_times():
    """Pulls precise sunrise and sunset times for today."""
    print(f"Fetching sunrise/sunset times for {TARGET_AREA}...")
    
    # We use formatted=0 to get clean ISO 8601 timestamps in UTC
    params = {
        'lat': LAT,
        'lng': LON,
        'formatted': 0
    }
    
    response = requests.get(BASE_URL, params=params)
    
    if response.status_code == 200:
        return response.json().get('results', {})
    else:
        print(f"Error fetching sun times: {response.status_code} - {response.text}")
        return None

def save_to_db(sun_data):
    """Normalizes the times into the context_signals table."""
    if not sun_data:
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
    
    # Extract the precise times (returned in UTC)
    sunrise = sun_data.get('sunrise', 'Unknown')
    sunset = sun_data.get('sunset', 'Unknown')
    golden_hour = sun_data.get('golden_hour', 'Unknown')
    
    # Insert Sunrise
    cursor.execute(
        "INSERT INTO context_signals (area_cell, timestamp, signal_type, value) VALUES (?, ?, ?, ?)",
        (TARGET_AREA, current_time, 'time_sunrise', sunrise)
    )
    
    # Insert Sunset
    cursor.execute(
        "INSERT INTO context_signals (area_cell, timestamp, signal_type, value) VALUES (?, ?, ?, ?)",
        (TARGET_AREA, current_time, 'time_sunset', sunset)
    )

    # Insert Golden Hour (Dusk/Approaching darkness)
    cursor.execute(
        "INSERT INTO context_signals (area_cell, timestamp, signal_type, value) VALUES (?, ?, ?, ?)",
        (TARGET_AREA, current_time, 'time_golden_hour_dusk', golden_hour)
    )

    conn.commit()
    conn.close()
    
    print(f"✅ Successfully logged sun times to database:")
    print(f"   - Sunrise: {sunrise}")
    print(f"   - Sunset:  {sunset}")

def main():
    data = fetch_sun_times()
    save_to_db(data)

if __name__ == '__main__':
    main()