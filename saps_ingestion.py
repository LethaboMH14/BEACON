import pandas as pd
import sqlite3
import datetime
import warnings

# Suppress the openpyxl validation warnings for a cleaner terminal
warnings.filterwarnings('ignore', category=UserWarning, module='openpyxl')

DB_NAME = 'vuka_data.db'
FILE_NAME = '2025-2026_-_4th_Quarter_WEB.xlsx'
TARGET_PRECINCT = 'Douglasdale'

def load_saps_data():
    """Reads the SAPS Excel file and filters for the target precinct."""
    print(f"Loading SAPS Excel file (Target: {TARGET_PRECINCT})...")
    
    # Read the RAW Data sheet without headers, since the headers are messy
    df = pd.read_excel(FILE_NAME, sheet_name='RAW Data', header=None)
    
    # Column 4 contains the precinct names
    precinct_data = df[df[4] == TARGET_PRECINCT]
    
    if precinct_data.empty:
        print(f"Warning: Precinct '{TARGET_PRECINCT}' not found.")
        return None
        
    return precinct_data

def save_to_db(precinct_data):
    """Normalizes the crime counts into the context_signals table."""
    if precinct_data is None:
        return
        
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Ensure the table exists (in case this script runs before the ESP one)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS context_signals (
            area_cell TEXT,
            timestamp TEXT,
            signal_type TEXT,
            value TEXT
        )
    ''')
    
    # Using the first day of the quarter as the timestamp baseline
    quarter_timestamp = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc).isoformat()
    
    # Variables to hold our target crime totals
    total_carjackings = 0
    total_agg_robbery = 0
    
    # Iterate through the rows for Douglasdale
    for index, row in precinct_data.iterrows():
        crime_category = str(row[7]).strip()
        
        # Column 12 is the Q4 Total (Jan+Feb+Mar). 
        # (Cols 9, 10, 11 are Jan, Feb, Mar individually)
        quarterly_total = row[12] 
        
        if crime_category == 'Carjacking':
            total_carjackings = quarterly_total
            
        elif crime_category == 'Robbery with aggravating circumstances':
            total_agg_robbery = quarterly_total

    # Insert Carjacking baseline
    cursor.execute(
        "INSERT INTO context_signals (area_cell, timestamp, signal_type, value) VALUES (?, ?, ?, ?)",
        (TARGET_PRECINCT, quarter_timestamp, 'baseline_carjacking', str(total_carjackings))
    )
    
    # Insert Aggravated Robbery baseline
    cursor.execute(
        "INSERT INTO context_signals (area_cell, timestamp, signal_type, value) VALUES (?, ?, ?, ?)",
        (TARGET_PRECINCT, quarter_timestamp, 'baseline_agg_robbery', str(total_agg_robbery))
    )

    conn.commit()
    conn.close()
    
    print(f"✅ Successfully logged Q4 baseline for {TARGET_PRECINCT} to database:")
    print(f"   - Carjackings: {total_carjackings}")
    print(f"   - Aggravated Robberies: {total_agg_robbery}")

def main():
    data = load_saps_data()
    save_to_db(data)

if __name__ == '__main__':
    main()