import json
import requests
from bs4 import BeautifulSoup
import time
import os
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn
from rich.table import Table

# Initialize Rich console
console = Console()

def find_last_page(base_url, brand, headers):
    """
    Finds the last page number for a brand that has products.
    First finds the highest page that returns 200, then finds the last page with products within that range.
    """
    console.print(f"🕵️  [bold cyan]Finding last page for {brand.upper()}[/bold cyan]")
    
    # Step 1: Find the highest page that returns 200 (not 404)
    start = 1
    end = 1000
    max_page = 1
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
    ) as progress:
        task = progress.add_task(f"Finding max page for {brand}...", total=None)
        while start <= end:
            mid = (start + end) // 2
            url = f"{base_url}/{brand}/?p={mid}"
            progress.update(task, description=f"Testing page {mid} for 200")
            
            try:
                response = requests.get(url, timeout=10, headers=headers)
                if response.status_code == 404:
                    console.print(f"  ➡️ Page {mid}: [yellow]Not found (404)[/yellow]. Max page is lower.")
                    end = mid - 1
                else:
                    console.print(f"  ➡️ Page {mid}: [green]Found (200)[/green]. Max page is at least {mid}.")
                    max_page = mid
                    start = mid + 1
            except requests.exceptions.RequestException as e:
                console.print(f"  ➡️ Page {mid}: [red]Request failed: {e}[/red]. Assuming not found.")
                end = mid - 1
            time.sleep(0.5)
    
    console.print(f"📏 [bold]Max page for {brand.upper()}: {max_page}[/bold]")
    
    # Step 2: Find the last page with products by searching from max_page down
    last_page = 0
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
    ) as progress:
        task = progress.add_task(f"Finding last product page for {brand}...", total=max_page)
        for page in range(max_page, 0, -1):
            progress.update(task, advance=1, description=f"Checking page {page} for products")
            url = f"{base_url}/{brand}/?p={page}"
            
            try:
                response = requests.get(url, timeout=10, headers=headers)
                if response.status_code == 404:
                    console.print(f"  ➡️ Page {page}: [yellow]Not found (404)[/yellow].")
                    continue
                response.raise_for_status()
                soup = BeautifulSoup(response.content, 'lxml')
                buttons = soup.find_all('a', class_='buybox--button')
                if buttons:
                    console.print(f"  ➡️ Page {page}: [green]Found products[/green]. This is the last page.")
                    last_page = page
                    break
                else:
                    console.print(f"  ➡️ Page {page}: [dim]No products (200)[/dim].")
            except requests.exceptions.RequestException as e:
                console.print(f"  ➡️ Page {page}: [red]Request failed: {e}[/red].")
            time.sleep(0.5)

    if last_page == 0:
        console.print(f"⚠️  [yellow]No products found for {brand.upper()}. Setting last page to 1.[/yellow]")
        last_page = 1

    console.print(f"✅ [bold green]Found last page with products for {brand.upper()}: {last_page}[/bold green]")
    return last_page

def scrape_product_links(output_file="product_links.json"):
    """
    Scrapes product links from the AC Schnitzer website for all categories and pages,
    and saves them to a JSON file.
    Allows specifying max pages and start page per brand for controlled scraping.
    """
    
    scrape_config = {
        "max_pages_per_brand": {
            "default": None, # No limit by default
            "bmw": None,
        },
        "start_page_per_brand": {
            "default": 1,
        },
        "end_page_search_start": {
            "default": 1000,
        }
    }

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    }
    base_url = "https://www.ac-schnitzer.de/en"
    brands = ["bmw", "mini", "toyota", "accessoires"]
    
    try:
        with open(output_file, 'r') as f:
            output_data = json.load(f)
            product_links = output_data.get("product_links", {brand: [] for brand in brands})
            console.print(f"✅ [green]Loaded existing links from {output_file}.[/green]")
    except (FileNotFoundError, json.JSONDecodeError):
        product_links = {brand: [] for brand in brands}
        console.print(f"📝 [yellow]No existing file found at {output_file} or file is empty. Starting fresh.[/yellow]")

    for brand in brands:
        console.print(Panel(f"Processing Brand: [bold blue]{brand.upper()}[/bold blue]", expand=False, border_style="blue"))
        
        start_page = scrape_config["start_page_per_brand"].get(brand, scrape_config["start_page_per_brand"]["default"])
        max_pages_to_scrape = scrape_config["max_pages_per_brand"].get(brand, scrape_config["max_pages_per_brand"]["default"])
        
        total_pages = find_last_page(base_url, brand, headers)
        
        if max_pages_to_scrape is None:
            max_pages_to_scrape = total_pages
        
        pages_to_scrape = min(total_pages, max_pages_to_scrape)

        with Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TextColumn("({task.completed} of {task.total})"),
            SpinnerColumn(),
        ) as progress:
            task = progress.add_task(f"Scraping {brand}...", total=pages_to_scrape)

            for page in range(start_page, start_page + pages_to_scrape):
                progress.update(task, advance=1, description=f"Scraping page {page}/{total_pages}")
                
                url = f"{base_url}/{brand}/?p={page}"
                
                try:
                    response = requests.get(url, timeout=10, headers=headers)
                    if response.status_code == 404:
                        console.print(f"    - Page {page}: [yellow]Not found (404).[/yellow] Assuming end of category.")
                        break
                    response.raise_for_status()

                    soup = BeautifulSoup(response.content, 'lxml')
                    details_buttons = soup.find_all('a', class_='buybox--button')

                    new_links_found = 0
                    for details_button in details_buttons:
                        if details_button and details_button.get('href'):
                            link = details_button.get('href')
                            if link not in product_links[brand]:
                                product_links[brand].append(link)
                                new_links_found += 1
                    
                    if new_links_found > 0:
                        console.print(f"    - Page {page}: [green]Found {new_links_found} new links.[/green]")
                    else:
                        console.print(f"    - Page {page}: [dim]Found 0 new links.[/dim]")

                    time.sleep(1)

                except requests.exceptions.RequestException as e:
                    console.print(f"    - Page {page}: [red]An error occurred: {e}[/red]")
                    break
        
        console.print(f"💾 [bold]Finished scraping for {brand}. Saving data...[/bold]")
        link_counts = {brand: len(links) for brand, links in product_links.items()}
        output_data = {"link_counts": link_counts, "product_links": product_links}
        with open(output_file, 'w') as f:
            json.dump(output_data, f, indent=4)
        console.print(f"...{output_file} saved.")

    console.print(Panel("[bold green]🎉 Scraping complete for all brands! 🎉[/bold green]", expand=False))
    
    table = Table(title="Final Link Counts")
    table.add_column("Brand", justify="right", style="cyan", no_wrap=True)
    table.add_column("Link Count", justify="center", style="magenta")

    for brand, count in {b: len(l) for b, l in product_links.items()}.items():
        table.add_row(brand.upper(), str(count))
        
    console.print(table)


    console.print(table)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Scrape product links")
    parser.add_argument("--output", default="product_links.json", help="Output JSON file")
    args = parser.parse_args()
    
    scrape_product_links(args.output)

if __name__ == '__main__':
    main()