

import pandas as pd
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_DIR = os.path.join(BASE_DIR, "pipelines", "data", "processed")

def normalize(series: pd.Series) -> pd.Series:
    if series.max() == series.min():
        return series * 0.0
    return (series - series.min()) / (series.max() - series.min())


def load_csv(name: str) -> pd.DataFrame:
    """Load CSV and convert timestamp column."""
    path = os.path.join(CSV_DIR, name)
    df = pd.read_csv(path)
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    return df