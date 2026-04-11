# Pipeline CSV Loading from S3

## Overview
The new `load_csv_from_s3()` utility function enables your pipelines to load CSV data directly from S3 based on client (db_name) and dataset names.

## Key Features
- **Automatic Fallback**: First tries loading from local processed folder (synced via `/sync` endpoint), then falls back to S3
- **Client Scoping**: Each client has isolated data in S3: `s3://retail-search/{client}/{dataset}/{dataset}.csv`
- **Bulk Loading**: Use `load_multiple_csvs_from_s3()` to load multiple datasets at once
- **Error Handling**: Clear logging and error messages for debugging

## Setup

### 1. Environment Variables
Ensure these are set in `.env`:
```env
S3_PATH=s3://retail-search
AWS_ACCESS_KEY_ID=your_key
AWS_SECRET_ACCESS_KEY=your_secret
AWS_STORAGE_BUCKET_NAME=retail-search
AWS_S3_REGION_NAME=us-east-1
```

### 2. Data Sync
Before running pipelines, sync the latest data from S3:
```bash
curl -X POST http://localhost:8000/recommendations/s3/sync?client=amazon
```

Or call it programmatically:
```python
import requests
response = requests.post("http://localhost:8000/recommendations/s3/sync?client=amazon")
```

## Usage Patterns

### Single CSV Loading
```python
import os
from .utils import load_csv_from_s3

def run_bestseller_pipeline(client: str, weights: dict, time_window: dict):
    s3_path = os.getenv("s3_path")
    
    if not s3_path:
        raise ValueError("s3_path is not set in environment variables")
    
    # Load individual CSVs by client and dataset
    catalog = load_csv_from_s3(s3_path, client, "catalog")
    fulfillment = load_csv_from_s3(s3_path, client, "fulfillment")
    orders = load_csv_from_s3(s3_path, client, "orders")
    analytics = load_csv_from_s3(s3_path, client, "analytics")
    inventory = load_csv_from_s3(s3_path, client, "inventory")
    returns = load_csv_from_s3(s3_path, client, "returns")
    
    # Continue with your pipeline logic
    # ...
```

### Bulk CSV Loading
```python
import os
from .utils import load_multiple_csvs_from_s3

def run_bestseller_pipeline(client: str, weights: dict, time_window: dict):
    s3_path = os.getenv("s3_path")
    
    # Load multiple CSVs at once
    datasets = ["catalog", "fulfillment", "orders", "analytics", "inventory", "returns"]
    dfs = load_multiple_csvs_from_s3(s3_path, client, datasets)
    
    catalog = dfs["catalog"]
    fulfillment = dfs["fulfillment"]
    orders = dfs["orders"]
    analytics = dfs["analytics"]
    inventory = dfs["inventory"]
    returns = dfs["returns"]
    
    # Continue with your pipeline logic
    # ...
```

### Popular Calculation Example (Your Use Case)
```python
import os
from .utils import load_csv_from_s3

s3_path = os.getenv("s3_path")

def popularity_base_calculation(popularity_df, start_date, end_date, client):
    """Calculate popularity metrics using S3 data for a specific client."""
    if not s3_path:
        raise ValueError("s3_path is not set in environment variables")
    
    # Load required datasets from S3
    cancellations_df = load_csv_from_s3(s3_path, client, "cancellations")
    ratings_df = load_csv_from_s3(s3_path, client, "ratings")
    reviews_df = load_csv_from_s3(s3_path, client, "reviews")
    
    # Your calculation logic here
    # ...
    
    return result
```

## Data Organization in S3

Your data should be organized like this:
```
s3://retail-search/
├── amazon/
│   ├── catalog/
│   │   └── catalog.csv
│   ├── orders/
│   │   └── orders.csv
│   ├── analytics/
│   │   └── analytics.csv
│   ├── cancellations/
│   │   └── cancellations.csv
│   ├── ratings/
│   │   └── ratings.csv
│   └── reviews/
│       └── reviews.csv
├── flipkart/
│   ├── catalog/
│   │   └── catalog.csv
│   ├── orders/
│   │   └── orders.csv
│   ... (same structure)
└── ss3/
    ... (same structure)
```

## Data Organization Locally

After syncing, files are cached locally at:
```
recommendations/pipelines/data/processed/
├── amazon/
│   ├── catalog/
│   │   └── catalog.csv
│   ├── orders/
│   │   └── orders.csv
│   ... (same structure)
├── flipkart/
│   ... (same structure)
```

## Integration with Services

In your service files, pass the client to the pipeline functions:

```python
# recommendations/services/bestseller_service.py
import os
from ..pipelines import run_bestseller_pipeline

def generate_bestseller_insights(client: str, weights: dict = None):
    """Generate bestseller insights for a specific client from S3 data."""
    s3_path = os.getenv("s3_path")
    
    # Call pipeline with client parameter
    result = run_bestseller_pipeline(
        client=client,
        weights=weights or DEFAULT_WEIGHTS,
        time_window=DEFAULT_WINDOW
    )
    
    return result
```

## API Integration

Call your pipeline via the recommendation APIs, passing the client:

```bash
# Start by syncing data from S3
curl -X POST http://localhost:8000/recommendations/s3/sync?client=amazon

# Then run your bestseller pipeline
curl http://localhost:8000/recommendations/bestseller?client=amazon
```

## Error Handling

The function provides clear error messages:

```python
try:
    catalog = load_csv_from_s3(s3_path, "amazon", "catalog")
except FileNotFoundError as e:
    print(f"Error: {e}")
    # Output: Could not load catalog.csv for client 'amazon'. 
    #         Make sure the file exists in S3 or in local processed folder
except ValueError as e:
    print(f"Configuration error: {e}")
    # Output: s3_path is not set in environment variables
```

## Debugging

Enable debug logging to see which files are being loaded:

```python
import logging
logging.basicConfig(level=logging.DEBUG)

# Now when you load CSVs, you'll see debug messages:
# INFO: Loading catalog from local processed folder: .../processed/amazon/catalog/catalog.csv
# or
# INFO: Loading catalog from S3 for client amazon
# INFO: Successfully loaded catalog from S3 for client amazon
```

## Best Practices

1. **Always sync first**: Call `/s3/sync` endpoint before running pipelines for fresh data
2. **Client parameter is required**: Every pipeline function should accept a `client` parameter
3. **Use bulk loading**: For multiple CSVs, prefer `load_multiple_csvs_from_s3()` for better performance
4. **Check logs**: The utility logs all operations, so check logs if data loading fails
5. **Handle None values**: `load_multiple_csvs_from_s3()` returns None for failed loads, check for them

## Migration Checklist

- [ ] Update all pipeline functions to accept `client` parameter
- [ ] Replace hardcoded CSV paths with `load_csv_from_s3()` calls
- [ ] Add `s3_path = os.getenv("s3_path")` at the top of pipeline functions
- [ ] Test with a single client first (e.g., "amazon")
- [ ] Verify S3 bucket has data organized by client/dataset structure
- [ ] Call `/s3/sync` endpoint before running pipelines
- [ ] Check logs for any "Failed to load" messages
- [ ] Update service functions to pass client parameter to pipelines
- [ ] Update API routes to accept and pass client parameter
