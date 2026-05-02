# Image_Finder is responsible for finding relevant images according to structure of HTML and product schema. This
# is something that Hydrator could not complete because the list of URLs would eat through context.
#
# Ideally, instead of trying to decipher relevant images from the structure of the HTML file,
# this would have a web-scraping (i.e, Selenium) + computer vision solution. 

from models import Product
import ai
import json
import re
from bs4 import BeautifulSoup

def find_images(html_text: str) -> list[str]:
    image_urls = []
    # Match http://, https://, and protocol-relative // URLs with various image extensions
    url_pattern = r'(?:https?:|)//[^\s"<>]+\.(?:jpg|jpeg|png|webp|gif|svg)'

    for match in re.finditer(url_pattern, html_text):
        url = match.group(0)
        # Normalize protocol-relative URLs to https://
        if url.startswith('//'):
            url = 'https:' + url
        # Filter to likely product image URLs (not tracking pixels, etc)
        if not any(x in url.lower() for x in ['px', 'pixel', 'tracking', '1x1', '0x0']):
            image_urls.append(url)

    unique_urls = list(dict.fromkeys(image_urls))
    return unique_urls

def clean_html_for_image_finding(html_text: str) -> str:
    """
    Clean HTML for image finding by removing structural chrome while preserving images.
    Images are kept to provide context about which images belong to the product.
    """
    soup = BeautifulSoup(html_text, 'html.parser')

    # Structural/chrome elements to remove (same as hydrator, but excluding 'img')
    chrome_selectors = [
        'nav', 'header', 'footer', 'aside',
        'style', 'noscript',
        'iframe', 'meta', 'link',
        'button[onclick]',  # Tracking buttons
        '.nav', '.navbar', '.header', '.footer', '.sidebar', '.ads', '.ad',
        '.advertisement', '.comments', '.related-products',
        '[role="navigation"]', '[role="sidebar"]',
        'svg'  # Remove SVG but keep img tags
    ]

    for selector in chrome_selectors:
        for elem in soup.select(selector):
            elem.decompose()

    # Remove scripts but preserve JSON-LD
    for script in soup.find_all('script'):
        if script.get('type') != 'application/ld+json':
            script.decompose()

    # Keep text content and semantically important tags, including img
    keep_tags = {'html', 'body', 'main', 'section', 'article', 'div', 'p', 'span',
                 'form', 'select', 'option', 'input', 'label', 'button', 'textarea',
                 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'ul', 'ol', 'li', 'table',
                 'tr', 'td', 'th', 'a', 'strong', 'em', 'b', 'i', 'img'}

    # Keep attributes needed for identifying images and variants
    keep_attrs = {'name', 'value', 'type', 'for', 'placeholder', 'aria-label', 'title', 'src', 'alt', 'class'}

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


async def find_images(product: Product, image_urls: list[str], html_text: str) -> list[str]:
    # Cap images to avoid token limit - prioritize unique domains
    capped_urls = image_urls[:50] if len(image_urls) > 50 else image_urls

    # Clean HTML to preserve images but remove structural noise
    cleaned_html = clean_html_for_image_finding(html_text)

    # Limit HTML size to stay within token budget
    if len(cleaned_html) > 10000:
        cleaned_html = cleaned_html[:10000]

    prompt = f"""You are finding relevant product images from a list.

    Filter URLs to only include product images (not thumbnails, navigation, ads, logos).

    Rules:
    - Include: hero images, product photos, variant angles
    - Exclude: thumbnails, navigation, logos, icons, banners
    - Deduplicate: Keep only 1 per image (prefer _large, _max, full over _thumb, _sm)

    Product:
    Name: {product.name}
    Brand: {product.brand}

    Image URLs to filter:
    {json.dumps(capped_urls)}

    Return only a JSON array: ["url1", "url2"]
    """

    try:
        response = await ai.responses(
            "openai/gpt-3.5-turbo",
            [{"role": "user", "content": prompt}]
        )

        # Extract text from OpenAI Responses API
        response_text = None

        # The Responses API returns output_text directly
        if hasattr(response, 'output_text') and response.output_text:
            response_text = response.output_text
        # Fallback to parsing output items
        elif hasattr(response, 'output') and response.output:
            for item in response.output:
                if hasattr(item, 'content') and item.content:
                    for content_block in item.content:
                        if hasattr(content_block, 'text'):
                            response_text = content_block.text
                            break
                if response_text:
                    break

        if not response_text:
            raise ValueError("Could not extract text from response")

        # Clean up the response (remove markdown code blocks if present)
        response_text = response_text.strip()
        if response_text.startswith('```json'):
            response_text = response_text[7:]
        if response_text.startswith('```'):
            response_text = response_text[3:]
        if response_text.endswith('```'):
            response_text = response_text[:-3]
        response_text = response_text.strip()

        filtered_urls = json.loads(response_text)

        if not isinstance(filtered_urls, list):
            print(f"Expected list of URLs, got {type(filtered_urls)}")
            return image_urls

        return filtered_urls

    except Exception as e:
        print(f"ERROR filtering images: {e}")
        import traceback
        traceback.print_exc()
        return image_urls