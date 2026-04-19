"""
scraper.py
==========
TDS Onion site scraper — all 12 tasks.
Uses SOCKS5 proxy via Tor on 127.0.0.1:9050.
"""

import requests
import re
import time
from bs4 import BeautifulSoup

BASE = "http://tds26vu3ptapxx6igo6n26kuwfpn2l5omkmagc4hc7g7yn2o3xb25syd.onion"

PROXIES = {
    "http":  "socks5h://127.0.0.1:9050",
    "https": "socks5h://127.0.0.1:9050",
}


class TDSScraper:

    def __init__(self, log_fn=print, delay=0.5):
        self.log = log_fn
        self.delay = delay
        self.sess = requests.Session()
        self.sess.proxies = PROXIES
        self.sess.headers["User-Agent"] = (
            "Mozilla/5.0 (Windows NT 10.0; rv:109.0) Gecko/20100101 Firefox/115.0"
        )

    # ─── HTTP ──────────────────────────────────────────────────────────────────

    def _get(self, url, retries=5):
        for attempt in range(retries):
            try:
                r = self.sess.get(url, timeout=40)
                r.raise_for_status()
                time.sleep(self.delay)
                return r
            except Exception as e:
                wait = 2 ** attempt
                self.log(f"  Retry {attempt+1}/{retries} [{url[-40:]}]: {e} — wait {wait}s", "warn")
                time.sleep(wait)
        raise RuntimeError(f"All {retries} retries failed for: {url}")

    def _soup(self, url):
        return BeautifulSoup(self._get(url).text, "lxml")

    def _full(self, href):
        if not href:
            return None
        href = href.strip()
        return href if href.startswith("http") else BASE + href

    # ─── Pagination ────────────────────────────────────────────────────────────

    def _next_page(self, s, current):
        """Return next page URL or None."""
        # Try rel=next and common 'Next' link patterns
        for sel in [
            "a[rel='next']", "a.next", "li.next > a",
            ".pagination a:last-child", ".pager-next a",
            "a:contains('Next')", "a:contains('»')", "a:contains('›')",
        ]:
            try:
                el = s.select_one(sel)
                if el and el.get("href"):
                    nxt = self._full(el["href"])
                    if nxt and nxt != current:
                        return nxt
            except Exception:
                pass

        # Try ?page= increment
        m = re.search(r"[?&]page=(\d+)", current)
        if m:
            pg = int(m.group(1))
            nxt = re.sub(r"([?&]page=)\d+", f"\\g<1>{pg+1}", current)
            try:
                r = self.sess.get(nxt, timeout=15)
                if r.status_code == 200 and r.url != current and len(r.text) > 500:
                    return nxt
            except Exception:
                pass
        else:
            # Try appending ?page=2
            sep = "&" if "?" in current else "?"
            nxt = current + sep + "page=2"
            try:
                r = self.sess.get(nxt, timeout=15)
                if r.status_code == 200 and len(r.text) > 500:
                    test_s = BeautifulSoup(r.text, "lxml")
                    # Only use if it has actual content links
                    if len(test_s.find_all("a", href=True)) > 5:
                        return nxt
            except Exception:
                pass
        return None

    def _paginate(self, start):
        """Yield (soup, url) for every page."""
        url, seen = start, set()
        while url and url not in seen:
            seen.add(url)
            s = self._soup(url)
            yield s, url
            url = self._next_page(s, url)

    # ─── Number utils ──────────────────────────────────────────────────────────

    @staticmethod
    def _f(text):
        """Extract first float."""
        if not text:
            return 0.0
        text = str(text).replace(",", "").replace("$", "").strip()
        m = re.search(r"\d+\.?\d*", text)
        return float(m.group()) if m else 0.0

    @staticmethod
    def _i(text):
        """Extract first int."""
        if not text:
            return 0
        m = re.search(r"\d+", str(text).replace(",", ""))
        return int(m.group()) if m else 0

    # ─── URL discovery ─────────────────────────────────────────────────────────

    def _find_url(self, patterns, label):
        """Try a list of URL patterns, return first that returns 200."""
        for path in patterns:
            url = BASE + path
            try:
                r = self.sess.get(url, timeout=12)
                if r.status_code == 200 and len(r.text) > 200:
                    self.log(f"  Found {label} at {path}", "ok")
                    return url
            except Exception:
                pass
        raise RuntimeError(f"Cannot find URL for '{label}'. Tried: {patterns}")

    # ─── Link collectors ───────────────────────────────────────────────────────

    def _product_links(self, cat_url):
        links = set()
        for s, url in self._paginate(cat_url):
            for a in s.find_all("a", href=True):
                h = a["href"]
                if any(x in h for x in ["/product/", "/products/", "/item/", "/p/"]):
                    full = self._full(h)
                    if full:
                        links.add(full)
            # Fallback: linked cards
            for el in s.select(".product a, .item a, .card a, h2 > a, h3 > a"):
                h = el.get("href", "")
                if h and h != cat_url and h != "/":
                    full = self._full(h)
                    if full:
                        links.add(full)
            self.log(f"    {len(links)} product links collected")
        return list(links)

    def _article_links(self, cat_url):
        links = set()
        for s, url in self._paginate(cat_url):
            for a in s.find_all("a", href=True):
                h = a["href"]
                full = self._full(h)
                if full and full != cat_url and any(
                    x in h for x in ["/article/", "/news/", "/post/", "/story/", "/blog/"]
                ):
                    links.add(full)
            for el in s.select(".article a, .post a, .news-item a, h2 > a, h3 > a"):
                h = el.get("href", "")
                full = self._full(h)
                if full and full != cat_url:
                    links.add(full)
            self.log(f"    {len(links)} article links collected")
        return list(links)

    def _user_links(self, users_url):
        links = set()
        for s, url in self._paginate(users_url):
            for a in s.find_all("a", href=True):
                h = a["href"]
                if any(x in h for x in ["/user/", "/profile/", "/u/", "/member/"]):
                    full = self._full(h)
                    if full and full != users_url:
                        links.add(full)
            self.log(f"    {len(links)} user links collected")
        return list(links)

    def _post_links(self, posts_url):
        links = set()
        for s, url in self._paginate(posts_url):
            for a in s.find_all("a", href=True):
                h = a["href"]
                if any(x in h for x in ["/post/", "/p/", "/status/", "/feed/"]):
                    full = self._full(h)
                    if full and full != posts_url:
                        links.add(full)
            for el in s.select(".post a, .feed-item a, h2 > a, h3 > a"):
                h = el.get("href", "")
                full = self._full(h)
                if full and full != posts_url:
                    links.add(full)
            self.log(f"    {len(links)} post links collected")
        return list(links)

    def _thread_links(self, board_url):
        links = set()
        for s, url in self._paginate(board_url):
            for a in s.find_all("a", href=True):
                h = a["href"]
                if any(x in h for x in ["/thread/", "/topic/", "/t/", "/discussion/"]):
                    full = self._full(h)
                    if full and full != board_url:
                        links.add(full)
            self.log(f"    {len(links)} thread links collected")
        return list(links)

    # ─── Page scrapers ─────────────────────────────────────────────────────────

    def _scrape_product(self, url):
        s = self._soup(url)
        t = s.get_text(" ", strip=True)

        # Price
        price = 0.0
        for el in s.find_all(attrs={"data-price": True}):
            price = self._f(el["data-price"])
            if price: break
        if not price:
            for sel in [".current-price", ".price", "[class*='price']", "[itemprop='price']"]:
                el = s.select_one(sel)
                if el:
                    price = self._f(el.get("content") or el.get("data-price") or el.get_text())
                    if price: break
        if not price:
            m = re.search(r"\$\s*([\d,]+\.?\d*)", t)
            if m: price = float(m.group(1).replace(",", ""))

        # Stock
        stock = 0
        for el in s.find_all(attrs={"data-stock": True}):
            stock = self._i(el["data-stock"])
            if stock is not None: break
        if not stock:
            for sel in [".stock", "[class*='stock']", "[class*='inventory']", "[class*='qty']"]:
                el = s.select_one(sel)
                if el:
                    stock = self._i(el.get("data-stock") or el.get_text())
                    if stock: break
        if not stock:
            m = re.search(r"(?:stock|quantity|qty)[:\s]+(\d+)", t, re.I)
            if m: stock = int(m.group(1))

        # SKU
        sku = ""
        for el in s.find_all(attrs={"data-sku": True}):
            sku = el["data-sku"].strip()
            if sku: break
        if not sku:
            for sel in [".sku", "[class*='sku']", "[itemprop='sku']"]:
                el = s.select_one(sel)
                if el:
                    sku = el.get("content") or el.get("data-sku") or el.get_text(strip=True)
                    if sku: break
        if not sku:
            m = re.search(r"SKU[:\s#]*([A-Z0-9][A-Z0-9\-]{2,})", t, re.I)
            if m: sku = m.group(1)

        # Reviews
        reviews = 0
        for el in s.find_all(attrs={"data-reviews": True}):
            reviews = self._i(el["data-reviews"])
            if reviews: break
        if not reviews:
            for sel in ["[class*='review-count']", "[class*='reviews']", ".review-count"]:
                el = s.select_one(sel)
                if el:
                    reviews = self._i(el.get("data-reviews") or el.get_text())
                    if reviews: break
        if not reviews:
            m = re.search(r"(\d+)\s+review", t, re.I)
            if m: reviews = int(m.group(1))

        # Rating
        rating = 0.0
        for el in s.find_all(attrs={"data-rating": True}):
            rating = self._f(el["data-rating"])
            if rating: break
        if not rating:
            for sel in ["[class*='rating']", ".stars", "[itemprop='ratingValue']"]:
                el = s.select_one(sel)
                if el:
                    rating = self._f(el.get("content") or el.get("data-rating") or el.get_text())
                    if rating: break
        if not rating:
            m = re.search(r"([\d.]+)\s*/\s*5", t)
            if m: rating = float(m.group(1))

        # Status
        oos = bool(re.search(r"out[\s_-]*of[\s_-]*stock", t, re.I))

        return {"price": price, "stock": stock, "sku": sku,
                "reviews": reviews, "rating": rating, "oos": oos}

    def _scrape_article(self, url):
        s = self._soup(url)
        t = s.get_text(" ", strip=True)

        # Internal views — search EVERY element's attributes
        internal_views = 0
        for el in s.find_all(True):
            v = el.get("data-internal-views")
            if v is not None:
                internal_views = self._i(v)
                break

        # Author
        author = ""
        for el in s.find_all(attrs={"data-author": True}):
            author = el["data-author"].strip()
            if author: break
        if not author:
            for sel in [".author", "[class*='author']", "[rel='author']",
                        ".byline", "[itemprop='author']", ".writer"]:
                el = s.select_one(sel)
                if el:
                    author = el.get("content") or el.get_text(strip=True)
                    if author: break
        if not author:
            m = re.search(r"[Bb]y\s+([A-Z][a-z]+(?: [A-Z][a-z]+)+)", t)
            if m: author = m.group(1)

        return {"internal_views": internal_views, "author": author}

    def _scrape_user(self, url):
        s = self._soup(url)
        t = s.get_text(" ", strip=True)

        # Verified
        verified = False
        for el in s.find_all(True):
            cls = " ".join(el.get("class", []))
            dv = el.get("data-verified", "")
            if "verified" in cls.lower() or dv in ["true", "1", "yes"]:
                verified = True
                break
        if not verified:
            # Look for verified symbol/text near username
            verified = bool(re.search(r"\bverified\b", t, re.I))

        # Followers
        followers = 0
        for el in s.find_all(attrs={"data-followers": True}):
            followers = self._i(el["data-followers"])
            break
        if not followers:
            for sel in ["[class*='follower']", ".followers", "[class*='follow-count']"]:
                el = s.select_one(sel)
                if el:
                    followers = self._i(el.get("data-followers") or el.get_text())
                    if followers: break
        if not followers:
            m = re.search(r"([\d,]+)\s+followers?", t, re.I)
            if m: followers = int(m.group(1).replace(",", ""))

        # Location
        location = ""
        for el in s.find_all(attrs={"data-location": True}):
            location = el["data-location"].strip()
            break
        if not location:
            for sel in ["[class*='location']", ".location", "[itemprop='addressLocality']"]:
                el = s.select_one(sel)
                if el:
                    location = el.get("content") or el.get_text(strip=True)
                    if location: break
        if not location:
            m = re.search(r"[Ll]ocation[:\s]+([^\n<,]{3,50})", t)
            if m: location = m.group(1).strip()

        return {"verified": verified, "followers": followers, "location": location}

    def _scrape_post(self, url):
        s = self._soup(url)
        t = s.get_text(" ", strip=True)

        hashtags = [h.lower() for h in re.findall(r"#\w+", t)]

        likes = 0
        for el in s.find_all(attrs={"data-likes": True}):
            likes = self._i(el["data-likes"])
            break
        if not likes:
            for sel in ["[class*='like-count']", ".likes", "[class*='likes']"]:
                el = s.select_one(sel)
                if el:
                    likes = self._i(el.get("data-likes") or el.get_text())
                    if likes: break
        if not likes:
            m = re.search(r"([\d,]+)\s+likes?", t, re.I)
            if m: likes = int(m.group(1).replace(",", ""))

        return {"hashtags": hashtags, "likes": likes}

    def _scrape_forum_user(self, url):
        s = self._soup(url)
        t = s.get_text(" ", strip=True)

        # Reputation
        rep = 0
        for el in s.find_all(attrs={"data-reputation": True}):
            rep = self._i(el["data-reputation"])
            break
        if not rep:
            for sel in ["[class*='reputation']", ".reputation", ".rep", "[data-rep]"]:
                el = s.select_one(sel)
                if el:
                    rep = self._i(el.get("data-reputation") or el.get("data-rep") or el.get_text())
                    if rep: break
        if not rep:
            m = re.search(r"[Rr]eputation[:\s]+([\d,]+)", t)
            if m: rep = int(m.group(1).replace(",", ""))

        # Join date
        joined = ""
        for el in s.find_all(attrs={"data-joined": True}):
            joined = el["data-joined"].strip()
            break
        if not joined:
            for sel in ["[class*='joined']", ".join-date", ".member-since",
                        "[class*='registered']", "[class*='join']", "time"]:
                el = s.select_one(sel)
                if el:
                    joined = (el.get("datetime") or el.get("data-joined")
                              or el.get_text(strip=True))
                    if joined: break
        if not joined:
            m = re.search(
                r"[Jj]oined[:\s]+([A-Za-z]+ \d{4}|\d{4}-\d{2}-\d{2}|\d{2}[/-]\d{2}[/-]\d{4})",
                t,
            )
            if m: joined = m.group(1)

        # Badges
        badges = []
        for el in s.select(
            ".badge, [class*='badge'], .flair, .role-tag, .user-badge, .rank, [class*='rank']"
        ):
            txt = el.get_text(strip=True)
            if txt and len(txt) < 40:
                badges.append(txt)
        for el in s.find_all(attrs={"data-badge": True}):
            badges.append(el["data-badge"])

        return {"reputation": rep, "joined": joined, "badges": list(set(badges))}

    def _scrape_thread(self, url):
        s = self._soup(url)
        t = s.get_text(" ", strip=True)

        for el in s.find_all(attrs={"data-replies": True}):
            return self._i(el["data-replies"])

        for sel in ["[class*='reply-count']", ".replies", "[class*='post-count']"]:
            el = s.select_one(sel)
            if el:
                return self._i(el.get("data-replies") or el.get_text())

        # Count reply posts minus 1 OP
        posts = s.select(".post, .reply, [class*='message'][class*='reply']")
        if len(posts) > 1:
            return len(posts) - 1

        m = re.search(r"(\d+)\s+repli", t, re.I)
        if m: return int(m.group(1))
        return 0

    # ─── Category URL finders ──────────────────────────────────────────────────

    def _ecom_url(self, cat):
        return self._find_url([
            f"/category/{cat}", f"/categories/{cat}",
            f"/shop/{cat}", f"/store/{cat}", f"/{cat}",
            f"/products?category={cat}", f"/products/{cat}",
        ], f"e-commerce/{cat}")

    def _news_url(self, cat):
        return self._find_url([
            f"/news/{cat}", f"/articles/{cat}", f"/blog/{cat}",
            f"/category/{cat}", f"/news?category={cat}",
        ], f"news/{cat}")

    def _social_url(self, path):
        return self._find_url([
            f"/{path}", f"/social/{path}", f"/platform/{path}",
        ], f"social/{path}")

    def _forum_url(self, path):
        return self._find_url([
            f"/forum/{path}", f"/board/{path}", f"/{path}",
            f"/forums/{path}", f"/community/{path}", f"/discussion/{path}",
        ], f"forum/{path}")

    # ══════════════════════════════════════════════════════════════════════════
    # RUN ALL 12 TASKS
    # ══════════════════════════════════════════════════════════════════════════

    def run_all(self, progress_cb=None):
        """
        Scrape all 12 tasks.
        progress_cb(task_num, answer) called after each task completes.
        Returns dict {"task1": ..., "task2": ..., ...}
        """
        results = {}

        def done(n, val):
            results[f"task{n}"] = str(val)
            self.log(f"✓ TASK {n} = {val}", "ok")
            if progress_cb:
                progress_cb(n, str(val))

        def fail(n, e):
            results[f"task{n}"] = f"ERROR: {e}"
            self.log(f"✗ TASK {n} failed: {e}", "err")
            if progress_cb:
                progress_cb(n, f"ERROR: {e}")

        # ── Task 1: Apparel total inventory value ─────────────────────────────
        self.log("━━ Task 1: Apparel inventory value")
        try:
            url = self._ecom_url("apparel")
            links = self._product_links(url)
            self.log(f"  Scraping {len(links)} products...")
            total = 0.0
            for i, u in enumerate(links, 1):
                p = self._scrape_product(u)
                v = p["price"] * p["stock"]
                total += v
                self.log(f"  [{i}/{len(links)}] ${p['price']} × {p['stock']} = {v:.2f}")
            done(1, f"{total:.2f}")
        except Exception as e:
            fail(1, e)

        # ── Task 2: Outdoors SKU with most reviews ────────────────────────────
        self.log("━━ Task 2: Outdoors top-review SKU")
        try:
            url = self._ecom_url("outdoors")
            links = self._product_links(url)
            best_sku, best_rev = "", 0
            for i, u in enumerate(links, 1):
                p = self._scrape_product(u)
                if p["reviews"] > best_rev:
                    best_rev, best_sku = p["reviews"], p["sku"]
                self.log(f"  [{i}/{len(links)}] SKU={p['sku']} reviews={p['reviews']}")
            done(2, best_sku)
        except Exception as e:
            fail(2, e)

        # ── Task 3: Outdoors OOS average rating ───────────────────────────────
        self.log("━━ Task 3: Outdoors OOS avg rating")
        try:
            url = self._ecom_url("outdoors")
            links = self._product_links(url)
            ratings = []
            for i, u in enumerate(links, 1):
                p = self._scrape_product(u)
                if p["oos"]:
                    ratings.append(p["rating"])
                self.log(f"  [{i}/{len(links)}] oos={p['oos']} rating={p['rating']}")
            avg = sum(ratings) / len(ratings) if ratings else 0
            done(3, f"{avg:.2f}")
        except Exception as e:
            fail(3, e)

        # ── Task 4: Tech total internal views ─────────────────────────────────
        self.log("━━ Task 4: Tech total internal views")
        try:
            url = self._news_url("tech")
            links = self._article_links(url)
            total = 0
            for i, u in enumerate(links, 1):
                a = self._scrape_article(u)
                total += a["internal_views"]
                self.log(f"  [{i}/{len(links)}] views={a['internal_views']} total={total}")
            done(4, total)
        except Exception as e:
            fail(4, e)

        # ── Task 5: Sports — Michael Clayton article count ────────────────────
        self.log("━━ Task 5: Michael Clayton sports articles")
        try:
            url = self._news_url("sports")
            links = self._article_links(url)
            count = 0
            for i, u in enumerate(links, 1):
                a = self._scrape_article(u)
                match = "michael clayton" in a["author"].lower()
                if match: count += 1
                self.log(f"  [{i}/{len(links)}] '{a['author']}' {'← MATCH' if match else ''}")
            done(5, count)
        except Exception as e:
            fail(5, e)

        # ── Task 6: Politics avg internal views ───────────────────────────────
        self.log("━━ Task 6: Politics avg internal views")
        try:
            url = self._news_url("politics")
            links = self._article_links(url)
            views = []
            for i, u in enumerate(links, 1):
                a = self._scrape_article(u)
                views.append(a["internal_views"])
                self.log(f"  [{i}/{len(links)}] views={a['internal_views']}")
            avg = round(sum(views) / len(views)) if views else 0
            done(6, avg)
        except Exception as e:
            fail(6, e)

        # ── Task 7: Verified users total followers ────────────────────────────
        self.log("━━ Task 7: Verified users total followers")
        try:
            url = self._social_url("users")
            links = self._user_links(url)
            total = 0
            for i, u in enumerate(links, 1):
                usr = self._scrape_user(u)
                if usr["verified"]: total += usr["followers"]
                self.log(f"  [{i}/{len(links)}] verified={usr['verified']} followers={usr['followers']}")
            done(7, total)
        except Exception as e:
            fail(7, e)

        # ── Task 8: #coffee posts total likes ─────────────────────────────────
        self.log("━━ Task 8: #coffee posts total likes")
        try:
            url = self._social_url("posts")
            links = self._post_links(url)
            total = 0
            for i, u in enumerate(links, 1):
                post = self._scrape_post(u)
                has = "#coffee" in post["hashtags"]
                if has: total += post["likes"]
                self.log(f"  [{i}/{len(links)}] #coffee={has} likes={post['likes']}")
            done(8, total)
        except Exception as e:
            fail(8, e)

        # ── Task 9: Users in Wrightborough ────────────────────────────────────
        self.log("━━ Task 9: Users in Wrightborough")
        try:
            url = self._social_url("users")
            links = self._user_links(url)
            count = 0
            for i, u in enumerate(links, 1):
                usr = self._scrape_user(u)
                match = "wrightborough" in usr["location"].lower()
                if match: count += 1
                self.log(f"  [{i}/{len(links)}] '{usr['location']}' {'← MATCH' if match else ''}")
            done(9, count)
        except Exception as e:
            fail(9, e)

        # ── Task 10: Forum June 2025 joiners reputation sum ───────────────────
        self.log("━━ Task 10: June 2025 joiners rep sum")
        try:
            url = self._forum_url("users")
            links = self._user_links(url)
            total = 0
            for i, u in enumerate(links, 1):
                fu = self._scrape_forum_user(u)
                is_june = bool(re.search(r"june\s*2025|2025[-/]06", fu["joined"], re.I))
                if is_june: total += fu["reputation"]
                self.log(f"  [{i}/{len(links)}] joined='{fu['joined']}' rep={fu['reputation']} {'← JUNE25' if is_june else ''}")
            done(10, total)
        except Exception as e:
            fail(10, e)

        # ── Task 11: Vendor badge total reputation ────────────────────────────
        self.log("━━ Task 11: Vendor badge reputation total")
        try:
            url = self._forum_url("users")
            links = self._user_links(url)
            total = 0
            for i, u in enumerate(links, 1):
                fu = self._scrape_forum_user(u)
                has_vendor = any("vendor" in b.lower() for b in fu["badges"])
                if has_vendor: total += fu["reputation"]
                self.log(f"  [{i}/{len(links)}] badges={fu['badges']} rep={fu['reputation']} {'← VENDOR' if has_vendor else ''}")
            done(11, total)
        except Exception as e:
            fail(11, e)

        # ── Task 12: General board 0-reply threads ────────────────────────────
        self.log("━━ Task 12: General board 0-reply threads")
        try:
            url = self._forum_url("general")
            links = self._thread_links(url)
            count = 0
            for i, u in enumerate(links, 1):
                replies = self._scrape_thread(u)
                if replies == 0: count += 1
                self.log(f"  [{i}/{len(links)}] replies={replies} {'← ZERO' if replies == 0 else ''}")
            done(12, count)
        except Exception as e:
            fail(12, e)

        return results
