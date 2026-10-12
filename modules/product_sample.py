"""
product_sample.py - The products a run reports: a stratified sample, not the first N in crawl order.

Each collection page contributes at most `per_collection` products it has not already seen, and so do
the homepage's own product cards and the Shopify products.json feed (one source each). A product page
contributes its one product. The total is capped at `total` (max_products). Without the per-source
cap the first collection of a big store filled the whole sample, and the price range was that one
collection's.
"""

from typing import Dict, List

from .product_extractor import product_key

# page_type -> key in summary(); product pages are not capped per source
SOURCE_KINDS = {'collection': 'collections', 'home': 'homepage', 'feed': 'feed', 'product': 'product_pages'}


class ProductSample:
    def __init__(self, total: int, per_collection: int):
        self.total = max(int(total), 0)
        self.per_collection = max(int(per_collection), 1)
        self.products: List = []
        self._keys = set()
        self._by_source: Dict[str, int] = {}
        self._kind_of: Dict[str, str] = {}

    @property
    def full(self) -> bool:
        return len(self.products) >= self.total

    def has(self, url: str) -> bool:
        return product_key(url) in self._keys

    def add(self, products, source: str, kind: str) -> List:
        """Take the products of one source (a page URL) in page order; returns the ones taken."""
        cap = None if kind == 'product' else self.per_collection
        taken = []
        for p in products:
            if self.full or (cap is not None and len(taken) >= cap):
                break
            key = product_key(p.url)
            if key in self._keys:
                continue
            self._keys.add(key)
            self.products.append(p)
            taken.append(p)
        if taken:
            self._by_source[source] = self._by_source.get(source, 0) + len(taken)
            self._kind_of[source] = kind
        return taken

    def summary(self) -> Dict[str, int]:
        """products, per_collection, and per kind: collections (pages that contributed), homepage /
        feed (products taken from them), product_pages (pages that contributed)."""
        out = {'products': len(self.products), 'collections': 0, 'per_collection': self.per_collection,
               'homepage': 0, 'product_pages': 0, 'feed': 0}
        for source, n in self._by_source.items():
            kind = self._kind_of[source]
            if kind in ('collection', 'product'):
                out[SOURCE_KINDS[kind]] += 1
            else:
                out[SOURCE_KINDS[kind]] += n
        return out


TEXT = {
    'en': {'none': "no products found", 'lead': "{n} products from {parts}",
           'collections': "{c} collections (at most {per} per collection)",
           'collection': "1 collection (at most {per} per collection)",
           'homepage': "the homepage ({h})", 'feed': "products.json ({f})",
           'product_pages': "{p} product pages", 'product_page': "1 product page",
           'sep': ", ", 'last': " and "},
    'zh': {'none': "未找到产品", 'lead': "{n}个产品，来自{parts}",
           'collections': "{c}个产品集合（每个最多{per}个）", 'collection': "1个产品集合（每个最多{per}个）",
           'homepage': "首页（{h}个）", 'feed': "products.json（{f}个）",
           'product_pages': "{p}个产品页", 'product_page': "1个产品页",
           'sep': "、", 'last': "和"},
}


def describe(summary: Dict[str, int], language: str = 'en') -> str:
    """'32 products from 3 collections (at most 10 per collection), the homepage (2) and 4 product
    pages' (or the Chinese equivalent)."""
    t = TEXT.get(language, TEXT['en'])
    if not summary or not summary.get('products'):
        return t['none']
    per = summary.get('per_collection')
    parts = []
    c, p = summary.get('collections', 0), summary.get('product_pages', 0)
    if c:
        parts.append((t['collection'] if c == 1 else t['collections']).format(c=c, per=per))
    if summary.get('homepage'):
        parts.append(t['homepage'].format(h=summary['homepage']))
    if summary.get('feed'):
        parts.append(t['feed'].format(f=summary['feed']))
    if p:
        parts.append((t['product_page'] if p == 1 else t['product_pages']).format(p=p))
    joined = parts[0] if len(parts) == 1 else t['sep'].join(parts[:-1]) + t['last'] + parts[-1]
    return t['lead'].format(n=summary['products'], parts=joined)
