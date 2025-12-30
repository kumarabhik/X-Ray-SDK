import random
from xray_sdk import XRayClient

XRAY = XRayClient(base_url="http://localhost:8000", app="demo")

MOCK_PRODUCTS = [
    {"asin": "B0COMP01", "title": "HydroFlask 32oz Wide Mouth", "price": 44.99, "rating": 4.5, "reviews": 8932},
    {"asin": "B0COMP02", "title": "Yeti Rambler 26oz", "price": 34.99, "rating": 4.4, "reviews": 5621},
    {"asin": "B0COMP03", "title": "Generic Water Bottle", "price": 8.99, "rating": 3.2, "reviews": 45},
    {"asin": "B0COMP04", "title": "Bottle Cleaning Brush Set", "price": 12.99, "rating": 4.6, "reviews": 3421},
    {"asin": "B0COMP05", "title": "Replacement Lid for HydroFlask", "price": 9.99, "rating": 4.7, "reviews": 2100},
    {"asin": "B0COMP07", "title": "Stanley Adventure Quencher", "price": 35.00, "rating": 4.3, "reviews": 4102},
]

def simulate_llm_keywords(title: str, category: str):
    variants = [
        ["stainless steel bottle insulated", "vacuum insulated bottle 32oz"],
        ["32oz insulated water bottle", "double wall steel bottle"],
        ["sports water bottle insulated", "steel thermos bottle"],
    ]
    kw = random.choice(variants)
    why = f"Extracted attributes (material=steel, capacity=32oz, feature=insulated). Picked keyword variant #{variants.index(kw)} for broader recall."
    return kw, why

def mock_search(keywords):
    items = MOCK_PRODUCTS[:]
    random.shuffle(items)
    total_results = random.randint(500, 5000)
    why = f"Mock API: returning 6 candidates (shuffled) for keywords={keywords}. Total matches simulated={total_results}."
    return total_results, items[:6], why

def apply_filters(reference, candidates):
    ref_price = reference["price"]
    min_p, max_p = 0.5 * ref_price, 2.0 * ref_price
    min_rating, min_reviews = 3.8, 100

    filters = {
        "price_range": {"min": round(min_p, 2), "max": round(max_p, 2), "rule": "0.5x - 2x of reference price"},
        "min_rating": {"value": min_rating, "rule": ">= 3.8 stars"},
        "min_reviews": {"value": min_reviews, "rule": ">= 100 reviews"},
        "remove_accessories": {"rule": "Reject obvious accessories (title contains lid/brush/bag)"},
    }

    evals = []
    qualified = []

    for c in candidates:
        title = c["title"].lower()
        is_accessory = any(w in title for w in ["lid", "brush", "bag", "carrier"])

        price_ok = (c["price"] >= min_p) and (c["price"] <= max_p)
        rating_ok = c["rating"] >= min_rating
        reviews_ok = c["reviews"] >= min_reviews
        accessory_ok = not is_accessory

        fr = {
            "price_range": {"passed": price_ok, "detail": f"${c['price']} in ${min_p:.2f}-${max_p:.2f}" if price_ok else f"${c['price']} outside ${min_p:.2f}-${max_p:.2f}"},
            "min_rating": {"passed": rating_ok, "detail": f"{c['rating']} >= {min_rating}" if rating_ok else f"{c['rating']} < {min_rating}"},
            "min_reviews": {"passed": reviews_ok, "detail": f"{c['reviews']} >= {min_reviews}" if reviews_ok else f"{c['reviews']} < {min_reviews}"},
            "remove_accessories": {"passed": accessory_ok, "detail": "Not an accessory" if accessory_ok else "Title indicates accessory"},
        }

        q = price_ok and rating_ok and reviews_ok and accessory_ok
        evals.append({
            "asin": c["asin"],
            "title": c["title"],
            "metrics": {"price": c["price"], "rating": c["rating"], "reviews": c["reviews"]},
            "filter_results": fr,
            "qualified": q
        })
        if q:
            qualified.append(c)

    selected = max(qualified, key=lambda x: x["reviews"]) if qualified else None
    return filters, evals, qualified, selected

def main():
    reference = {
        "asin": "B0XYZ123",
        "title": "ProBrand Steel Bottle 32oz Insulated",
        "price": 29.99,
        "rating": 4.2,
        "reviews": 1247,
        "category": "Sports & Outdoors > Water Bottles"
    }

    execution_id = XRAY.start_execution("competitor_selection", metadata={"reference_asin": reference["asin"]})

    with XRAY.step(execution_id, "keyword_generation", input={"product_title": reference["title"], "category": reference["category"]}) as s:
        keywords, why = simulate_llm_keywords(reference["title"], reference["category"])
        s.output({"keywords": keywords, "model": "mock-gpt"})
        s.reason(why)

    with XRAY.step(execution_id, "candidate_search", input={"keywords": keywords, "limit": 50}) as s:
        total, cands, why = mock_search(keywords)
        s.output({"total_results": total, "candidates_fetched": len(cands)})
        s.artifact("candidates", cands)
        s.reason(why)

    with XRAY.step(execution_id, "apply_filters_and_select", input={"reference_product": reference, "candidates_count": len(cands)}) as s:
        filters, evals, qualified, selected = apply_filters(reference, cands)
        s.artifact("filters_applied", filters)
        s.artifact("evaluations", evals)
        s.output({"passed": len(qualified), "failed": len(cands) - len(qualified), "selected": selected})
        s.reason("Applied deterministic business filters + accessory elimination; selected highest review-count among qualified.")

    print("✅ Execution recorded:", execution_id)

if __name__ == "__main__":
    main()
