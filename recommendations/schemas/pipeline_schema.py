from pydantic import BaseModel


class TrendingWeightsModel(BaseModel):
    
    internal_sales_24h: float = 40.0
    internal_sales_3d:  float = 30.0
    internal_sales_7d:  float = 30.0

    internal_views_24h: float = 40.0
    internal_views_3d:  float = 40.0
    internal_views_7d:  float = 20.0

    internal_cart_24h:  float = 40.0
    internal_cart_3d:   float = 30.0
    internal_cart_7d:   float = 30.0

    internal_wish_24h:  float = 40.0
    internal_wish_3d:   float = 30.0
    internal_wish_7d:   float = 30.0

    
    business_sales_weight: float = 0.5
    business_views_weight: float = 0.1
    business_cart_weight:  float = 0.3
    business_wish_weight:  float = 0.1

    # Thresholds
    threshold_value:       float = 64.0
    min_threshold_relaxed: float = 30.0

    # Category caps
    max_per_leaf_category: int   = 10   # cap per deepest (leaf) level
    min_per_l2_category:   int   = 10   # minimum fill target for L2

