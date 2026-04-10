import os

from fastapi.testclient import TestClient


os.environ.setdefault("HOST_URL", "http://localhost:7700")
os.environ.setdefault("API_KEY", "dummy_key")
os.environ.setdefault("ES_HOST", "localhost")
os.environ.setdefault("ES_PORT", "9200")
os.environ.setdefault("ES_SCHEME", "http")
os.environ.setdefault("FETCH_RATE_LIMIT_PER_MINUTE", "500")

from recommendations.main import app
from recommendations.api import bestseller, trending, popular_category, dealofday, fbt, popular_brands


client = TestClient(app)


def setup_module(module):
    bestseller.bestSellerService.fetch_all = lambda client, size: [{"skuid": "sku_1", "score": 0.9}]
    bestseller.bestSellerService.fetch_by_l3 = lambda client, l3_list, size: {
        "hits": [{"skuid": "sku_1", "l3": l3_list[0]}]
    }
    bestseller.bestSellerService.fetch_by_skuid = lambda client, skuid_list: {
        "hits": [{"skuid": skuid_list[0]}]
    }

    trending.service.getTrendingProducts = lambda client, filters=None, limit=20: {
        "count": 1,
        "data": [{"skuid": "sku_t_1", "category_l1": "electronics"}],
    }

    popular_category.bestSellerService.fetch_all_categories = lambda client, limit: {
        "count": 1,
        "data": [{"category_l1": "electronics", "score": 0.8}],
    }
    popular_category.bestSellerService.fetch_categories_by_filters = lambda client, filters, limit: {
        "count": 1,
        "data": [{"category_l2": "mobiles", "score": 0.7}],
    }

    dealofday.dealOfDayService.dealoftheday_fetch_l1 = lambda index_name, l1list, size: [
        {"skuid": "dod_1", "l1": l1list[0]}
    ]
    dealofday.dealOfDayService.dealoftheday_fetch_l2 = lambda index_name, l2list, size: [
        {"skuid": "dod_2", "l2": l2list[0]}
    ]
    dealofday.dealOfDayService.dealoftheday_fetch_l3 = lambda index_name, l3list, size: [
        {"skuid": "dod_3", "l3": l3list[0]}
    ]
    dealofday.dealOfDayService.dealoftheday_fetch_all = lambda index_name, size: [
        {"skuid": "dod_4"}
    ]

    fbt.fbtService.fetch_fbt_products = lambda product_id, index_name, top_n: {
        "product_id": product_id,
        "fbt": [{"skuid_B": "sku_b_1"}],
    }

    popular_brands.pbService.fetch_popular_brands = lambda brand, index_name, top_n: {
        "brand": brand,
        "results": [{"brand": brand, "rank": 1}],
    }


def test_bestseller_all_happy_path():
    res = client.get("/recommendations/bestseller/all", params={"client": "tenant1", "size": 5})
    assert res.status_code == 200
    assert isinstance(res.json(), list)


def test_bestseller_l3_happy_path():
    res = client.get(
        "/recommendations/bestseller/label3",
        params=[("client", "tenant1"), ("l3", "phones"), ("size", 5)],
    )
    assert res.status_code == 200
    body = res.json()
    assert body["count"] == 1


def test_bestseller_skuid_happy_path():
    res = client.get(
        "/recommendations/bestseller/skuid",
        params=[("client", "tenant1"), ("skuid", "sku_1")],
    )
    assert res.status_code == 200
    assert res.json()["count"] == 1


def test_trending_fetch_happy_path():
    res = client.get(
        "/recommendations/trending/data-preview",
        params={"client": "tenant1", "category_l1": "electronics", "limit": 10},
    )
    assert res.status_code == 200
    assert res.json()["count"] == 1


def test_popular_category_fetch_happy_path():
    res = client.get(
        "/recommendations/popular_category/fetch",
        params={"client": "tenant1", "limit": 10},
    )
    assert res.status_code == 200
    assert res.json()["count"] == 1


def test_dealofday_fetch_happy_path():
    res = client.get(
        "/recommendations/dealofday/fetch/l1",
        params=[("l1", "electronics"), ("index_name", "tenant1_deal_of_day"), ("size", 5)],
    )
    assert res.status_code == 200
    assert isinstance(res.json(), list)


def test_fbt_fetch_happy_path():
    res = client.get(
        "/recommendations/fbt/fetch",
        params={"client": "tenant1", "product_id": "sku_1", "top_n": 5},
    )
    assert res.status_code == 200
    assert res.json()["product_id"] == "sku_1"


def test_popular_brands_fetch_happy_path():
    res = client.get(
        "/recommendations/popular_brands/popular_brands",
        params={"brand": "apple", "index_name": "popular_brands", "top_n": 5},
    )
    assert res.status_code == 200
    assert res.json()["brand"] == "apple"
