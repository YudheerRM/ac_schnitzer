import json
from pathlib import Path

def main():
    path = Path("data/product_details.json")
    if not path.exists():
        path = Path("product_details.json")
        
    print(f"Loading {path}...")
    with path.open("r", encoding="utf-8") as fp:
        data = json.load(fp)
        
    products = data.get("products", {})
    
    count = 0
    for brand, items in products.items():
        for url, product in items.items():
            info = product.get("product_information", [])
            
            overview = next((item for item in info if item.get("title", "").strip().lower() == "overview"), None)
            description = next((item for item in info if item.get("title", "").strip().lower() == "description"), None)
            
            has_overview = overview and overview.get("text", "").strip()
            has_description = description and description.get("text", "").strip()
            
            if has_overview and has_description:
                print(f"\n--- Product with BOTH Overview and Description ---")
                print(f"URL: {url}")
                print("Overview HTML snippet:")
                print(overview.get("html", "")[:200])
                print("Description HTML snippet:")
                print(description.get("html", "")[:200])
                print("-" * 40)
                count += 1
                if count >= 3:
                    return

    if count == 0:
        print("No products found with both Overview and Description populated.")

if __name__ == "__main__":
    main()
