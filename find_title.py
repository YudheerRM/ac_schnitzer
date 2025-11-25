import json
from pathlib import Path

def main():
    path = Path("data/product_details.json")
    target_url_part = "ac-schnitzer-light-soft-shell-jacket"
    
    print(f"Searching in {path}...")
    with path.open("r", encoding="utf-8") as fp:
        data = json.load(fp)
        
    products = data.get("products", {})
    
    for brand, items in products.items():
        for url, product in items.items():
            if target_url_part in url:
                print(f"Found URL: {url}")
                print(f"Title: {product.get('title')}")
                return

if __name__ == "__main__":
    main()
