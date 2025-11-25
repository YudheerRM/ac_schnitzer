import argparse
import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from requests import Session
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)

console = Console()

BASE_DIR = Path(__file__).resolve().parent
PRODUCT_LINKS_FILE = BASE_DIR / "product_links.json"
OUTPUT_FILE = BASE_DIR / "product_details.json"
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
}
REQUEST_TIMEOUT = 20
DEFAULT_DELAY = 0.5


def element_text(element, separator: str = " ") -> Optional[str]:
    if element is None:
        return None
    text = element.get_text(separator=separator)
    text = text.strip()
    return text or None


def slug_to_title(slug: str) -> str:
    processed = slug.replace("-", " ").strip()
    if not processed:
        return ""
    tokens = []
    for token in processed.split():
        upper_token = token.upper()
        if upper_token in {"BMW", "MINI", "AC", "GR"}:
            tokens.append(upper_token)
            continue
        if token.isupper() or token.isdigit() or re.match(r"^[A-Za-z]+\d+$", token):
            tokens.append(token.upper())
            continue
        tokens.append(token.capitalize())
    return " ".join(tokens)


def derive_category_path(product_url: str) -> List[str]:
    parsed = urlparse(product_url)
    segments = [segment for segment in parsed.path.strip("/").split("/") if segment]
    category_segments: List[str] = []
    for segment in segments:
        if segment in {"en"}:
            continue
        if segment.isdigit():
            break
        category_name = slug_to_title(segment)
        if category_name:
            category_segments.append(category_name)
    return category_segments


def text_to_html(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return ""
    return "<br>".join(lines)


def load_links(file_path: Path) -> Dict[str, List[str]]:
    if not file_path.exists():
        raise FileNotFoundError(
            f"Could not find {file_path}. Run scrape_links.py before this script."
        )
    with file_path.open("r", encoding="utf-8") as fp:
        data = json.load(fp)
    
    # Check if we have the standard structure or the updated_products structure
    if "product_links" in data:
        product_links = data.get("product_links")
    elif "products" in data:
        # Handle updated_products.json structure which is just a list of urls under "products" key
        # We need to infer brand or put them all under a generic brand
        # For simplicity, let's try to infer brand from URL or put in "mixed"
        product_links = {}
        for url in data["products"]:
            # Simple brand inference
            brand = "unknown"
            if "bmw" in url.lower(): brand = "bmw"
            elif "mini" in url.lower(): brand = "mini"
            elif "toyota" in url.lower(): brand = "toyota"
            elif "accessoires" in url.lower(): brand = "accessoires"
            
            if brand not in product_links:
                product_links[brand] = []
            product_links[brand].append(url)
    else:
        raise ValueError("Invalid input file structure: missing 'product_links' or 'products' key")
        
    if not isinstance(product_links, dict):
         raise ValueError("Invalid product_links structure")
         
    return {brand: list(links) for brand, links in product_links.items()}


def init_output(file_path: Path) -> Dict[str, Any]:
    if file_path.exists():
        try:
            with file_path.open("r", encoding="utf-8") as fp:
                existing = json.load(fp)
            products = existing.get("products", {})
        except (json.JSONDecodeError, OSError):
            console.print(
                "[yellow]Warning: existing product_details.json is invalid. Starting fresh.[/yellow]"
            )
            products = {}
    else:
        products = {}
    return {
        "meta": {
            "generated_at": None,
            "total_products": 0,
            "brand_counts": {},
        },
        "products": products,
    }


def fetch_page(session: Session, url: str, delay: float, retries: int = 3) -> str:
    last_exception: Optional[Exception] = None
    for attempt in range(1, retries + 1):
        try:
            response = session.get(url, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            time.sleep(delay)
            return response.text
        except requests.RequestException as exc:
            last_exception = exc
            sleep_for = min(2 ** attempt, 10)
            console.print(
                f"    - [yellow]Attempt {attempt} failed for {url} ({exc}). Retrying in {sleep_for:.1f}s[/yellow]"
            )
            time.sleep(sleep_for)
    if last_exception:
        raise last_exception
    raise RuntimeError("Unexpected error fetching page")


def parse_mounting_time(soup: BeautifulSoup) -> Dict[str, Any]:
    mounting_block = soup.select_one(".montage-std-value")
    if not mounting_block:
        return {}
    raw_text = " ".join(mounting_block.stripped_strings)
    numeric_value: Optional[float] = None
    for token in raw_text.replace(",", ".").split():
        try:
            numeric_value = float(token)
            break
        except ValueError:
            continue
    return {
        "raw": raw_text or None,
        "hours": numeric_value,
    }


def parse_availability(soup: BeautifulSoup) -> Dict[str, Any]:
    availability: Dict[str, Any] = {}
    delivery_text = soup.select_one(".product--delivery .delivery--text")
    if delivery_text:
        availability["message"] = " ".join(delivery_text.stripped_strings)
        classes = delivery_text.get("class", [])
        availability["classes"] = classes
        for css_class in classes:
            if css_class.startswith("delivery--text-"):
                availability["status"] = css_class.replace("delivery--text-", "")
                break
    delivery_sign = soup.select_one(".delivery-sign")
    if delivery_sign:
        availability["badge"] = delivery_sign.get_text(strip=True)
    return availability


def parse_breadcrumbs(soup: BeautifulSoup) -> List[Dict[str, str]]:
    breadcrumbs: List[Dict[str, str]] = []
    for li in soup.select("ul.breadcrumb--list li[itemprop='itemListElement']"):
        anchor = li.select_one("a[itemprop='item']")
        if anchor:
            title = anchor.get_text(strip=True)
            href = anchor.get("href") or ""
        else:
            title = li.get_text(strip=True)
            href = ""
        position = li.select_one("meta[itemprop='position']")
        position_value: Optional[int] = None
        if position and position.get("content"):
            try:
                position_value = int(position.get("content"))
            except ValueError:
                position_value = None
        breadcrumbs.append(
            {
                "title": title,
                "url": href,
                "position": position_value,
            }
        )
    return breadcrumbs


def parse_price(soup: BeautifulSoup) -> Dict[str, Any]:
    price_meta = soup.select_one("meta[itemprop='price']")
    currency_meta = soup.select_one("meta[itemprop='priceCurrency']")
    price_block = soup.select_one(".product--price.price--default")
    price_text = " ".join(price_block.stripped_strings) if price_block else None
    return {
        "amount": price_meta.get("content") if price_meta else None,
        "currency": currency_meta.get("content") if currency_meta else None,
        "display": price_text,
    }


def parse_eu_tire_label(soup: BeautifulSoup) -> List[Dict[str, str]]:
    table = soup.select_one(".product--eu-tire-label-table")
    if not table:
        return []
    entries: List[Dict[str, str]] = []
    current: Optional[Dict[str, str]] = None
    for row in table.select("tr"):
        cells = row.find_all("td")
        if not cells:
            continue
        first_cell = cells[0]
        is_label_cell = "is--bold" in first_cell.get("class", []) or first_cell.has_attr("rowspan")
        if is_label_cell:
            label_text = first_cell.get_text(" ", strip=True).rstrip(":")
            current = {"label": label_text}
            entries.append(current)
            detail_cells = cells[1:]
        else:
            detail_cells = cells
        if current is None or len(detail_cells) < 2:
            continue
        key_text = detail_cells[0].get_text(" ", strip=True).rstrip(":")
        value_text = detail_cells[1].get_text(" ", strip=True)
        current[key_text] = value_text
    return entries


def render_eu_tire_label_html(entries: List[Dict[str, str]]) -> Optional[str]:
    if not entries:
        return None
    html_parts = [
        "<table>",
        "<thead><tr><th>Category</th><th>Position</th><th>Value</th></tr></thead>",
        "<tbody>",
    ]
    for entry in entries:
        label = entry.get("label", "")
        for key, value in entry.items():
            if key == "label" or not value:
                continue
            html_parts.append(
                f"<tr><td>{label}</td><td>{key}</td><td>{value}</td></tr>"
            )
    html_parts.append("</tbody></table>")
    return "".join(html_parts)


def parse_product_information(soup: BeautifulSoup) -> List[Dict[str, str]]:
    sections: List[Dict[str, str]] = []
    for container in soup.select(".accordion__container"):
        title_elem = container.select_one(".accordion__btn")
        panel = container.select_one(".accordion__panel")
        if not panel:
            continue
        title = title_elem.get_text(strip=True) if title_elem else ""
        text_content = panel.get_text("\n", strip=True)
        html_content = panel.decode_contents().strip()
        sections.append(
            {
                "title": title,
                "text": text_content,
                "html": html_content,
            }
        )
    return sections


def parse_images(soup: BeautifulSoup) -> Dict[str, Any]:
    image_entries: List[Dict[str, Optional[str]]] = []
    seen = set()
    for img_wrapper in soup.select(".image--element"):
        entry = {
            "small": img_wrapper.get("data-img-small"),
            "large": img_wrapper.get("data-img-large"),
            "original": img_wrapper.get("data-img-original"),
            "alt": img_wrapper.get("data-alt"),
        }
        img_tag = img_wrapper.select_one("img")
        if img_tag:
            entry["src"] = img_tag.get("src")
            entry["srcset"] = img_tag.get("srcset")
        key = tuple(entry.get(field) for field in ("small", "large", "original", "src"))
        if key in seen:
            continue
        seen.add(key)
        primary_url = (
            entry.get("original")
            or entry.get("large")
            or entry.get("small")
            or entry.get("src")
        )
        if primary_url:
            entry["primary"] = primary_url
        image_entries.append(entry)
    # Fallback to OpenGraph image if gallery empty
    if not image_entries:
        og_image = soup.select_one("meta[property='og:image']")
        if og_image and og_image.get("content"):
            image_entries.append({"original": og_image["content"], "primary": og_image["content"]})
    return {
        "count": len(image_entries),
        "gallery": image_entries,
    }


def parse_documents(soup: BeautifulSoup) -> List[Dict[str, str]]:
    documents: List[Dict[str, str]] = []
    seen_urls = set()
    for block in soup.select(".ac--multimedia [data-media-url]"):
        url = block.get("data-media-url")
        label = block.get_text(strip=True)
        if url and url not in seen_urls:
            seen_urls.add(url)
            documents.append({"url": url, "label": label})
    for link in soup.select(".ac--multimedia a[href]"):
        href = link.get("href")
        if not href:
            continue
        url = urljoin("https://www.ac-schnitzer.de", href)
        if url in seen_urls:
            continue
        seen_urls.add(url)
        documents.append({"url": url, "label": link.get_text(strip=True)})
    return documents


def parse_manufacturer_info(soup: BeautifulSoup) -> Optional[str]:
    address_block = soup.select_one(".ac--questions__address")
    return element_text(address_block, separator="\n")


def build_description_content(
    product_information: List[Dict[str, str]],
    eu_tire_label_html: Optional[str],
    documents: List[Dict[str, str]],
    manufacturer_info: Optional[str],
    product_url: str,
) -> Dict[str, Optional[str]]:
    short_html: Optional[str] = None
    short_text: Optional[str] = None
    sections_html: List[str] = []

    for section in product_information:
        title = section.get("title")
        section_html = (section.get("html") or "").strip()
        section_text = section.get("text") or ""
        if not section_html and section_text:
            section_html = text_to_html(section_text)
        if not short_html and section_html:
            short_html = section_html
            short_text = section_text or None
        if title:
            sections_html.append(f"<h3>{title}</h3>")
        if section_html:
            sections_html.append(section_html)

    if eu_tire_label_html:
        sections_html.append("<h3>EU Tire Label</h3>")
        sections_html.append(eu_tire_label_html)

    doc_items: List[str] = []
    for doc in documents:
        url = doc.get("url")
        label = doc.get("label") or url
        if not url:
            continue
        doc_items.append(f'<li><a href="{url}">{label}</a></li>')
    if doc_items:
        sections_html.append("<h3>Documentation</h3>")
        sections_html.append(f"<ul>{''.join(doc_items)}</ul>")

    if manufacturer_info:
        sections_html.append("<h3>Manufacturer Information</h3>")
        sections_html.append(text_to_html(manufacturer_info))

    if product_url:
        sections_html.append(
            f'<p><a href="{product_url}">Original AC Schnitzer listing</a></p>'
        )

    full_html = "\n".join(sections_html).strip()

    return {
        "short_html": short_html or None,
        "short_text": short_text,
        "full_html": full_html or None,
    }


def parse_variations(soup: BeautifulSoup) -> List[Dict[str, Any]]:
    variations: List[Dict[str, Any]] = []
    configurator = soup.select_one(".configurator--variant")
    if not configurator:
        return variations
    
    # Extract variant groups from the configurator
    variant_groups = configurator.select(".variant--group")
    for group in variant_groups:
        # Get the variant name (e.g., "Size", "Color", "Brand")
        name_elem = group.select_one(".variant--name")
        if not name_elem:
            continue
        variant_name = name_elem.get_text(strip=True)
        
        # Extract all variant options from radio inputs and labels
        options = []
        option_labels = group.select(".variant--option label.radio-label")
        for label in option_labels:
            option_text = label.get_text(strip=True)
            if option_text:
                options.append(option_text)
        
        # Only add if we found options
        if options:
            variations.append(
                {
                    "name": variant_name,
                    "options": options,
                }
            )
    
    return variations


def parse_product_page(html: str, url: str, brand: str) -> Dict[str, Any]:
    soup = BeautifulSoup(html, "lxml")
    title_elem = soup.select_one(".product--title")
    title = title_elem.get_text(strip=True) if title_elem else None

    tail_number_elem = soup.select_one("[itemprop='tail_number']")
    sku_elem = soup.select_one("[itemprop='sku']")
    product_id_elem = soup.select_one("meta[itemprop='productID']")

    price = parse_price(soup)
    availability = parse_availability(soup)
    mounting = parse_mounting_time(soup)
    breadcrumbs = parse_breadcrumbs(soup)
    product_info = parse_product_information(soup)
    category_path = derive_category_path(url)
    documents = parse_documents(soup)
    manufacturer_info = parse_manufacturer_info(soup)
    eu_tire_label_entries = parse_eu_tire_label(soup)
    eu_tire_label_html = render_eu_tire_label_html(eu_tire_label_entries)
    descriptions = build_description_content(
        product_information=product_info,
        eu_tire_label_html=eu_tire_label_html,
        documents=documents,
        manufacturer_info=manufacturer_info,
        product_url=url,
    )
    images = parse_images(soup)
    image_urls = [entry.get("primary") for entry in images["gallery"] if entry.get("primary")]
    ac_document_text = element_text(soup.select_one(".ac--document"))
    variations = parse_variations(soup)
    og_price_meta = soup.select_one("meta[property='product:price']")
    og_currency_meta = soup.select_one("meta[property='product:price:currency']")
    og_url_meta = soup.select_one("meta[property='product:product_link']")

    return {
        "brand": brand,
        "url": url,
        "title": title,
        "breadcrumbs": breadcrumbs,
        "category_path": category_path,
        "part_number": tail_number_elem.get_text(strip=True) if tail_number_elem else None,
        "sku": sku_elem.get_text(strip=True) if sku_elem else None,
        "product_id": product_id_elem.get("content") if product_id_elem else None,
        "price": price,
        "availability": availability,
        "mounting_time": mounting,
        "descriptions": descriptions,
        "product_information": product_info,
        "images": images,
        "image_urls": image_urls,
        "documents": documents,
        "document_urls": [doc["url"] for doc in documents if doc.get("url")],
        "manufacturer_info": manufacturer_info,
        "ac_document": ac_document_text,
        "eu_tire_label": eu_tire_label_entries,
        "variations": variations,
        "meta": {
            "scraped_at": datetime.utcnow().isoformat(),
            "price_meta": {
                "og_price": og_price_meta.get("content") if og_price_meta else None,
                "og_currency": og_currency_meta.get("content") if og_currency_meta else None,
                "og_product_url": og_url_meta.get("content") if og_url_meta else None,
            },
            "eu_tire_label_html": eu_tire_label_html,
        },
    }


def update_output_structure(output: Dict[str, Any]) -> None:
    products = output.get("products", {})
    brand_counts = {brand: len(items) for brand, items in products.items()}
    total_products = sum(brand_counts.values())
    output["meta"]["generated_at"] = datetime.utcnow().isoformat()
    output["meta"]["total_products"] = total_products
    output["meta"]["brand_counts"] = brand_counts


def save_output(file_path: Path, output: Dict[str, Any]) -> None:
    update_output_structure(output)
    with file_path.open("w", encoding="utf-8") as fp:
        json.dump(output, fp, indent=2)
    console.print(
        Panel(
            f"Saved product details to [bold]{file_path.name}[/bold]",
            border_style="green",
        )
    )


def iterate_links(
    links_by_brand: Dict[str, List[str]],
    brands: List[str],
    offset: int,
    limit: Optional[int],
) -> List[Dict[str, Any]]:
    queue: List[Dict[str, Any]] = []
    remaining = limit if limit is not None else None
    for brand in brands:
        urls = links_by_brand.get(brand, [])
        start_idx = min(offset, len(urls)) if offset > 0 else 0
        for url in urls[start_idx:]:
            queue.append({"brand": brand, "url": url})
            if remaining is not None:
                remaining -= 1
                if remaining <= 0:
                    return queue
    return queue


def scrape_products(
    links_by_brand: Dict[str, List[str]],
    brands: List[str],
    max_links: Optional[int],
    offset: int,
    delay: float,
    output_file: Path = OUTPUT_FILE,
) -> None:
    output = init_output(output_file)
    products = output.setdefault("products", {})

    tasks = iterate_links(links_by_brand, brands, offset, max_links)
    total_tasks = len(tasks)
    if total_tasks == 0:
        console.print("[yellow]No links to scrape with the current settings.[/yellow]")
        return

    console.print(Panel(f"Preparing to scrape {total_tasks} product pages", border_style="cyan"))

    errors: List[str] = []
    start_time = time.perf_counter()

    with requests.Session() as session:
        session.headers.update(DEFAULT_HEADERS)
        with Progress(
            SpinnerColumn(),
            TextColumn("{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task_id = progress.add_task("Scraping products", total=total_tasks)

            for item in tasks:
                brand = item["brand"]
                url = item["url"]
                progress.update(task_id, description=f"{brand.upper()} :: {url}")
                try:
                    html = fetch_page(session, url, delay)
                    product_data = parse_product_page(html, url, brand)
                    products.setdefault(brand, {})[url] = product_data
                except Exception as exc:  # pylint: disable=broad-except
                    error_msg = f"{brand}:{url} -> {exc}"
                    console.print(f"    [red]Failed to scrape {url}: {exc}[/red]")
                    errors.append(error_msg)
                finally:
                    progress.advance(task_id)

    elapsed = time.perf_counter() - start_time
    elapsed = time.perf_counter() - start_time
    save_output(output_file, output)

    console.print(
        Panel(
            f"Completed in {elapsed:.1f}s. Scraped {total_tasks - len(errors)} of {total_tasks} pages.",
            border_style="blue",
        )
    )

    if errors:
        error_table = "\n".join(errors[:10])
        console.print(
            Panel(
                f"Encountered {len(errors)} errors (showing up to 10):\n{error_table}",
                border_style="red",
            )
        )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Scrape AC Schnitzer product details")
    parser.add_argument(
        "--brands",
        nargs="+",
        help="Brands to scrape (default: all brands found in product_links.json)",
    )
    parser.add_argument(
        "--max",
        type=int,
        default=None,
        help="Maximum number of product links to scrape in total (default: all)",
    )
    parser.add_argument(
        "--offset",
        type=int,
        default=0,
        help="Number of links to skip per brand before scraping (default: 0)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=DEFAULT_DELAY,
        help=f"Delay between requests in seconds (default: {DEFAULT_DELAY})",
    )
    parser.add_argument(
        "--input_links",
        type=Path,
        default=PRODUCT_LINKS_FILE,
        help="Path to the input links JSON file (default: product_links.json)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=OUTPUT_FILE,
        help="Path to the output JSON file (default: product_details.json)",
    )
    return parser


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()

    parser = build_arg_parser()
    args = parser.parse_args()

    links_by_brand = load_links(args.input_links)
    available_brands = sorted(links_by_brand.keys())

    if args.brands:
        requested_brands = [brand.lower() for brand in args.brands]
        invalid = sorted(set(requested_brands) - set(available_brands))
        if invalid:
            raise ValueError(f"Unknown brands requested: {', '.join(invalid)}")
        selected_brands = requested_brands
    else:
        selected_brands = available_brands

    console.print(
        Panel(
            "\n".join(
                [
                    "Scraping configuration:",
                    f"  Brands      : {', '.join(b.upper() for b in selected_brands)}",
                    f"  Max links   : {args.max if args.max is not None else 'ALL'}",
                    f"  Offset      : {args.offset}",
                    f"  Delay (s)   : {args.delay}",
                ]
            ),
            border_style="magenta",
        )
    )

    scrape_products(
        links_by_brand=links_by_brand,
        brands=selected_brands,
        max_links=args.max,
        offset=args.offset,
        delay=max(args.delay, 0.0),
        output_file=args.output,
    )


if __name__ == "__main__":
    main()
