from pathlib import Path
import asyncio
from pydantic import BaseModel
from bs4 import BeautifulSoup
import json
import re
import os

import ai
from models import Product


def clean_html_for_llm(html_text: str) -> str:
    """
    Clean HTML by removing structural chrome and non-essential attributes.
    Preserves product content and form elements that might contain variants.
    """

    # Image URLs are large and not semantically important to the LLM, but they are a requirement in the
    # project. So, we process them first.
    image_urls = []
    url_pattern = r'https://[^"\s<>]+\.(?:jpg|jpeg|png|webp|gif)'
    for match in re.finditer(url_pattern, html_text):
        url = match.group(0)
        # Filter to likely product image URLs (not tracking pixels, etc)
        if not any(x in url.lower() for x in ['px', 'pixel', 'tracking', '1x1', '0x0']):
            image_urls.append(url)

    soup = BeautifulSoup(html_text, 'html.parser')

    # Structural/chrome elements are not important to the LLM and shouldn't include anything about the
    # product, so we clean them here.
    chrome_selectors = [
        'nav', 'header', 'footer', 'aside',
        'script', 'style', 'noscript',
        'iframe', 'meta', 'link',
        'button[onclick]',  # Tracking buttons
        '.nav', '.navbar', '.header', '.footer', '.sidebar', '.ads', '.ad',
        '.advertisement', '.comments', '.related-products',
        '[role="navigation"]', '[role="sidebar"]',
        'svg', 'img'  # Remove images to reduce noise
    ]

    for selector in chrome_selectors:
        for elem in soup.select(selector):
            elem.decompose()

    # Keep text content and semantically important tags
    keep_tags = {'html', 'body', 'main', 'section', 'article', 'div', 'p', 'span',
                 'form', 'select', 'option', 'input', 'label', 'button', 'textarea',
                 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'ul', 'ol', 'li', 'table',
                 'tr', 'td', 'th', 'a', 'strong', 'em', 'b', 'i'}

    # Keep attributes that might help identify variants, and remove noise like style/class
    keep_attrs = {'name', 'value', 'type', 'for', 'placeholder', 'aria-label', 'title'}

    # Remove all elements not in keep_tags
    for elem in soup.find_all(True):
        if elem.name not in keep_tags:
            # Keep the text content but remove the tag wrapper
            elem.unwrap()
        else:
            # Strip unwanted attributes
            attrs_to_remove = [attr for attr in elem.attrs if attr not in keep_attrs]
            for attr in attrs_to_remove:
                del elem[attr]

    cleaned = str(soup)

    # Remove excessive whitespace
    cleaned = '\n'.join(line.strip() for line in cleaned.split('\n') if line.strip())

    # FIXME: just a hack for now; gonna figure out a cleaner way to keep track of image urls when i'm not so sleepy
    # Append extracted image URLs as a comment for the LLM to find
    if image_urls:
        unique_urls = list(dict.fromkeys(image_urls))  # Remove duplicates, preserve order
        cleaned += '\n\n<!-- Product Image URLs -->\n'
        for url in unique_urls[:20]:  # Limit to first 20 images
            cleaned += f'<!-- {url} -->\n'

    return cleaned


async def hydrate_from_json_ld(html_text: str) -> Product | None:
    """
    Extract and map JSON-LD structured data to a semi-hydrated Product schema.
    Returns a Product instance with available fields populated from JSON-LD,
    or None if no JSON-LD found or extraction fails.
    """
    soup = BeautifulSoup(html_text, 'html.parser')
    script_tag = soup.find('script', type='application/ld+json')

    if not script_tag:
        return None

    try:
        json_ld_data = json.loads(script_tag.string)
    except (json.JSONDecodeError, TypeError):
        return None

    # Map JSON-LD Product schema fields to Product model
    product_data = {}

    # Extract basic fields
    if 'name' in json_ld_data:
        product_data['name'] = json_ld_data['name']

    if 'description' in json_ld_data:
        product_data['description'] = json_ld_data['description']

    if 'brand' in json_ld_data:
        brand = json_ld_data['brand']
        # Handle brand as either string or object with 'name' field
        if isinstance(brand, dict) and 'name' in brand:
            product_data['brand'] = brand['name']
        elif isinstance(brand, str):
            product_data['brand'] = brand

    # Extract price information
    if 'offers' in json_ld_data:
        offers = json_ld_data['offers']
        if isinstance(offers, list) and len(offers) > 0:
            offers = offers[0]
        if isinstance(offers, dict):
            price_value = offers.get('price')
            currency = offers.get('priceCurrency', 'USD')
            if price_value is not None:
                try:
                    product_data['price'] = {
                        'price': float(price_value),
                        'currency': currency
                    }
                except (ValueError, TypeError):
                    pass

    # Extract image URLs
    if 'image' in json_ld_data:
        images = json_ld_data['image']
        if isinstance(images, str):
            product_data['image_urls'] = [images]
        elif isinstance(images, list):
            product_data['image_urls'] = [img if isinstance(img, str) else img.get('url', '') for img in images if img]

    # Extract category - try to find in schema but may need LLM for taxonomy validation
    if 'category' in json_ld_data:
        category_name = json_ld_data['category']
        if isinstance(category_name, dict):
            category_name = category_name.get('name', category_name.get('name', ''))
        product_data['category'] = {'name': str(category_name)} if category_name else None

    # Set default values for required fields if not found
    if 'name' not in product_data:
        product_data['name'] = ''
    if 'description' not in product_data:
        product_data['description'] = ''
    if 'brand' not in product_data:
        product_data['brand'] = ''
    if 'price' not in product_data:
        product_data['price'] = {'price': 0.0, 'currency': 'USD'}
    if 'image_urls' not in product_data:
        product_data['image_urls'] = []
    if 'category' not in product_data or product_data['category'] is None:
        product_data['category'] = {'name': 'Apparel & Accessories'}
    if 'key_features' not in product_data:
        product_data['key_features'] = []
    if 'options' not in product_data:
        product_data['options'] = {}

    try:
        return Product(**product_data)
    except Exception:
        # If schema validation fails, return None to fall back to LLM
        return None


async def extract_variants_with_llm(product: Product, html_text: str) -> Product:
    """Use LLM to fully hydrate a partially-filled Product instance from HTML."""
    # Clean the HTML first to remove noise and reduce tokens
    cleaned_html = clean_html_for_llm(html_text)

    # Limit the size to stay within token budget
    if len(cleaned_html) > 15000:
        cleaned_html = cleaned_html[:15000]

    prompt = f"""You are analyzing the HTML source of an e-commerce product page and a partially hydrated instance of
    a product schema. Complete/fill in all missing information in the Product schema using the HTML.

    IMPORTANT:
    - Look for image URLs in HTML comments marked as "<!-- URL -->".
    - Return ALL required fields, even if empty. Use null for missing optional fields.
    - If category is missing, infer from product type and use a valid Google Product Taxonomy category.

    Return ONLY a valid JSON object with ALL of these fields:
    - name: product name (string)
    - price: object with "price" (number) and "currency" (string)
    - description: product description (string)
    - key_features: list of 3-5 key features (list of strings)
    - image_urls: list of all product image URLs (list of strings)
    - video_url: null or video URL string
    - category: object with "name" field (Google Product Taxonomy category string)
    - brand: brand name (string)
    - options: dict with color/size/etc as keys, lists of values (dict)

    Example:
    {{
        "name": "Adidas Ultraboost",
        "price": {{"price": 149.99, "currency": "USD"}},
        "description": "Running shoe with boost cushioning",
        "key_features": ["boost cushioning", "responsive", "lightweight", "durable outsole"],
        "image_urls": ["https://example.com/1.jpg", "https://example.com/2.jpg"],
        "video_url": null,
        "category": {{"name": "Shoes"}},
        "brand": "Adidas",
        "options": {{"color": ["Black", "White"], "size": ["7", "8", "9"]}}
    }}

    Current partial Product:
    {product}

    HTML:
    {cleaned_html}"""

    try:
        response = await ai.responses(
            "openai/gpt-5-nano",
            [{"role": "user", "content": prompt}]
        )

        # Extract the JSON from the Response object
        output_text = None
        if hasattr(response, 'output') and response.output:
            # It's an OpenAI Response object with output messages
            for item in response.output:
                # Skip reasoning items, look for message items with content
                if hasattr(item, 'content') and item.content:
                    for content_block in item.content:
                        if hasattr(content_block, 'text'):
                            output_text = content_block.text
                            break
                if output_text:
                    break

        if not output_text:
            raise ValueError("Could not extract text from response")

        response_json = json.loads(output_text)

        # Convert the JSON response to a Product instance
        hydrated = Product(**response_json)
        return hydrated

    except Exception as e:
        print(f"ERROR extracting product data: {e}")
        import traceback
        traceback.print_exc()
        return product


async def hydrate_product(product: Product, html_text: str) -> Product:
    """
    Fully hydrate a partially-filled Product instance using HTML.
    Uses LLM extraction to complete all missing fields.
    """
    return await extract_variants_with_llm(product, html_text)

async def test_hydrate_product_file(html_file: Path):
    """Test hydrating a Product from an HTML file."""
    html_text = html_file.read_text(encoding="utf-8")

    # Try to extract from JSON-LD first
    partial_product = await hydrate_from_json_ld(html_text)

    # If JSON-LD extraction failed, create a minimal product
    if partial_product is None:
        print(f"No JSON-LD data found, starting with minimal product...")
        partial_product = Product(
            name="",
            price={"price": 0.0, "currency": "USD"},
            description="",
            key_features=[],
            image_urls=[],
            category={"name": "Apparel & Accessories"},
            brand="",
            options={}
        )
    else:
        print(f"Found JSON-LD data, starting with semi-hydrated product...")

    print(f"partial product:\n{partial_product}")
    
    print(f"Hydrating product from {html_file.name}...")
    hydrated_product = await hydrate_product(partial_product, html_text)

    print(f"\nHydrated Product:")
    print(f"  Name: {hydrated_product.name}")
    print(f"  Brand: {hydrated_product.brand}")
    print(f"  Price: {hydrated_product.price}")
    print(f"  Category: {hydrated_product.category}")
    print(f"  Description: {hydrated_product.description[:100]}...")
    print(f"  Key Features: {hydrated_product.key_features}")
    print(f"  Images: {len(hydrated_product.image_urls)} found")
    print(f"  Options: {hydrated_product.options}")


if __name__ == "__main__":
    import sys

    # if len(sys.argv) > 1:
    #     html_file = sys.argv[1]
    #     html_path = Path(f"./data/{html_file}")
    # else:
    #     # Test all HTML files
    #     html_files = [
    #         "adaysmarch.html",
    #         "nike.html",
    #         "llbean.html",
    #         "acehardware.html",
    #         "article.html"
    #     ]
    #     for html_file in html_files:
    #         html_path = Path(f"./data/{html_file}")
    #         if not html_path.exists():
    #             print(f"⚠️  {html_file} not found, skipping")
    #             continue
    #         print(f"\n{'='*70}")
    #         asyncio.run(test_hydrate_product_file(html_path))
    #     sys.exit(0)
        
    html_path = Path(f"./data/adaysmarch.html")
    asyncio.run(test_hydrate_product_file(html_path))

    if html_path.exists():
        asyncio.run(test_hydrate_product_file(html_path))
    else:
        print(f"File not found: {html_path}")