import argparse
import csv
import json
import re
import itertools
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from html import unescape
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    from bs4 import BeautifulSoup  # type: ignore
except ImportError:  # pragma: no cover - fallback when bs4 unavailable
    BeautifulSoup = None  # type: ignore

HEADER = [
    "Type",
    "SKU",
    "Name",
    "Published",
    "Is featured?",
    "Visibility in catalog",
    "Short description",
    "Description",
    "Date sale price starts",
    "Date sale price ends",
    "Tax status",
    "Tax class",
    "In stock?",
    "Stock",
    "Backorders allowed?",
    "Sold individually?",
    "Weight (lbs)",
    "Length (in)",
    "Width (in)",
    "Height (in)",
    "Allow customer reviews?",
    "Purchase note",
    "Sale price",
    "Regular price",
    "Categories",
    "Tags",
    "Shipping class",
    "Images",
    "Download limit",
    "Download expiry days",
    "Parent",
    "Grouped products",
    "Upsells",
    "Cross-sells",
    "External URL",
    "Button text",
    "Position",
    "Attribute 1 name",
    "Attribute 1 value(s)",
    "Attribute 1 visible",
    "Attribute 1 global",
    "Attribute 2 name",
    "Attribute 2 value(s)",
    "Attribute 2 visible",
    "Attribute 2 global",
    "Attribute 3 name",
    "Attribute 3 value(s)",
    "Attribute 3 visible",
    "Attribute 3 global",
    "Attribute 4 name",
    "Attribute 4 value(s)",
    "Attribute 4 visible",
    "Attribute 4 global",
    "Meta: _wpcom_is_markdown",
    "Download 1 name",
    "Download 1 URL",
    "Download 2 name",
    "Download 2 URL",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert product JSON into WooCommerce CSV")
    parser.add_argument("--input", type=Path, default=Path("product_details.json"))
    parser.add_argument("--output", type=Path, default=Path("woocommerce_products.csv"))
    parser.add_argument("--brand", nargs="*", help="Optional list of brands to include")
    parser.add_argument("--batch", type=int, default=0, help="Maximum number of rows per CSV file (0 for no limit)")
    parser.add_argument("--price-formula", type=str, help="Formula to adjust price (use 'x' for price, e.g. 'x * 1.2')", default="")
    return parser.parse_args()


def load_products(path: Path) -> Dict[str, Dict[str, Any]]:
    try:
        print(f"Loading products from: {path.absolute()}")
        if not path.exists():
            raise FileNotFoundError(f"Product file not found: {path.absolute()}")
        
        with path.open("r", encoding="utf-8") as fp:
            payload = json.load(fp)
        
        products = payload.get("products")
        if not isinstance(products, dict):
            raise ValueError("Invalid JSON structure: missing 'products' mapping")
        
        print(f"Successfully loaded {sum(len(items) for items in products.values())} products")
        return products
    except FileNotFoundError as e:
        print(f"ERROR: {e}")
        raise
    except json.JSONDecodeError as e:
        print(f"ERROR: Failed to parse JSON from {path}: {e}")
        raise
    except Exception as e:
        print(f"ERROR: Unexpected error loading products from {path}: {e}")
        raise


def normalize_price(value: Optional[str]) -> str:
    if not value:
        return ""
    cleaned = value.strip().replace(" ", "").replace(",", ".")
    try:
        decimal_value = Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return ""
    quantized = decimal_value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return format(quantized, "f")


def apply_price_formula(price_str: str, formula: str) -> str:
    """
    Applies a formula to the price string.
    Formula should use 'x' as the variable for the price.
    Returns the new price as a string formatted to 2 decimal places.
    """
    if not price_str or not formula:
        return price_str
    
    try:
        # Convert price string to float for calculation
        x = float(price_str)
        
        # Safe evaluation environment
        allowed_names = {"x": x, "price": x, "min": min, "max": max, "round": round}
        
        # Evaluate formula
        result = eval(formula, {"__builtins__": {}}, allowed_names)
        
        # Convert back to Decimal for precise rounding
        decimal_result = Decimal(str(result))
        quantized = decimal_result.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return format(quantized, "f")
    except Exception as e:
        # If anything goes wrong (e.g. invalid formula), return original price
        # In a real app we might want to log this
        return price_str


def bool_flag(condition: bool) -> str:
    return "1" if condition else "0"


def coalesce(*values: Optional[str]) -> str:
    for value in values:
        if value:
            return str(value)
    return ""


def dedupe_preserve(values: Iterable[str]) -> List[str]:
    seen = set()
    result: List[str] = []
    for value in values:
        if not value:
            continue
        key = value.strip().lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(value.strip())
    return result


BR_RE = re.compile(r"<\s*br\s*/?>", re.IGNORECASE)
BLOCK_TAG_RE = re.compile(r"</?(?:p|div|li|h[1-6]|tr|td|th)>", re.IGNORECASE)
TAG_RE = re.compile(r"<[^>]+>")


def html_to_plain(html: Optional[str]) -> str:
    if not html:
        return ""
    if BeautifulSoup is not None:
        soup = BeautifulSoup(html, "lxml")
        text = soup.get_text("\n")
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        return "\n".join(lines)
    intermediate = BR_RE.sub("\n", html)
    intermediate = BLOCK_TAG_RE.sub("\n", intermediate)
    intermediate = TAG_RE.sub("", intermediate)
    text = unescape(intermediate)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines)


def format_categories(product: Dict[str, Any]) -> str:
    raw_path = product.get("category_path") or []
    if isinstance(raw_path, list):
        categories = [str(item).strip() for item in raw_path if str(item).strip()]
    else:
        categories = []
    brand_value = product.get("brand")
    if brand_value:
        brand_title = str(brand_value).strip().title()
        if brand_title and brand_title.lower() not in {item.lower() for item in categories}:
            categories.insert(0, brand_title)
    if not categories:
        return ""
    # Remove consecutive duplicates
    deduped_categories: List[str] = []
    for category in categories:
        if not deduped_categories or category.lower() != deduped_categories[-1].lower():
            deduped_categories.append(category)
    
    hierarchical: List[str] = []
    current: List[str] = []
    for category in deduped_categories:
        current.append(category)
        hierarchical.append(" > ".join(current))
    return ", ".join(hierarchical)


def build_images_field(product: Dict[str, Any]) -> str:
    urls: List[str] = []
    image_urls = product.get("image_urls") or []
    if isinstance(image_urls, list):
        urls.extend([u for u in image_urls if u])
    gallery = product.get("images", {}).get("gallery") if isinstance(product.get("images"), dict) else []
    if isinstance(gallery, list):
        for entry in gallery:
            if not isinstance(entry, dict):
                continue
            for key in ("primary", "original", "large", "small", "src"):
                candidate = entry.get(key)
                if candidate:
                    urls.append(candidate)
                    break
    
    # Filter out no-picture.jpg
    filtered_urls = [u for u in urls if not u.lower().endswith("no-picture.jpg")]
    
    deduped = dedupe_preserve(filtered_urls)
    return ", ".join(deduped)


def pick_sku(product: Dict[str, Any]) -> str:
    return coalesce(product.get("sku"), product.get("part_number"), product.get("product_id"))


def stock_flag(product: Dict[str, Any]) -> str:
    availability = product.get("availability") or {}
    status = str(availability.get("status") or "").lower()
    classes = [str(item).lower() for item in availability.get("classes") or []]
    indicators = {status, *classes}
    return bool_flag(any(token in {"available", "instock", "in-stock"} for token in indicators))


def clean_description_html(html_content: str) -> str:
    if not html_content:
        return ""

    # 1. Replace newlines with space instead of <br> - REMOVED to preserve formatting
    # cleaned = html_content.replace("\n", " ").replace("\t", " ").replace("\r", " ")
    cleaned = html_content
    
    # 2. Remove "Documentation" section and everything after it
    cleaned = re.sub(r"<h3>Documentation</h3>.*$", "", cleaned, flags=re.IGNORECASE | re.DOTALL)
    
    # 3. Remove "Manufacturer Information" section
    cleaned = re.sub(r"<h3>Manufacturer Information</h3>.*?(?=<h3>|$)", "", cleaned, flags=re.IGNORECASE | re.DOTALL)
    
    return cleaned.strip()


def get_product_info_descriptions(product: Dict[str, Any]) -> Tuple[str, str]:
    """
    Returns (short_description, long_description) based on product_information entries.
    Logic:
    - Check 'Overview' and 'Description' entries in product_information.
    - Check for existence using 'text' field.
    - Use 'html' field for content.
    - If both exist: Short = Overview, Long = Description.
    - If only Description: Short = "", Long = Description.
    - If only Overview: Short = "", Long = Overview.
    - If neither: Both empty.
    """
    info = product.get("product_information") or []
    if not isinstance(info, list):
        info = []
        
    overview_entry = next((item for item in info if isinstance(item, dict) and item.get("title", "").strip().lower() == "overview"), None)
    description_entry = next((item for item in info if isinstance(item, dict) and item.get("title", "").strip().lower() == "description"), None)

    has_overview = overview_entry and overview_entry.get("text", "").strip()
    has_description = description_entry and description_entry.get("text", "").strip()

    short_desc_html = ""
    long_desc_html = ""

    if has_overview and has_description:
        short_desc_html = overview_entry.get("html", "")
        long_desc_html = description_entry.get("html", "")
    elif has_description:
        long_desc_html = description_entry.get("html", "")
    elif has_overview:
        long_desc_html = overview_entry.get("html", "")
        
    return clean_description_html(short_desc_html), clean_description_html(long_desc_html)


def download_fields(product: Dict[str, Any]) -> Dict[str, str]:
    documents = product.get("documents") or []
    downloads: Dict[str, str] = {}
    if isinstance(documents, list):
        limited = [doc for doc in documents if isinstance(doc, dict) and doc.get("url")][:2]
        for idx, doc in enumerate(limited, start=1):
            name_key = f"Download {idx} name"
            url_key = f"Download {idx} URL"
            downloads[name_key] = doc.get("label") or doc.get("url") or ""
            downloads[url_key] = doc.get("url") or ""
    return downloads


def build_row(product: Dict[str, Any], price_formula: str = "") -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    
    # --- Parent Product Row ---
    parent_row = {key: "" for key in HEADER}
    parent_row["Type"] = "simple"  # Will change to 'variable' if variations exist
    sku = pick_sku(product)
    parent_row["SKU"] = sku
    parent_row["Name"] = coalesce(product.get("title"))
    parent_row["Published"] = "1"
    parent_row["Is featured?"] = "0"
    parent_row["Visibility in catalog"] = "visible"
    
    # New description logic
    short_desc, long_desc = get_product_info_descriptions(product)
    parent_row["Short description"] = short_desc
    parent_row["Description"] = long_desc
    
    parent_row["Tax status"] = "taxable"
    parent_row["In stock?"] = stock_flag(product)
    parent_row["Backorders allowed?"] = "0"
    parent_row["Sold individually?"] = "0"
    parent_row["Allow customer reviews?"] = "1"
    
    # Price handling with formula
    raw_price = normalize_price(coalesce(product.get("price", {}).get("amount")))
    if price_formula:
        parent_row["Regular price"] = apply_price_formula(raw_price, price_formula)
    else:
        parent_row["Regular price"] = raw_price
        
    parent_row["Categories"] = format_categories(product)
    parent_row["Images"] = build_images_field(product)
    parent_row["Meta: _wpcom_is_markdown"] = "0"
    parent_row.update(download_fields(product))
    
    variations = product.get("variations", [])
    
    if not variations or not isinstance(variations, list):
        rows.append(parent_row)
        return rows

    # --- Handle Variable Product ---
    parent_row["Type"] = "variable"
    
    # Prepare attributes for Cartesian product
    attr_names = []
    attr_options_list = []
    
    # We only support up to 4 attributes in the CSV structure defined
    valid_variations = variations[:4]
    
    for idx, variation in enumerate(valid_variations, start=1):
        if not isinstance(variation, dict):
            continue
        
        var_name = variation.get("name", "")
        var_options = variation.get("options", [])
        
        if var_name and var_options:
            attr_names.append(var_name)
            attr_options_list.append(var_options)
            
            # Populate parent row attributes (visible & global)
            options_str = ", ".join(str(opt) for opt in var_options if opt)
            parent_row[f"Attribute {idx} name"] = var_name
            parent_row[f"Attribute {idx} value(s)"] = options_str
            parent_row[f"Attribute {idx} visible"] = "1"
            parent_row[f"Attribute {idx} global"] = "1"

    rows.append(parent_row)

    # --- Generate Variation Rows ---
    # Create a Cartesian product of all options
    # e.g. Size=[20"], Color=[Red, Blue] -> (20", Red), (20", Blue)
    if attr_options_list:
        combinations = list(itertools.product(*attr_options_list))
        
        for combo in combinations:
            var_row = {key: "" for key in HEADER}
            var_row["Type"] = "variation"
            var_row["Parent"] = sku  # Link to parent SKU
            var_row["Published"] = "1"
            var_row["Visibility in catalog"] = "visible"
            var_row["Tax status"] = "taxable"
            var_row["In stock?"] = parent_row["In stock?"] # Inherit stock status
            var_row["Regular price"] = parent_row["Regular price"] # Inherit price
            
            # Populate specific attribute values for this variation
            for idx, value in enumerate(combo, start=1):
                var_row[f"Attribute {idx} name"] = attr_names[idx-1]
                var_row[f"Attribute {idx} value(s)"] = str(value)
                var_row[f"Attribute {idx} global"] = "1"
                # Attribute visible is usually empty for variations in the example
            
            rows.append(var_row)
            
    return rows


def filter_products(products: Dict[str, Dict[str, Any]], brands: Optional[List[str]]) -> List[Dict[str, Any]]:
    if not brands:
        brands_lower: Optional[List[str]] = None
    else:
        brands_lower = [brand.lower() for brand in brands]
    collected: List[Dict[str, Any]] = []
    for brand, items in products.items():
        if brands_lower and brand.lower() not in brands_lower:
            continue
        for product in items.values():
            if isinstance(product, dict):
                collected.append(product)
    return collected


def write_csv(path: Path, rows: Iterable[Dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=HEADER, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main() -> None:
    args = parse_args()
    products = load_products(args.input)
    filtered = filter_products(products, args.brand)
    if not filtered:
        raise SystemExit("No products matched the requested filters")
    
    all_rows = []
    batch_index = 1
    
    for product in filtered:
        product_rows = build_row(product, args.price_formula)
        all_rows.extend(product_rows)
        
        # Check for batch limit
        # Only split if limit is set (>0), limit is reached, AND last row is simple
        if args.batch > 0 and len(all_rows) >= args.batch:
            last_row_type = all_rows[-1].get("Type")
            if last_row_type == "simple":
                # Flush current batch
                output_path = args.output.parent / f"{args.output.stem}_{batch_index}{args.output.suffix}"
                write_csv(output_path, all_rows)
                print(f"Wrote batch {batch_index} with {len(all_rows)} rows to {output_path}")
                
                all_rows = []
                batch_index += 1
    
    # Write remaining rows
    if all_rows:
        if args.batch > 0:
            output_path = args.output.parent / f"{args.output.stem}_{batch_index}{args.output.suffix}"
            write_csv(output_path, all_rows)
            print(f"Wrote batch {batch_index} with {len(all_rows)} rows to {output_path}")
        else:
            # No batching, write to original output path
            write_csv(args.output, all_rows)
            print(f"Wrote {len(all_rows)} rows to {args.output}")


if __name__ == "__main__":
    main()
