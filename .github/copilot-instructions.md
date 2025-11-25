# AC Schnitzer Product Scraper - Copilot Instructions

## Project Overview
This is a **web scraping pipeline** that extracts product data from the AC Schnitzer website and converts it to WooCommerce-compatible CSV format. It runs as a Docker-containerized Streamlit web app or scheduled background job.

## Architecture & Data Flow
```
sitemap-1.xml.gz → scrape_links.py → product_links.json
                                          ↓
                   scrape_products.py → product_details.json
                                          ↓
              convert_products_to_csv.py → woocommerce_products.csv
```

**Orchestration**: `run_updates.py` coordinates the incremental update flow by comparing sitemap `lastmod` dates against stored data.

## Key Directories
- **`src/`**: All Python scripts (entry points have CLI via `argparse`)
- **`data/`**: JSON databases and sitemap XML (persisted in Docker volume)
- **`output/`**: Generated WooCommerce CSV files

## Critical Data Structures

### `data/product_links.json`
```json
{
  "link_counts": {"bmw": 4778, "mini": 539, ...},
  "product_links": {"bmw": ["https://..."], "mini": [...]}
}
```

### `data/product_details.json`
Nested structure: `products.<brand>.<url>` containing scraped attributes (title, price, images, variants, etc.)

## Running the Project

### Docker (Recommended)
```bash
docker-compose up --build     # Starts Streamlit UI on port 8501
```
Toggle between Web UI and scheduler in `docker-compose.yml` via `command:` directive.

### Local Development
```bash
pip install -r requirements.txt
streamlit run src/app.py                    # Web UI
python src/run_updates.py                   # Full update pipeline
python src/scrape_products.py --help        # See CLI options
```

## Code Conventions

### Scraping Patterns
- Use `requests.Session` with `DEFAULT_HEADERS` (see `scrape_products.py` lines 26-34)
- Implement request delays (`DEFAULT_DELAY = 0.5`) to avoid rate limiting
- Use `BeautifulSoup` with `lxml` parser for HTML parsing
- Rich console output for progress tracking (`rich.progress`, `rich.console`)

### Path Resolution
All scripts use `Path(__file__).resolve().parent.parent` to find `BASE_DIR`:
```python
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
```

### URL Normalization
Product URLs are normalized by extracting the slug (last path segment) to handle URL variations:
```python
# Same product, different URLs:
# .../371/product-slug/?c=123
# .../372/product-slug/
# Both normalize to: "product-slug"
```

## When Modifying Scrapers
1. **Selector changes**: Product page structure is parsed in `scrape_products.py` - check `element_text()` helper and BeautifulSoup selectors
2. **New brands**: Add to `scrape_config` in `scrape_links.py` (line ~93)
3. **CSV fields**: Modify `HEADER` list in `convert_products_to_csv.py` (WooCommerce import format)
4. **Sitemap URL**: Defined in `run_updates.py` as `SITEMAP_URL` constant

## Integration Points
- **Source**: `https://www.ac-schnitzer.de/` (German auto parts retailer)
- **Sitemap**: `SITEMAP_URL` in `run_updates.py` - gzipped XML
- **Target**: WooCommerce product import CSV format

## Scheduler
`scheduler.py` uses the `schedule` library to run `run_updates.main()` daily at 08:00 UTC. Logs to stdout.
