
import fnmatch
import io
import os
from pathlib import Path

import pandas as pd

def normalize(series):
    min_val = series.min()
    max_val = series.max()
    
    if max_val == min_val:
        return pd.Series([0.0] * len(series), index=series.index)
    
    return (series - min_val) / (max_val - min_val)


def load_csv(dataset: str, client: str) -> pd.DataFrame:
    """
    Load CSV from local processed folder first, fallback to S3.
    
    Args:
        dataset: Dataset name (e.g., "catalog", "orders", "analytics")
        client: Client identifier (e.g., "amazon", "flipkart")
    
    Returns:
        pd.DataFrame: The loaded CSV data
    
    Raises:
        FileNotFoundError: If CSV file cannot be found in either location
    """
    # Try local processed folder first
    base_processed_dir = Path(__file__).parent.parent / "pipelines" / "data" / "processed"
    local_csv_path = base_processed_dir / client / dataset / f"{dataset}.csv"
    
    if local_csv_path.exists():
        print(f"Loading {dataset} from local: {local_csv_path}")
        try:
            df = pd.read_csv(local_csv_path)
            if "timestamp" in df.columns:
                df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
            return df
        except Exception as exc:
            print(f"Warning: Failed to load from local {local_csv_path}: {exc}. Trying S3...")
    
    # Fall back to S3
    s3_path = os.getenv("S3_PATH", "s3://retail-search")
    return load_csv_from_s3(s3_path, client, dataset)


def load_csv_from_s3(s3_path: str, client: str, dataset: str) -> pd.DataFrame:
    """
    Load a CSV file directly from S3 based on client and dataset.
    
    Args:
        s3_path: Base S3 path (e.g., "s3://retail-search")
        client: Client identifier (e.g., "amazon", "flipkart")
        dataset: Dataset name (e.g., "catalog", "orders", "analytics")
    
    Returns:
        pd.DataFrame: The loaded CSV data
    
    Raises:
        ValueError: If s3_path is not set or parameters are invalid
        FileNotFoundError: If CSV file cannot be found in S3
    """
    if not s3_path:
        raise ValueError("s3_path is not set in environment variables")
    
    if not client or not dataset:
        raise ValueError("client and dataset parameters are required")
    
    return load_csv_from_s3_advanced(
        s3_path=s3_path,
        client=client,
        dataset=dataset,
        mode="latest",
    )


def load_csv_from_s3_advanced(
    s3_path: str,
    client: str,
    dataset: str,
    mode: str = "latest",
    filename: str | None = None,
    pattern: str | None = None,
    add_source_column: bool = False,
) -> pd.DataFrame:
    """
    Advanced S3 CSV loader for datasets that may contain multiple files.

    Modes:
    - latest: load a specific filename if provided, otherwise most recently modified file.
    - all: load all matching files and concatenate into one DataFrame.
    """
    if not s3_path:
        raise ValueError("s3_path is not set in environment variables")

    if not client or not dataset:
        raise ValueError("client and dataset parameters are required")

    mode_value = (mode or "latest").strip().lower()
    if mode_value not in {"latest", "all"}:
        raise ValueError("mode must be 'latest' or 'all'")

    try:
        from ..services.s3_service import S3Service

        print(f"Loading dataset '{dataset}' from S3 for client '{client}' (mode={mode_value})")
        s3_service = S3Service()

        if mode_value == "latest":
            payload = s3_service.fetch_file(
                client=client,
                dataset=dataset,
                filename=filename,
            )
            raw = payload["stream"].read()
            df = pd.read_csv(io.BytesIO(raw))
            if "timestamp" in df.columns:
                df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
            return df

        listing = s3_service.list_files(client=client, dataset=dataset, max_keys=1000)
        files = listing.get("files", [])
        if pattern:
            files = [f for f in files if fnmatch.fnmatch(f.get("filename", ""), pattern)]
        if filename:
            files = [f for f in files if f.get("filename") == filename]

        if not files:
            raise FileNotFoundError(
                f"No files found for client='{client}', dataset='{dataset}'"
                + (f", pattern='{pattern}'" if pattern else "")
            )

        files = sorted(files, key=lambda item: item.get("last_modified") or "")
        frames: list[pd.DataFrame] = []

        for item in files:
            file_payload = s3_service.fetch_file(
                client=client,
                dataset=dataset,
                filename=item.get("filename"),
            )
            raw = file_payload["stream"].read()
            part = pd.read_csv(io.BytesIO(raw))
            if "timestamp" in part.columns:
                part["timestamp"] = pd.to_datetime(part["timestamp"], errors="coerce")
            if add_source_column:
                part["source_file"] = item.get("filename")
            frames.append(part)

        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    except Exception as exc:
        raise FileNotFoundError(
            f"Could not load dataset '{dataset}' for client '{client}' from S3. "
            f"Expected under: s3://retail-search/{client}/{dataset}/"
        ) from exc
