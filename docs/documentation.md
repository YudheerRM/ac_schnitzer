# AC Schnitzer Product Scraper & Converter Documentation

## Project Overview
This project is designed to automate the process of cloning product data from the AC Schnitzer website and preparing it for import into a WooCommerce store. The workflow consists of three main stages: gathering product links, scraping detailed product information, and converting that data into a CSV format compatible with WooCommerce's product importer.

## Project Structure

The project is organized as follows:

-   **`src/`**: Contains all Python source code and scripts.
-   **`data/`**: Stores persistent data files like JSON databases and sitemaps.
-   **`output/`**: Destination for generated CSV files.
-   **`docs/`**: Project documentation.
-   **`Dockerfile` & `docker-compose.yml`**: Deployment configuration.

## Workflow
The project follows a linear pipeline, orchestrated by `src/run_updates.py`:
1.  **Link Discovery**: `src/scrape_links.py` crawls the target website to find all product URLs.
2.  **Data Extraction**: `src/scrape_products.py` visits each URL to extract comprehensive product details.
3.  **Data Transformation**: `src/convert_products_to_csv.py` processes the extracted data and formats it into a WooCommerce-ready CSV file.

## Scripts Description

### 1. `src/run_updates.py`
**Purpose**: Orchestrates the entire update workflow. It downloads the sitemap, checks for updates, scrapes updated products, and generates a CSV.
**Usage**:
```bash
python src/run_updates.py
```

### 2. `src/scrape_links.py`
**Purpose**: Discovers and collects all product URLs.
**Usage**:
```bash
python src/scrape_links.py --output data/product_links.json
```

### 3. `src/scrape_products.py`
**Purpose**: Visits each collected link and scrapes detailed product attributes.
**Usage**:
```bash
python src/scrape_products.py --input_links data/product_links.json --output data/product_details.json
```

### 4. `src/convert_products_to_csv.py`
**Purpose**: Transforms the raw JSON data into a CSV file.
**Usage**:
```bash
python src/convert_products_to_csv.py --input data/product_details.json --output output/woocommerce_products.csv
```

### 5. `src/update_lastmod.py`
**Purpose**: Updates the `product_details.json` file with `lastmod` dates extracted from `sitemap.xml`.
**Usage**:
```bash
python src/update_lastmod.py --sitemap data/sitemap.xml --input data/product_details.json
```

## Deployment
The project is containerized using Docker. See `docs/deployment_plan.md` for details.

## Pricing Formula
It appears that the client uses a formula that takes the scraped euro price from AC Schnitzer, applies a discount, converts to NOK, and then adds a percent based markup to determine the final price.

Final Pricing Formula:

Let:

P_eur = scraped Euro price

d = discount = 24.5% = 0.245

r = conversion rate = 12.0231788079

m = markup = 27.7884880198% = 0.277884880198

Step-by-step formula

Apply discount:
P₁ = P_eur × (1 − d)

Convert EUR → NOK:
P₂ = P₁ × r

Apply markup:
Final Price = P₂ × (1 + m)

Single-line Final Formula
Final Price=Peur*0.755*12.0231788079*1.277884880198
