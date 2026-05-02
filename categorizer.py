# Categorizer needs to be able to categorize the Product, but it is expensive to pass in the .txt of valid categories. And even then,
# there is no guarantee that the agent would categorize the Product into a valid category. So, I chose to augment the categorizer
# with semantic search and fuzzy matching. 

from models import Product, Category, VALID_CATEGORIES
import ai
from sentence_transformers import SentenceTransformer, util
from difflib import get_close_matches
import torch

# Load embedding model once at module level
MODEL = SentenceTransformer('all-MiniLM-L6-v2')

# Pre-compute embeddings for all valid categories at startup
CATEGORY_LIST = sorted(list(VALID_CATEGORIES))
CATEGORY_EMBEDDINGS = MODEL.encode(CATEGORY_LIST, convert_to_tensor=True)

def find_candidate_categories(product: Product, top_k: int = 15) -> list[str]:
    """Use semantic search to find the most likely valid categories for this product."""
    # Create a search query from product info
    query = f"{product.name} {product.brand} {product.description}"

    # Encode the query
    query_embedding = MODEL.encode(query, convert_to_tensor=True)

    # Find top-k most similar categories using cosine similarity
    # Use a slightly higher k to give LLM more options to choose from
    cos_scores = util.cos_sim(query_embedding, CATEGORY_EMBEDDINGS)[0]
    top_results = torch.topk(cos_scores, k=min(top_k, len(CATEGORY_LIST)))

    # Extract the top candidate categories
    candidates = [CATEGORY_LIST[idx] for idx in top_results.indices]
    return candidates


def fuzzy_match_category(category_str: str, threshold: float = 0.6) -> str | None:
    """Use fuzzy matching to find the closest valid category."""
    matches = get_close_matches(
        category_str,
        CATEGORY_LIST,
        n=1,
        cutoff=threshold
    )
    return matches[0] if matches else None


async def categorize(product: Product, max_retries: int = 3):
    """Categorize product using semantic search pre-filtering + LLM + fuzzy matching."""

    for attempt in range(max_retries):
        try:
            # Step 1: Semantic search to find candidate categories
            candidate_categories = find_candidate_categories(product, top_k=15)

            # Step 1b: Rerank candidates to de-prioritize misleading categories
            # If product name contains pants/trousers/shorts keywords,
            # deprioritize underwear categories
            product_text_lower = f"{product.name} {product.brand}".lower()
            pants_keywords = ['pant', 'trouser', 'short', 'jean', 'khaki', 'cargo', 'chino']
            underwear_keywords = ['underwear', 'long john', 'thermal', 'base layer']

            is_pants_product = any(kw in product_text_lower for kw in pants_keywords)

            if is_pants_product:
                # Move underwear categories to the end
                reranked = [c for c in candidate_categories if not any(uw in c.lower() for uw in underwear_keywords)]
                reranked += [c for c in candidate_categories if any(uw in c.lower() for uw in underwear_keywords)]
                candidate_categories = reranked

            print(f"DEBUG: Candidate categories for '{product.name}' (reranked):")
            for i, cat in enumerate(candidate_categories[:5]):
                print(f"  {i+1}. {cat}")

            candidates_text = "\n".join(candidate_categories)

            # Create a compact product representation without huge image list
            product_info = f"""Name: {product.name}
            Brand: {product.brand}
            Description: {product.description}
            Key Features: {', '.join(product.key_features[:3])}  # Limit to first 3"""

            prompt = f"""You are analyzing a product and must assign it to ONE of the provided categories.

            IMPORTANT:
            - You must return ONLY ONE category from the list below - do not invent categories.
            - Return just the category name, nothing else - no explanation or additional text.
            - Choose the MOST SPECIFIC category that best matches the product.
            - For clothing items: consider the primary garment type (pants, shirts, dresses, etc) over subcategories like underwear or activewear unless explicitly indicated.
            - If multiple categories seem equally applicable, choose the broadest/most general category.

            VALID CATEGORIES (choose from these only):
            {candidates_text}

            Product Information:
            {product_info}

            Return only the category name:"""

            response = await ai.responses(
                "openai/gpt-3.5-turbo",
                [{"role": "user", "content": prompt}]
            )

            # Extract category string from response
            output_text = None

            # The Responses API returns output_text directly
            if hasattr(response, 'output_text') and response.output_text:
                output_text = response.output_text
            # Fallback to parsing output items
            elif hasattr(response, 'output') and response.output:
                for item in response.output:
                    if hasattr(item, 'content') and item.content:
                        for content_block in item.content:
                            if hasattr(content_block, 'text'):
                                output_text = content_block.text
                                break
                    if output_text:
                        break

            if not output_text:
                raise ValueError("Could not extract text from response")

            category_str = output_text.strip()
            print(f"DEBUG: LLM returned category: '{category_str}'")

            # Step 2: Validate that the category is in the valid list
            if category_str in VALID_CATEGORIES:
                print(f"✓ Category matched: {category_str}")
                category = Category(name=category_str)
                product.category = category
                return product

            # Step 3: Fuzzy match to nearest valid category
            fuzzy_match = fuzzy_match_category(category_str, threshold=0.5)
            if fuzzy_match:
                print(f"~ Fuzzy matched '{category_str}' → '{fuzzy_match}'")
                category = Category(name=fuzzy_match)
                product.category = category
                return product

            # If neither worked, try again with different query
            if attempt < max_retries - 1:
                print(f"✗ Invalid category '{category_str}', retrying... (attempt {attempt + 1}/{max_retries})")
                continue
            else:
                # Last resort: pick the top semantic match
                top_match = candidate_categories[0]
                print(f"! Last resort: assigning top semantic match '{top_match}'")
                category = Category(name=top_match)
                product.category = category
                return product

        except Exception as e:
            if attempt == max_retries - 1:
                print(f"ERROR categorizing the product after {max_retries} attempts: {e}")
                import traceback
                traceback.print_exc()
                # Fallback to top semantic match
                try:
                    candidate_categories = find_candidate_categories(product, top_k=1)
                    category = Category(name=candidate_categories[0])
                    product.category = category
                except:
                    pass
                return product
            else:
                print(f"Attempt {attempt + 1} failed: {e}, retrying...")

    return product
