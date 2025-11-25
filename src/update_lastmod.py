import xml.etree.ElementTree as ET
import json
import os
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeRemainingColumn
from rich.panel import Panel
from rich.theme import Theme

# Define a custom theme for a pretty UI
custom_theme = Theme({
    "info": "cyan",
    "warning": "yellow",
    "error": "bold red",
    "success": "bold green",
    "highlight": "magenta"
})

console = Console(theme=custom_theme)



def parse_sitemap(xml_path):
    """Parses the sitemap.xml and returns a dictionary of {url: lastmod}."""
    if not os.path.exists(xml_path):
        console.print(f"[error]Error: {xml_path} not found.[/error]")
        return {}

    url_map = {}
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
        
        # Handle namespace
        ns = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
        
        # Find all url entries
        urls = root.findall('ns:url', ns)
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console
        ) as progress:
            task = progress.add_task("[cyan]Parsing Sitemap...", total=len(urls))
            
            for url_entry in urls:
                loc = url_entry.find('ns:loc', ns)
                lastmod = url_entry.find('ns:lastmod', ns)
                
                if loc is not None and lastmod is not None:
                    url_map[loc.text.strip()] = lastmod.text.strip()
                
                progress.advance(task)
                
        console.print(f"[success]Successfully parsed {len(url_map)} URLs from {xml_path}[/success]")
        return url_map

    except ET.ParseError as e:
        console.print(f"[error]Error parsing XML: {e}[/error]")
        return {}
    except Exception as e:
        console.print(f"[error]Unexpected error: {e}[/error]")
        return {}

def update_json(json_path, url_map):
    """Updates the product_details.json with lastmod dates."""
    if not os.path.exists(json_path):
        console.print(f"[error]Error: {json_path} not found.[/error]")
        return

    try:
        with console.status("[bold green]Loading JSON data...[/bold green]"):
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

        if 'products' not in data:
            console.print("[error]Invalid JSON structure: 'products' key missing.[/error]")
            return

        updated_count = 0
        total_products = 0
        
        # Calculate total products for progress bar
        for category in data['products']:
            total_products += len(data['products'][category])

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeRemainingColumn(),
            console=console
        ) as progress:
            task = progress.add_task("[magenta]Updating Products...", total=total_products)

            for category, products in data['products'].items():
                for product_url, product_data in products.items():
                    # Strip query parameters for matching
                    clean_url = product_url.split('?')[0]
                    
                    if clean_url in url_map:
                        product_data['lastmod'] = url_map[clean_url]
                        updated_count += 1
                    
                    progress.advance(task)

        with console.status("[bold green]Saving updated JSON...[/bold green]"):
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)

        console.print(Panel(f"[success]Update Complete![/success]\n\n[info]Total Products Processed:[/info] {total_products}\n[info]Products Updated:[/info] {updated_count}", title="Summary", border_style="green"))

    except json.JSONDecodeError as e:
        console.print(f"[error]Error decoding JSON: {e}[/error]")
    except Exception as e:
        console.print(f"[error]Unexpected error: {e}[/error]")

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Update lastmod dates in product details")
    parser.add_argument("--sitemap", default="sitemap.xml", help="Path to sitemap.xml")
    parser.add_argument("--input", default="product_details.json", help="Path to product_details.json")
    args = parser.parse_args()

    console.print(Panel.fit("[bold blue]AC Schnitzer Sitemap Updater[/bold blue]", subtitle="v1.4"))
    
    url_map = parse_sitemap(args.sitemap)
    
    if url_map:
        update_json(args.input, url_map)

if __name__ == "__main__":
    main()
