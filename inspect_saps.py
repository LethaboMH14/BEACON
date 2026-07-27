import pandas as pd

FILE_NAME = "2025-2026_-_4th_Quarter_WEB.xlsx"
print("Loading SAPS workbook (ignoring the openpyxl warnings)...")
import warnings
warnings.filterwarnings('ignore', category=UserWarning, module='openpyxl')

xls = pd.ExcelFile(FILE_NAME)

print("\nHunting for 'Douglasdale' across all sheets...")
for sheet in xls.sheet_names:
    df = pd.read_excel(xls, sheet_name=sheet, header=None)
    
    # Search for douglasdale
    mask = df.astype(str).apply(lambda col: col.str.contains('douglasdale', case=False, na=False))
    
    if mask.any().any():
        print(f"\n✅ FOUND in sheet: '{sheet}'")
        
        matching_rows = df[mask.any(axis=1)]
        
        for idx, row in matching_rows.iterrows():
            print(f"--- Row {idx} ---")
            print(row.values[:15])