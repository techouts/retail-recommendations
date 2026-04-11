

import pandas as pd
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_DIR = os.path.join(BASE_DIR, "pipelines", "data", "processed")

def normalize(series):
    min_val = series.min()
    max_val = series.max()
    
    if max_val == min_val:
        return pd.Series([0.0] * len(series), index=series.index)
    
    return (series - min_val) / (max_val - min_val)

def load_csv(name: str) -> pd.DataFrame:
    """Load CSV and convert timestamp column."""
    path = os.path.join(CSV_DIR, name)
    df = pd.read_csv(path)
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    return df