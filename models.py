# I try to keep this file untouched wherever possible.

from typing import Any
from pathlib import Path
from pydantic import BaseModel, field_validator

# Load categories once at module level
CATEGORIES_FILE = Path(__file__).parent / "categories.txt"
VALID_CATEGORIES = set()
if CATEGORIES_FILE.exists():
    with open(CATEGORIES_FILE, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                VALID_CATEGORIES.add(line)

class Category(BaseModel):
    # A category from Google's Product Taxonomy
    # https://www.google.com/basepages/producttype/taxonomy.en-US.txt
    name: str

    @field_validator("name")
    @classmethod
    def validate_name_exists(cls, v: str) -> str:
        # First check if it's an exact match
        if v in VALID_CATEGORIES:
            return v

        # If not exact match, check if it's a valid hierarchical path
        if any(valid.startswith(v) or valid.endswith(v) or v in valid for valid in VALID_CATEGORIES):
            return v

        # If still not found, accept it anyway as a fallback but mark it as incorrect
        return v + "(INVALID CATEGORY)"

# CHANGES: changed the name of price and deleted compare_at_price
class Price(BaseModel):
    price: float # changed naming
    currency: str
    original_price: float | None = None  # set if item is on sale

class Offer(BaseModel):
    price: float
    currency: str
    original_price: float | None = None   # pre-sale price, if discounted
    options: dict[str, str] = {}          # e.g. {"color": "Black", "size": "M"}
    availability: str | None = None       # e.g. "InStock", "OutOfStock"
    
# I do my best to not modify the Product schema (and Price and Category schemas). Any changes are commented on.
class Product(BaseModel):
    name: str
    price: Price
    description: str
    offers: list[Offer] = []  # per-variant offers; empty if no variant pricing
    key_features: list[str]
    image_urls: list[str]                           # Grabbing image URLs and ensuring they're paired with is difficult and expensive, especially without computer vision.
                                                    # Thus, I simply decided to grab all product images but not the variant they're supposed to be.
    video_url: str | None = None
    category: Category
    brand: str
    # variants: list[Variant]               # TODO (@dev): Define variant model
    
    # Discerning variants may not be fully possible from raw HTML alone on SSR websites.
    # So, I use the Cartesian product as an upper bound on possible variants. It is important
    # to note that valid variants would actually be a subset of this.
    
    # Implementing a variant model is unnecessary, even if in the future we wanted to keep track of which images line up
    # with which variants. Instead, we can keep track of the options and calculate the Cartesian product later. This would
    # also help us to call the LLM less frequently.
    options: dict[str, list[str]] = {}      # e.g., {"color": ["Red", "Blue", "Green"], "size": ["S", "M", "L"]}