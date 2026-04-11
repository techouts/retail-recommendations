import logging
import pandas as pd
import numpy as np
import os
from pathlib import Path
import io


logger = logging.getLogger(__name__)


def load_csv_from_s3(s3_path: str, client: str, dataset: str) -> pd.DataFrame:
    """
    Load a CSV file from S3 or local processed folder based on client and dataset.
    
    This function first checks if the file exists in the local processed folder 
    (which should be synced from S3 via /recommendations/s3/sync endpoint).
    If not found locally, it attempts to load directly from S3.
    
    Args:
        s3_path: Base S3 path or "s3://" URI. Can also be a local base path.
        client: Client identifier (e.g., "amazon", "flipkart", "ss3")
        dataset: Dataset name (e.g., "catalog", "orders", "analytics", "cancellations", "ratings", "reviews")
    
    Returns:
        pd.DataFrame: The loaded CSV data
    
    Raises:
        ValueError: If s3_path is not set or file not found in either location
        FileNotFoundError: If CSV file cannot be found
    
    Example:
        catalog_df = load_csv_from_s3(s3_path, "amazon", "catalog")
        orders_df = load_csv_from_s3(s3_path, "flipkart", "orders")
    """
    if not s3_path:
        raise ValueError("s3_path is not set in environment variables")
    
    if not client or not dataset:
        raise ValueError("client and dataset parameters are required")
    
    # Try local processed folder first (after sync)
    base_processed_dir = Path(__file__).parent / "data" / "processed"
    local_csv_path = base_processed_dir / client / dataset / f"{dataset}.csv"
    
    if local_csv_path.exists():
        logger.info(f"Loading {dataset} from local processed folder: {local_csv_path}")
        try:
            return pd.read_csv(local_csv_path)
        except Exception as exc:
            logger.warning(f"Failed to load from local path {local_csv_path}: {exc}. Trying S3...")
    
    # Fall back to S3 using S3Service
    try:
        from ..services.s3_service import S3Service
        from ..adapters.s3.client import get_s3_client
        from ..core.config import settings
        
        logger.info(f"Loading {dataset} from S3 for client {client}")
        
        s3_service = S3Service(get_s3_client(), settings)
        
        # Fetch the file from S3
        file_content = s3_service.fetch_file(
            client=client,
            dataset=dataset,
            filename=f"{dataset}.csv",
            latest=True
        )
        
        # Convert bytes to DataFrame
        df = pd.read_csv(io.BytesIO(file_content))
        logger.info(f"Successfully loaded {dataset} from S3 for client {client}")
        return df
    
    except Exception as exc:
        logger.error(f"Failed to load {dataset} from S3: {exc}")
        raise FileNotFoundError(
            f"Could not load {dataset}.csv for client '{client}'. "
            f"Make sure the file exists in S3 (s3://retail-search/{client}/{dataset}/{dataset}.csv) "
            f"or in local processed folder ({local_csv_path})"
        ) from exc


def load_multiple_csvs_from_s3(s3_path: str, client: str, datasets: list[str]) -> dict[str, pd.DataFrame]:
    """
    Load multiple CSV files from S3 for a specific client in bulk.
    
    Args:
        s3_path: Base S3 path or "s3://" URI
        client: Client identifier
        datasets: List of dataset names to load
    
    Returns:
        dict: Dictionary mapping dataset names to DataFrames
    
    Example:
        dfs = load_multiple_csvs_from_s3(s3_path, "amazon", ["catalog", "orders", "analytics"])
        catalog_df = dfs["catalog"]
        orders_df = dfs["orders"]
    """
    result = {}
    for dataset in datasets:
        try:
            result[dataset] = load_csv_from_s3(s3_path, client, dataset)
        except Exception as exc:
            logger.error(f"Failed to load {dataset} for client {client}: {exc}")
            result[dataset] = None
    
    return result


def df_to_es_docs(df: pd.DataFrame) -> list[dict]:
    df = df.replace([np.nan, np.inf, -np.inf], None)
    return df.to_dict(orient="records")


def get_eligible_skus(df: pd.DataFrame, min_stock:int=2):
    stock_totals=df.groupby("skuid",as_index=False)["stock_quantity"].sum()
    eligible_products=stock_totals.loc[stock_totals["stock_quantity"]>min_stock,"skuid"]
    logger.info("Eligible skuids (stock > %d): %d", min_stock, len(eligible_products))
    return eligible_products