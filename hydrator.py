# Hydrator is the core of this project. The goal was to hydrate the Product via deterministic methods as much as possible, and then use LLMs
# to finish the process. As such, I try to parse the JSON-LD to partially hydrate the Product schema before handing it off to an LLM. A future
# optimization might be to implement more deterministic methods based on stack/platform (i.e, Next.js, Shopify)
# 
# Initially, I wanted to be able to 'one-shot' PDPs (1 LLM call per page), as it was important to me that I was efficient with the credits that
# I was given. Though it turned out to be incredibly difficult and I needed to abstract functionality away, it helped me identify what the Hydrator
# could and could not able to do with its given context (categorizer.py, image_finder.py)

from pathlib import Path
import asyncio
from pydantic import BaseModel
from bs4 import BeautifulSoup
import json
import re
import os

import ai
from models import Product, Price, Offer
from bs4 import BeautifulSoup

def clean_html_for_llm(html_text: str) -> str:
    """
    Clean HTML by removing structural chrome and non-essential attributes.
    Preserves product content and form elements that might contain variants.
    """

    soup = BeautifulSoup(html_text, 'html.parser')

    # Structural/chrome elements are not important to the LLM and shouldn't include anything about the
    # product, so we clean them here.
    chrome_selectors = [
        'nav', 'header', 'footer', 'aside',
        'style', 'noscript',
        'iframe', 'meta', 'link',
        'button[onclick]',  # Tracking buttons
        '.nav', '.navbar', '.header', '.footer', '.sidebar', '.ads', '.ad',
        '.advertisement', '.comments', '.related-products',
        '[role="navigation"]', '[role="sidebar"]',
        'svg'  # Remove svg but keep img tags so LLM can extract image URLs
    ]

    for selector in chrome_selectors:
        for elem in soup.select(selector):
            elem.decompose()

    # Remove scripts but preserve JSON-LD
    for script in soup.find_all('script'):
        if script.get('type') != 'application/ld+json':
            script.decompose()

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

    # Extract price information and variant offers from offers
    extracted_offers = []
    all_prices = []
    has_sale = False

    if 'offers' in json_ld_data:
        offers_data = json_ld_data['offers']

        # Handle AggregateOffer with nested offers
        if isinstance(offers_data, dict) and offers_data.get('@type') == 'AggregateOffer':
            # Look for nested offers list inside AggregateOffer
            if 'offers' in offers_data:
                offers_data = offers_data['offers']

        # Normalize to list
        if isinstance(offers_data, dict):
            offers_data = [offers_data]

        if isinstance(offers_data, list) and len(offers_data) > 0:
            # Process each offer
            for offer in offers_data:
                if isinstance(offer, dict):
                    price_value = offer.get('price')
                    currency = offer.get('priceCurrency', 'USD')
                    availability = offer.get('availability')

                    # Strip schema.org URL prefix if present (e.g. "http://schema.org/InStock" -> "InStock")
                    if availability and '/' in availability:
                        availability = availability.split('/')[-1]

                    # Extract variant options from additionalProperty array
                    variant_options = {}
                    if 'additionalProperty' in offer and isinstance(offer['additionalProperty'], list):
                        for prop in offer['additionalProperty']:
                            if isinstance(prop, dict) and prop.get('@type') == 'PropertyValue':
                                name = prop.get('name')
                                value = prop.get('value')
                                if name and value:
                                    variant_options[name] = str(value)

                    # Also check for variant info in offer name (e.g. "Black / M")
                    if not variant_options and 'name' in offer:
                        offer_name = offer.get('name', '')
                        # Simple heuristic: split by '/' to detect variant patterns
                        if '/' in offer_name:
                            parts = [p.strip() for p in offer_name.split('/')]
                            # If looks like variant (2+ parts), store it
                            if len(parts) >= 2:
                                # Try to infer which part is which
                                variant_options['variant'] = offer_name

                    # Extract price info
                    if price_value is not None:
                        try:
                            price_float = float(price_value)
                            all_prices.append(price_float)

                            # Check if there's a sale price indication
                            original_price = None
                            if 'priceValidUntil' in offer:
                                # Presence of priceValidUntil suggests a sale/limited offer
                                original_price = None  # Mark as potential sale

                            # Create Offer instance for variant tracking
                            offer_obj = Offer(
                                price=price_float,
                                currency=currency,
                                original_price=original_price,
                                options=variant_options,
                                availability=availability
                            )
                            extracted_offers.append(offer_obj)
                        except (ValueError, TypeError):
                            pass

            # Set top-level price from cheapest offer (or first if no availability info)
            if all_prices:
                top_price = min(all_prices)
                product_data['price'] = Price(
                    price=top_price,
                    currency='USD'
                )

            # Store extracted offers
            if extracted_offers:
                product_data['offers'] = extracted_offers

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
        # Use a sentinel value (999.99) instead of 0 to indicate "price not found"
        # This prevents returning $0 products and makes it clear to LLM to fill it in
        product_data['price'] = Price(price=999.99, currency='USD')
    if 'offers' not in product_data:
        product_data['offers'] = []
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


async def hydrate_product_with_llm(product: Product, html_text: str) -> Product:
    """Use LLM to fully hydrate a partially-filled Product instance from HTML."""
    # Clean the HTML to remove noise and reduce tokens
    cleaned_html = clean_html_for_llm(html_text)
    # Limit the size to stay within token budget
    if len(cleaned_html) > 15000:
        cleaned_html = cleaned_html[:15000]


    prompt = f"""You are analyzing the HTML source of an e-commerce product page and a partially hydrated instance of
    a product schema. Complete/fill in all missing information in the Product schema using the HTML.

    IMPORTANT:
    - Return ALL required fields, even if empty. Use null for missing optional fields.
    - If category is missing, leave the field EMPTY.
    - If you only find the list of key features, then you may generate a 1-4 sentence description.
    - Product images have already been extracted and should NOT be included in your response.

    Return ONLY a valid JSON object with ALL of these fields:
    - name: product name (string)
    - price: object with "price" (number), "currency" (string), and "original_price" (float)
    - description: product description (string)
    - key_features: list of 3-5 key features (list of strings)
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
            "openai/gpt-3.5-turbo",
            [{"role": "user", "content": prompt}]
        )

        # Extract the JSON from the Response object
        output_text = None

        # The Responses API returns output_text directly
        if hasattr(response, 'output_text') and response.output_text:
            output_text = response.output_text
        # Fallback to parsing output items
        elif hasattr(response, 'output') and response.output:
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

        # Clean markdown code blocks if present
        output_text = output_text.strip()
        if output_text.startswith('```json'):
            output_text = output_text[7:]  # Remove ```json
        elif output_text.startswith('```'):
            output_text = output_text[3:]  # Remove ```
        if output_text.endswith('```'):
            output_text = output_text[:-3]  # Remove trailing ```
        output_text = output_text.strip()

        response_json = json.loads(output_text)

        # Leave as empty - Image_Finder will find the images.
        response_json['image_urls'] = []
        
        # Validate price - if missing/null/zero, keep original from partial product
        price_value = response_json.get('price')
        if not price_value or (isinstance(price_value, dict) and price_value.get('price', 0) == 0):
            # Preserve the partially-extracted price (from JSON-LD or sentinel value)
            response_json['price'] = {
                'price': product.price.price,
                'currency': product.price.currency,
                'original_price': product.price.original_price
            }

        # Convert the JSON response to a Product instance
        hydrated = Product(**response_json)

        return hydrated

    except Exception as e:
        print(f"ERROR extracting product data: {e}")
        import traceback
        traceback.print_exc()
        # Return the original product with its existing price (don't return a potentially $0 product)
        return product


async def hydrate_product(product: Product, html_text: str) -> Product:
    """
    Fully hydrate a partially-filled Product instance using HTML.
    Uses LLM extraction to complete all missing fields.
    """
    return await hydrate_product_with_llm(product, html_text)

# async def test_hydrate_product_file(html_file: Path):
#     """Test hydrating a Product from an HTML file."""
#     html_text = html_file.read_text(encoding="utf-8")

#     # Try to extract from JSON-LD first
#     partial_product = await hydrate_from_json_ld(html_text)

#     # If JSON-LD extraction failed, create a minimal product
#     if partial_product is None:
#         print(f"No JSON-LD data found, starting with minimal product...")
#         partial_product = Product(
#             name="",
#             price={"price": 0.0, "currency": "USD"},
#             description="",
#             key_features=[],
#             image_urls=[],
#             category={"name": "Apparel & Accessories"},
#             brand="",
#             options={}
#         )
#     else:
#         print(f"Found JSON-LD data, starting with semi-hydrated product...")

#     print(f"partial product:\n{partial_product}")
    
#     print(f"Hydrating product from {html_file.name}...")
#     hydrated_product = await hydrate_product(partial_product, html_text)

#     print(f"\nHydrated Product:")
#     print(f"  Name: {hydrated_product.name}")
#     print(f"  Brand: {hydrated_product.brand}")
#     print(f"  Price: {hydrated_product.price}")
#     print(f"  Category: {hydrated_product.category}")
#     print(f"  Description: {hydrated_product.description[:100]}...")
#     print(f"  Key Features: {hydrated_product.key_features}")
#     print(f"  Images: {len(hydrated_product.image_urls)} found")
#     print(f"  Options: {hydrated_product.options}")