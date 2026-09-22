#!/usr/bin/env python3
"""
ScrapeMaster 2000 - local helper + launcher.

Run:   python scrapemaster2000.py
It starts a small server on http://127.0.0.1:8787 (your computer only) and opens
scrapemaster2000.html in your browser. The helper fetches pages and images for the
interface, because browsers don't let an HTML page read other websites directly.

No third-party packages needed (Python 3.8+). Stop it with Ctrl+C.
"""

import hashlib
import io
import json
import os
import re
import ssl
import sys
import threading
import webbrowser
import zipfile
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urljoin, urlparse
from urllib.request import Request, urlopen

HOST, PORT = "127.0.0.1", 8787
APP_NAME = "ScrapeMaster 2000"
# When packaged as an executable (PyInstaller), bundled files live in sys._MEIPASS.
HERE = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
HTML_FILE = os.path.join(HERE, "scrapemaster2000.html")

# Trust the computer's own certificates, plus certifi's list when available
# (packaged Mac builds have no usable system list without it).
SSL_CONTEXT = ssl.create_default_context()
try:
    import certifi
    SSL_CONTEXT.load_verify_locations(cafile=certifi.where())
except Exception:
    pass

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
IMG_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".bmp", ".ico", ".avif", ".tif", ".tiff"}
CONTENT_TYPE_EXT = {
    "image/jpeg": ".jpg", "image/png": ".png", "image/gif": ".gif", "image/webp": ".webp",
    "image/svg+xml": ".svg", "image/bmp": ".bmp", "image/x-icon": ".ico",
    "image/vnd.microsoft.icon": ".ico", "image/avif": ".avif", "image/tiff": ".tif",
}
CSS_URL_RE = re.compile(r"url\(\s*['\"]?([^'\")]+)['\"]?\s*\)", re.I)

# Query parameters image CDNs (imgix, Cloudinary-style proxies, Shopify, WordPress, Contentful,
# Sanity, Next.js, etc.) use to resize/re-encode an image. Removing them gets the original file.
RESIZE_PARAMS = {
    "fm", "q", "w", "h", "fit", "crop", "auto", "dpr", "format", "fmt", "width", "height",
    "quality", "resize", "size", "rect", "ar", "bg", "blur", "sharp", "sharpen", "trim",
    "max-w", "max-h", "min-w", "min-h", "maxwidth", "maxheight", "mode", "scale", "fl",
    "cs", "ixlib", "ixid", "s", "sig", "v", "rs", "sat", "exp", "con", "gam", "vib",
    "orient", "rot", "flip", "fp-x", "fp-y", "fp-z", "pad", "strip", "lossless", "im",
    "tr", "tw", "th", "sw", "sh", "zoom", "compress", "resolution", "optimize",
}


def original_url(url):
    """Strip resize/format parameters from an image URL. Returns None if nothing to strip."""
    parts = urlparse(url)
    if not parts.query:
        return None
    kept = [p for p in parts.query.split("&")
            if p and unquote(p.split("=", 1)[0]).lower() not in RESIZE_PARAMS]
    if len(kept) == len([p for p in parts.query.split("&") if p]):
        return None
    return parts._replace(query="&".join(kept)).geturl()


MAX_IMAGE_BYTES = 50 * 1024 * 1024

_cache = {}               # image url -> (bytes, content_type)
_cache_lock = threading.Lock()


# ---------------------------------------------------------------- scraping

def parse_srcset(value):
    out = []
    for part in value.split(","):
        bits = part.strip().split()
        if bits:
            size = 0.0
            if len(bits) > 1:
                try:
                    size = float(bits[1].rstrip("wx"))
                except ValueError:
                    pass
            out.append((size, bits[0]))
    out.sort(key=lambda c: c[0], reverse=True)
    return [u for _, u in out]


class ImageFinder(HTMLParser):
    def __init__(self):
        super().__init__()
        self.found = []        # (url, where-found)
        self.base = None
        self.title = ""
        self._in_title = False

    def add(self, url, where):
        if url and not url.strip().startswith(("javascript:", "about:")):
            self.found.append((url.strip(), where))

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "title":
            self._in_title = True
        if tag == "base" and a.get("href"):
            self.base = a["href"]
        if tag == "img":
            for key in ("src", "data-src", "data-original", "data-lazy-src", "data-url"):
                self.add(a.get(key), "img")
            for key in ("srcset", "data-srcset"):
                if a.get(key):
                    for u in parse_srcset(a[key]):
                        self.add(u, "srcset")
        if tag == "source" and a.get("srcset"):
            for u in parse_srcset(a["srcset"]):
                self.add(u, "picture")
        if tag == "meta":
            prop = (a.get("property") or a.get("name") or "").lower()
            if prop in ("og:image", "og:image:url", "og:image:secure_url", "twitter:image", "twitter:image:src"):
                self.add(a.get("content"), "social preview")
        if tag == "link":
            rel = a.get("rel", "").lower()
            if "icon" in rel or "image_src" in rel:
                self.add(a.get("href"), "icon")
        if a.get("style"):
            for u in CSS_URL_RE.findall(a["style"]):
                self.add(u, "background")

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data


def fetch(url, timeout=25, limit=None):
    req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    with urlopen(req, timeout=timeout, context=SSL_CONTEXT) as resp:
        data = resp.read(limit + 1) if limit else resp.read()
        if limit and len(data) > limit:
            raise ValueError("file too large")
        return data, resp.headers.get("Content-Type", ""), resp.geturl()


def scan_page(page_url):
    body, ctype, final_url = fetch(page_url)
    m = re.search(r"charset=([\w-]+)", ctype)
    html = body.decode(m.group(1) if m else "utf-8", errors="replace")

    finder = ImageFinder()
    finder.feed(html)
    base = urljoin(final_url, finder.base) if finder.base else final_url
    for block in re.findall(r"<style[^>]*>(.*?)</style>", html, re.I | re.S):
        for u in CSS_URL_RE.findall(block):
            if os.path.splitext(urlparse(u).path)[1].lower() in IMG_EXTS:
                finder.add(u, "css")

    seen, images = set(), []
    host = urlparse(final_url).netloc
    for u, where in finder.found:
        if u.startswith("data:"):
            continue
        absolute = urljoin(base, u).split("#")[0]
        if absolute.startswith(("http://", "https://")) and absolute not in seen:
            seen.add(absolute)
            images.append({
                "url": absolute,
                "original": original_url(absolute),
                "found_in": where,
                "same_domain": urlparse(absolute).netloc == host,
            })
    return {"page": final_url, "title": finder.title.strip(), "images": images}


def get_image(url):
    with _cache_lock:
        if url in _cache:
            return _cache[url]
    data, ctype, _ = fetch(url, limit=MAX_IMAGE_BYTES)
    ctype = ctype.split(";")[0].strip().lower()
    if not ctype or ctype in ("application/octet-stream", "binary/octet-stream"):
        ext = os.path.splitext(urlparse(url).path)[1].lower()
        ctype = {v: k for k, v in CONTENT_TYPE_EXT.items()}.get(ext, "application/octet-stream")
    if not (ctype.startswith("image/") or ctype == "application/octet-stream"):
        raise ValueError(f"not an image ({ctype})")
    with _cache_lock:
        _cache[url] = (data, ctype)
    return data, ctype


def filename_for(url, ctype, used):
    name = os.path.basename(unquote(urlparse(url).path)) or "image"
    name = re.sub(r"[^\w.\-]+", "_", name)[:120]
    stem, ext = os.path.splitext(name)
    if ext.lower() not in IMG_EXTS:
        ext = CONTENT_TYPE_EXT.get(ctype, ext or ".img")
    candidate = stem + ext
    if candidate.lower() in used:
        candidate = f"{stem}_{hashlib.md5(url.encode()).hexdigest()[:8]}{ext}"
    used.add(candidate.lower())
    return candidate


def build_zip(urls):
    def grab(u):
        try:
            return u, get_image(u)
        except Exception:
            return u, None

    buf, used, hashes = io.BytesIO(), set(), set()
    with ThreadPoolExecutor(6) as pool:
        results = list(pool.map(grab, urls))
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as zf:
        for u, got in results:
            if not got:
                continue
            data, ctype = got
            digest = hashlib.sha1(data).digest()
            if digest in hashes:
                continue
            hashes.add(digest)
            zf.writestr(filename_for(u, ctype, used), data)
    return buf.getvalue()


# ---------------------------------------------------------------- server

class Handler(BaseHTTPRequestHandler):
    server_version = "ScrapeMaster2000/1.0"

    def log_message(self, *args):
        pass

    def _ok_origin(self):
        # Only answer requests from our own page (or a file:// page, whose origin is "null").
        origin = self.headers.get("Origin")
        host = (self.headers.get("Host") or "").split(":")[0]
        if host not in ("127.0.0.1", "localhost"):
            return False
        port = self.server.server_port
        return origin in (None, "null", f"http://{HOST}:{port}", f"http://localhost:{port}")

    def _cors(self):
        origin = self.headers.get("Origin")
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")

    def _send(self, code, body, ctype="application/json", extra=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self._cors()
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.send_header("Access-Control-Allow-Methods", "GET, POST")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        if not self._ok_origin():
            return self._send(403, {"error": "forbidden"})
        path = urlparse(self.path)
        q = parse_qs(path.query)

        if path.path in ("/", "/index.html", "/scrapemaster2000.html"):
            try:
                with open(HTML_FILE, "rb") as f:
                    return self._send(200, f.read(), "text/html; charset=utf-8")
            except FileNotFoundError:
                return self._send(404, "scrapemaster2000.html must be in the same folder as scrapemaster2000.py",
                                  "text/plain")

        if path.path == "/api/ping":
            return self._send(200, {"ok": True})

        if path.path == "/api/scan":
            url = (q.get("url") or [""])[0].strip()
            if not url:
                return self._send(400, {"error": "Please enter a web address."})
            if "://" not in url:
                url = "https://" + url
            try:
                return self._send(200, scan_page(url))
            except Exception as e:
                return self._send(502, {"error": f"Couldn't load that page: {e}"})

        if path.path == "/api/image":
            url = (q.get("url") or [""])[0]
            try:
                data, ctype = get_image(url)
            except Exception as e:
                return self._send(502, {"error": str(e)})
            extra = {}
            if q.get("download"):
                name = filename_for(url, ctype, set())
                extra["Content-Disposition"] = f'attachment; filename="{name}"'
            return self._send(200, data, ctype, extra)

        self._send(404, {"error": "not found"})

    def do_POST(self):
        if not self._ok_origin():
            return self._send(403, {"error": "forbidden"})
        if urlparse(self.path).path != "/api/zip":
            return self._send(404, {"error": "not found"})
        try:
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length) or b"{}")
            urls = [u for u in payload.get("urls", []) if isinstance(u, str)]
            name = re.sub(r"[^\w.\-]+", "_", payload.get("name") or "images")[:80]
        except Exception:
            return self._send(400, {"error": "bad request"})
        data = build_zip(urls)
        self._send(200, data, "application/zip",
                   {"Content-Disposition": f'attachment; filename="{name}.zip"'})


def already_running(port):
    """True if a ScrapeMaster helper is already answering on this port."""
    try:
        with urlopen(f"http://{HOST}:{port}/api/ping", timeout=1.5) as r:
            return json.loads(r.read()).get("ok") is True
    except Exception:
        return False


def main():
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass
    server = None
    for port in range(PORT, PORT + 10):
        try:
            server = ThreadingHTTPServer((HOST, port), Handler)
            break
        except OSError:
            if already_running(port):
                print(f"{APP_NAME} is already running - opening it in your browser.")
                webbrowser.open(f"http://{HOST}:{port}/")
                return
    if server is None:
        raise SystemExit(f"Couldn't find a free port between {PORT} and {PORT + 9}.")

    url = f"http://{HOST}:{server.server_port}/"
    print("=" * 52)
    print(f"  {APP_NAME}")
    print("=" * 52)
    print(f"  Running at {url}")
    print("  Your browser should open automatically.")
    print("  Keep this window open while you use it.")
    print("  Close this window (or press Ctrl+C) to quit.")
    print("=" * 52)
    if "--no-browser" not in sys.argv:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n{APP_NAME} hit a problem: {e}")
        if getattr(sys, "frozen", False):
            input("Press Enter to close this window...")
        sys.exit(1)
