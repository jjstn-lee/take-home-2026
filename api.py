# As per instructions, API only has a single route. 
#
# To avoid eating through credits during testing, I also implement a "cache". To test the same HTML file multiple times,
# you need to delete the 'cache.json' file in /data.

from contextlib import asynccontextmanager
from pathlib import Path
import asyncio
import json
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from models import Product
import hydrator
import categorizer
import image_finder

# Shared state for the application
app_state = {"html_content": None, "html_files": {}, "products": None}

# Cache configuration
CACHE_PATH = Path("./data/cache.json")

def load_cache() -> list[Product] | None:
    """Return cached products if cache file exists, else None."""
    if not CACHE_PATH.exists():
        return None
    try:
        cached_data = json.loads(CACHE_PATH.read_text())
        products = [Product.model_validate(p) for p in cached_data]
        return products if products else None
    except Exception as e:
        print(f"Warning: Failed to load cache: {e}")
        return None


def save_cache(products: list[Product]) -> None:
    """Write hydrated products to disk as JSON."""
    CACHE_PATH.write_text(json.dumps([p.model_dump() for p in products]))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load HTML files at startup and clean up at shutdown."""
    # Startup

    # Always load HTML files
    html_path = Path("./data/adaysmarch.html")
    if html_path.exists():
        app_state["html_content"] = html_path.read_text(encoding="utf-8")
    else:
        raise FileNotFoundError(f"HTML file not found: {html_path}")

    # Load all HTML files from data directory for catalog
    data_dir = Path("./data")
    html_files = {}
    for html_file in sorted(data_dir.glob("*.html")):
        if html_file.name != "adaysmarch.html-CLEAN.html":  # Skip cleaned files
            html_files[html_file.stem] = html_file.read_text(encoding="utf-8")
    app_state["html_files"] = html_files

    # Try to load from cache if available
    cached = load_cache()
    if cached:
        print(f"Loaded {len(cached)} products from cache")
        app_state["products"] = cached

    yield

    # Shutdown
    app_state["html_content"] = None
    app_state["html_files"] = {}
    app_state["products"] = None

app = FastAPI(lifespan=lifespan)

# Add CORS middleware for frontend development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5174", "http://localhost:5175"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

async def process_product_pipeline(html_text: str) -> Product:
    """Run the full product hydration pipeline on HTML text."""
    # Step 1: Extract from JSON-LD
    product = await hydrator.hydrate_from_json_ld(html_text)

    # If JSON-LD extraction failed, create a minimal product
    if product is None:
        product = Product(
            name="",
            price={"price": 0.0, "currency": "USD"},
            description="",
            key_features=[],
            image_urls=[],
            category={"name": ""},
            brand="",
            options={}
        )

    # Save JSON-LD images before Step 2 (which overwrites them)
    json_ld_images = list(product.image_urls)
    print(f"[API] Step 1: JSON-LD extracted {len(json_ld_images)} images")

    # Step 2: Hydrate with LLM
    product = await hydrator.hydrate_product(product, html_text)
    print(f"[API] Step 2: After hydration, product has {len(product.image_urls)} images")

    # Step 3: Categorize
    product = await categorizer.categorize(product)

    # Step 4: Build candidate image list (JSON-LD first, then regex-extracted)
    regex_images = image_finder.find_images(html_text)
    print(f"[API] Step 4a: Regex extracted {len(regex_images)} images")
    candidates = list(dict.fromkeys(json_ld_images + regex_images))  # deduplicate, JSON-LD first
    print(f"[API] Step 4b: Candidate list has {len(candidates)} unique images")

    # Step 5: LLM filter to extract actual product images
    filtered_images = await image_finder.find_images(product, candidates, html_text)
    print(f"[API] Step 5: image_finder returned {len(filtered_images)} images")
    product.image_urls = filtered_images

    print(f"[API] Final product has {len(product.image_urls)} images")
    return product

@app.get("/products", response_model=list[Product])
async def get_products():
    """Run the product hydration pipeline for HTML files concurrently and return list of products.

    Uses cache if available.
    """
    # Check if products are cached
    if app_state["products"]:
        print("Returning products from cache")
        return app_state["products"]

    html_files = app_state["html_files"]
    if not html_files:
        return []

    # Process HTML files concurrently
    tasks = [process_product_pipeline(html_text) for html_text in html_files.values()]
    products = await asyncio.gather(*tasks)

    # Persist to disk and store in memory
    save_cache(list(products))
    app_state["products"] = list(products)

    # Debug: print products
    print(f"\n=== GET /products returning {len(products)} products (from pipeline) ===")
    for i, product in enumerate(products):
        print(f"Product {i+1}: {product.name} | Brand: {product.brand} | Images: {len(product.image_urls)}")
    print("=" * 50 + "\n")

    return products


@app.delete("/products/cache")
async def clear_cache():
    """Clear the cache to force re-hydration on next request."""
    if CACHE_PATH.exists():
        CACHE_PATH.unlink()
    app_state["products"] = None
    return {"message": "Cache cleared"}
