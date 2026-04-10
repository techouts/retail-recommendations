import logging
import pandas as pd
import numpy as np


logger = logging.getLogger(__name__)

def df_to_es_docs(df: pd.DataFrame) -> list[dict]:
    df = df.replace([np.nan, np.inf, -np.inf], None)
    return df.to_dict(orient="records")


def get_eligible_skus(df: pd.DataFrame, min_stock:int=2):
    stock_totals=df.groupby("skuid",as_index=False)["stock_quantity"].sum()
    eligible_products=stock_totals.loc[stock_totals["stock_quantity"]>min_stock,"skuid"]
    logger.info("Eligible skuids (stock > %d): %d", min_stock, len(eligible_products))
    return eligible_products