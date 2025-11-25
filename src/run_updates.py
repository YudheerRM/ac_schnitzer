import gzip
import json
import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Set

import requests
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeElapsedColumn
from rich.theme import Theme

# Define custom theme
custom_theme = Theme({
    "info": "cyan",
    "warning": "yellow",
    "error": "bold red",
    "success": "bold green",
    "highlight": "magenta"
})

console = Console(theme=custom_theme)

# Constants
SITEMAP_URL = "https://www.ac-schnitzer.de/web/sitemap/shop-3/sitemap-1.xml.gz"
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "output"
SRC_DIR = BASE_DIR / "src"

SITEMAP_GZ = DATA_DIR / "sitemap-1.xml.gz"
SITEMAP_XML = DATA_DIR / "sitemap-1.xml"
PRODUCT_DETAILS_FILE = DATA_DIR / "product_details.json"
UPDATED_PRODUCTS_JSON = DATA_DIR / "updated_products.json"
UPDATED_PRODUCT_DETAILS_JSON = DATA_DIR / "updated_product_details.json"
UPDATED_CSV = OUTPUT_DIR / "woocommerce_products_updated.csv"

def download_sitemap():
    """Downloads the sitemap gz file."""
    console.print(f"[info]Downloading sitemap from {SITEMAP_URL}...[/info]")
    try:
        response = requests.get(SITEMAP_URL, stream=True)
        response.raise_for_status()
        with open(SITEMAP_GZ, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        console.print("[success]Sitemap downloaded successfully.[/success]")
        return True
    except Exception as e:
        console.print(f"[error]Failed to download sitemap: {e}[/error]")
        return False

def extract_sitemap():
    """Extracts the sitemap gz file and deletes the archive."""
    console.print("[info]Extracting sitemap...[/info]")
    try:
        with gzip.open(SITEMAP_GZ, 'rb') as f_in:
            with open(SITEMAP_XML, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
        
        # Remove the gz file
        os.remove(SITEMAP_GZ)
        console.print("[success]Sitemap extracted and gz file deleted.[/success]")
        return True
    except Exception as e:
        console.print(f"[error]Failed to extract sitemap: {e}[/error]")
        return False

def parse_sitemap(xml_path: Path) -> Dict[str, str]:
    """Parses the sitemap.xml and returns a dictionary of {url: lastmod}."""
    if not xml_path.exists():
        console.print(f"[error]Error: {xml_path} not found.[/error]")
        return {}

    url_map = {}
    skipped_categories = 0
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
        
        # Handle namespace
        ns = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
        
        # Find all url entries
        urls = root.findall('ns:url', ns)
        
        for url_entry in urls:
            loc = url_entry.find('ns:loc', ns)
            lastmod = url_entry.find('ns:lastmod', ns)
            
            if loc is not None and lastmod is not None:
                url = loc.text.strip()
                
                # Skip category/listing pages
                if is_category_page(url):
                    skipped_categories += 1
                    continue
                    
                url_map[url] = lastmod.text.strip()
                
        console.print(f"[success]Parsed {len(url_map)} product URLs from sitemap (skipped {skipped_categories} category pages).[/success]")
        return url_map

    except Exception as e:
        console.print(f"[error]Error parsing XML: {e}[/error]")
        return {}

def normalize_url(url: str) -> str:
    """
    Normalizes a URL by extracting the product slug.
    This handles cases where the same product has different IDs in the URL path.
    
    Example:
    .../371/slug/?c=123 -> slug
    .../372/slug/ -> slug
    """
    try:
        # Strip query params and trailing slash
        clean_path = url.split('?')[0].rstrip('/')
        # Get the last segment (slug)
        slug = clean_path.split('/')[-1]
        return slug
    except Exception:
        return url

def is_category_page(url: str) -> bool:
    """
    Determines if a URL is a category/listing page rather than a product page.
    Category pages typically end with category names and don't have product IDs.
    
    Returns True if the URL is a category page (should be skipped).
    """
    # Common category path segments that indicate a listing page, not a product
    category_paths = {
        'wheels', 'wheel-tyre-sets', 'xi-xd-wheel-tyre-sets', 'falcon-wheel-tyre-sets',
        'exhaust', 'engine', 'aerodynamics', 'suspension', 'interior', 'exterior',
        'performance-upgrade-petrol', 'performance-upgrade-diesel', 'sale',
        'accessories', 'pos', 'showroomdesign'
    }
    
    try:
        # Strip query params and trailing slash
        clean_path = url.split('?')[0].rstrip('/')
        # Get the last segment
        last_segment = clean_path.split('/')[-1].lower()
        
        # If the last segment is a known category name, it's a category page
        return last_segment in category_paths
    except Exception:
        return False

def get_existing_products(json_path: Path) -> Dict[str, List[str]]:
    """
    Loads existing products from json.
    Returns a dict mapping normalized_url -> list of original_urls.
    """
    if not json_path.exists():
        console.print(f"[warning]{json_path} not found. Assuming no existing products.[/warning]")
        return {}
    
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        products_map = {}
        if 'products' in data:
            for brand, items in data['products'].items():
                for url, details in items.items():
                    norm_url = normalize_url(url)
                    if norm_url not in products_map:
                        products_map[norm_url] = []
                    # Store tuple of (original_url, details) or just original_url?
                    # We need details to check lastmod.
                    # Let's store the details directly in a wrapper or just reference the dict in memory?
                    # Since we loaded 'data' into memory, we can store references to the 'details' dict.
                    products_map[norm_url].append({'url': url, 'details': details})
        return products_map
    except Exception as e:
        console.print(f"[error]Error loading existing products: {e}[/error]")
        return {}

def identify_updates(sitemap_urls: Dict[str, str], existing_products_map: Dict[str, List[Dict]]) -> List[str]:
    """Identifies URLs that need to be scraped."""
    updates = []
    seen_normalized = set()
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console
    ) as progress:
        task = progress.add_task("[cyan]Checking for updates...", total=len(sitemap_urls))
        
        for url, lastmod in sitemap_urls.items():
            norm_url = normalize_url(url)
            
            # Deduplication: If we've already marked this product (normalized) for update, skip other variations
            if norm_url in seen_normalized:
                progress.advance(task)
                continue
            
            if norm_url in existing_products_map:
                # Check against all matching existing products (usually just one)
                # If ANY of them is up-to-date, we might consider it up-to-date?
                # Or if ALL are stale?
                # Usually there's one match.
                
                needs_update = False
                # If we find a match, we compare dates.
                # If sitemap date > existing date, we update.
                
                # We assume the sitemap URL corresponds to the "current" version of the product.
                # We check the max lastmod of existing matches?
                
                # Let's check if *any* existing match has the same or newer date.
                is_up_to_date = False
                for entry in existing_products_map[norm_url]:
                    existing_lastmod = entry['details'].get('lastmod')
                    if existing_lastmod and lastmod and existing_lastmod >= lastmod:
                        is_up_to_date = True
                        break
                
                if not is_up_to_date:
                    updates.append(url)
                    seen_normalized.add(norm_url)
            else:
                # New product
                updates.append(url)
                seen_normalized.add(norm_url)
            
            progress.advance(task)
            
    return updates

def update_product_details_lastmod(json_path: Path, sitemap_urls: Dict[str, str]):
    """Updates the lastmod dates in the main product_details.json file."""
    if not json_path.exists():
        return

    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        # Build a map of normalized sitemap URLs to (original_sitemap_url, lastmod)
        sitemap_norm_map = {}
        for url, lastmod in sitemap_urls.items():
            sitemap_norm_map[normalize_url(url)] = lastmod

        updated_count = 0
        if 'products' in data:
            for brand, items in data['products'].items():
                for url, details in items.items():
                    norm_url = normalize_url(url)
                    
                    if norm_url in sitemap_norm_map:
                        new_lastmod = sitemap_norm_map[norm_url]
                        current_lastmod = details.get('lastmod')
                        
                        if current_lastmod != new_lastmod:
                            details['lastmod'] = new_lastmod
                            updated_count += 1

        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
            
        console.print(f"[success]Updated lastmod dates for {updated_count} products in {json_path.name}[/success]")
            
    except Exception as e:
        console.print(f"[error]Failed to update lastmod in product_details.json: {e}[/error]")

def merge_updates(main_file: Path, updates_file: Path, sitemap_urls: Dict[str, str]):
    """Merges scraped updates into the main product details file."""
    console.print(Panel("[bold magenta]Merging Updates into Main Database...[/bold magenta]"))
    
    if not updates_file.exists():
        console.print(f"[error]Updates file {updates_file} not found. Skipping merge.[/error]")
        return

    try:
        # Load main file
        if main_file.exists():
            with open(main_file, 'r', encoding='utf-8') as f:
                main_data = json.load(f)
        else:
            main_data = {"meta": {}, "products": {}}

        # Load updates file
        with open(updates_file, 'r', encoding='utf-8') as f:
            updates_data = json.load(f)

        merged_count = 0
        
        # Prepare sitemap normalization map for lastmod lookup
        sitemap_norm_map = {}
        for url, lastmod in sitemap_urls.items():
            sitemap_norm_map[normalize_url(url)] = lastmod

        if 'products' in updates_data:
            for brand, items in updates_data['products'].items():
                if brand not in main_data['products']:
                    main_data['products'][brand] = {}
                
                for url, details in items.items():
                    # Update the product data
                    main_data['products'][brand][url] = details
                    
                    # Ensure lastmod is set correctly from sitemap
                    norm_url = normalize_url(url)
                    if norm_url in sitemap_norm_map:
                        main_data['products'][brand][url]['lastmod'] = sitemap_norm_map[norm_url]
                        # console.print(f"[debug]Set lastmod for {norm_url}[/debug]") # Too verbose
                    else:
                        console.print(f"[warning]Could not find lastmod for {url} (norm: {norm_url})[/warning]")
                    
                    merged_count += 1

        # Update meta
        main_data['meta']['generated_at'] = datetime.utcnow().isoformat()
        main_data['meta']['total_products'] = sum(len(items) for items in main_data['products'].values())
        main_data['meta']['brand_counts'] = {b: len(i) for b, i in main_data['products'].items()}

        # Save main file
        with open(main_file, 'w', encoding='utf-8') as f:
            json.dump(main_data, f, indent=2)
            
        console.print(f"[success]Merged {merged_count} products into {main_file.name}[/success]")

    except Exception as e:
        console.print(f"[error]Failed to merge updates: {e}[/error]")

def main():
    console.print(Panel.fit("[bold blue]AC Schnitzer Update Workflow[/bold blue]", subtitle="v1.4"))
    
    # 1. Download and Extract Sitemap
    if not download_sitemap():
        return
    if not extract_sitemap():
        return
        
    # 2. Parse Sitemap
    sitemap_urls = parse_sitemap(SITEMAP_XML)
    if not sitemap_urls:
        console.print("[error]No URLs found in sitemap. Aborting.[/error]")
        return

    # 3. Load Existing Products
    existing_products_map = get_existing_products(PRODUCT_DETAILS_FILE)
    
    # 4. Identify Updates
    updated_urls = identify_updates(sitemap_urls, existing_products_map)
    
    if not updated_urls:
        console.print("[success]No updates found. All products are up to date.[/success]")
        # Still update lastmod in main file just in case
        update_product_details_lastmod(PRODUCT_DETAILS_FILE, sitemap_urls)
        return

    console.print(f"[highlight]Found {len(updated_urls)} products to update/add.[/highlight]")
    
    # 5. Save Updated Products List
    with open(UPDATED_PRODUCTS_JSON, 'w', encoding='utf-8') as f:
        json.dump({"products": updated_urls}, f, indent=2)
    console.print(f"[info]Saved updated product list to {UPDATED_PRODUCTS_JSON.name}[/info]")

    # 6. Run Scraper
    console.print(Panel("[bold magenta]Starting Scraper for Updated Products...[/bold magenta]"))
    scrape_cmd = [
        sys.executable,
        str(SRC_DIR / "scrape_products.py"),
        "--input_links", str(UPDATED_PRODUCTS_JSON),
        "--output", str(UPDATED_PRODUCT_DETAILS_JSON)
    ]
    
    try:
        subprocess.run(scrape_cmd, check=True)
    except subprocess.CalledProcessError as e:
        console.print(f"[error]Scraping failed: {e}[/error]")
        return

    # 7. Merge Updates into Main DB
    merge_updates(PRODUCT_DETAILS_FILE, UPDATED_PRODUCT_DETAILS_JSON, sitemap_urls)
    
    # 8. Update lastmod in main file (after successful scrape and merge)
    update_product_details_lastmod(PRODUCT_DETAILS_FILE, sitemap_urls)

    # 9. Run Converter
    console.print(Panel("[bold magenta]Converting Updated Products to CSV...[/bold magenta]"))
    convert_cmd = [
        sys.executable,
        str(SRC_DIR / "convert_products_to_csv.py"),
        "--input", str(UPDATED_PRODUCT_DETAILS_JSON),
        "--output", str(UPDATED_CSV)
    ]
    
    try:
        subprocess.run(convert_cmd, check=True)
        console.print(f"[success]Successfully generated {UPDATED_CSV.name}[/success]")
    except subprocess.CalledProcessError as e:
        console.print(f"[error]Conversion failed: {e}[/error]")
        return

    console.print(Panel.fit("[bold green]Update Workflow Completed Successfully![/bold green]"))

if __name__ == "__main__":
    main()
