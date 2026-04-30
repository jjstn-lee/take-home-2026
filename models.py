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
        if v not in VALID_CATEGORIES:
            raise ValueError(f"Category '{v}' is not a valid category in categories.txt")
        return v

class Price(BaseModel):
    price: float
    currency: str
    # If a product is on sale, this is the original price
    compare_at_price: float | None = None

# I do my best to not modify the Product schema (and Price and Category schemas). Any changes are commented on below.
class Product(BaseModel):
    name: str
    price: Price
    description: str
    key_features: list[str]
    image_urls: list[str]                           # Grabbing image URLs and ensuring they're paired with is difficult and expensive, especially without computer vision.
                                                    # Thus, I simply decided to grab all product images but not the variant they're supposed to be.
    video_url: str | None = None
    category: Category
    brand: str
    # variants: list[Variant]               # TODO (@dev): Define variant model
    
    # Discerning variants may not be fully possible from raw HTML alone on SSR websites. So,
    # I use the Cartesian product as an upper bound on possible variants. It is important
    # to note that valid variants would actually be a subset of this.
    
    # Implementing a variant model is unnecessary. Instead, we can keep track of the options and calculate the
    # Cartesian product later. This also helps us to call the LLM less frequently.
    options: dict[str, list[str]] = {}      # e.g., {"color": ["Red", "Blue", "Green"], "size": ["S", "M", "L"]}