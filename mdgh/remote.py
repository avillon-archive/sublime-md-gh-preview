# -*- coding: utf-8 -*-
"""Download cache of remote (http/https) images, used when `remote_images` is on.

The pure part (cache names, eviction choice, format check) is above "ST side"; the cache
object below imports sublime lazily. Files: sublime.cache_path()/<package>/images/<sha1(url)>.<ext>.
"""
import hashlib
import io
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from . import navigation

MAX_BYTES = 5 * 1024 * 1024
TIMEOUT_S = 10.0
CACHE_LIMIT = 200 * 1024 * 1024
EXTS = ('png', 'jpg', 'gif')
_CHUNK = 64 * 1024
WORKERS = 4


def cache_stem(url):
    return hashlib.sha1(url.encode('utf-8', 'surrogatepass')).hexdigest()


def cache_name(url, ext):
    return '%s.%s' % (cache_stem(url), ext)


def image_ext(data):
    """'png' | 'jpg' | 'gif' from the file header of downloaded bytes, or None (SVG, HTML error
    pages and every other format: the image stays an alt text link)."""
    if navigation.image_size(io.BytesIO(data)) is None:
        return None
    if data[:8] == b'\x89PNG\r\n\x1a\n':
        return 'png'
    if data[:6] in (b'GIF87a', b'GIF89a'):
        return 'gif'
    return 'jpg'


def eviction(files, limit, keep=()):
    """Names to delete so the cache is at most limit bytes: oldest mtime first.
    files: (name, size, mtime); names in keep (the file just written) are never chosen."""
    total = sum(f[1] for f in files)
    out = []
    for name, size, _ in sorted(files, key=lambda f: (f[2], f[0])):
        if total <= limit:
            break
        if name in keep:
            continue
        out.append(name)
        total -= size
    return out


def fetch(url, max_bytes=MAX_BYTES, timeout=TIMEOUT_S, opener=None):
    """Bytes of url, or None when it fails, is larger than max_bytes or takes longer than
    timeout seconds in total (urllib's own timeout is per socket operation)."""
    import urllib.request
    deadline = time.monotonic() + timeout
    req = urllib.request.Request(url, headers={'User-Agent': 'sublime-md-gh-preview'})
    try:
        with (opener or urllib.request.urlopen)(req, timeout=timeout) as resp:
            length = resp.headers.get('Content-Length')
            if length and length.isdigit() and int(length) > max_bytes:
                return None
            chunks = []
            n = 0
            while True:
                if time.monotonic() > deadline:
                    return None
                chunk = resp.read(_CHUNK)
                if not chunk:
                    break
                n += len(chunk)
                if n > max_bytes:
                    return None
                chunks.append(chunk)
            return b''.join(chunks)
    except Exception:       # network errors, HTTP errors, bad URLs: the image stays a link
        return None


# ---------------------------------------------------------------- ST side

# ST runs every async callback on one thread, so a slow download there would block the others
# (and parse): downloads run on this module's own pool, created on first use.
_pool = None


def _executor():
    global _pool
    if _pool is None:
        _pool = ThreadPoolExecutor(max_workers=WORKERS, thread_name_prefix='mdgh-remote')
    return _pool


def shutdown():
    """Stop the download pool (plugin_unloaded); a later lookup creates a new one."""
    global _pool
    pool, _pool = _pool, None
    if pool is not None:
        pool.shutdown(wait=False, cancel_futures=True)


class RemoteImages:
    """lookup(url) on the main thread: the cached file's path, or None while it is missing
    (then one download per URL is started on a worker; on_ready(url) runs on the main thread
    once it is cached). Failed URLs are not retried in this session."""

    def __init__(self, folder, on_ready, limit=CACHE_LIMIT):
        self.folder = folder
        self.on_ready = on_ready
        self.limit = limit
        self.paths = {}         # url -> cached file path
        self.failed = set()
        self.loading = set()
        self._lock = threading.Lock()   # serialises cache writes and eviction (workers)

    def _on_disk(self, url):
        stem = cache_stem(url)
        for ext in EXTS:
            p = os.path.join(self.folder, '%s.%s' % (stem, ext))
            if os.path.isfile(p):
                try:
                    os.utime(p)     # eviction is oldest first: a used file is young again
                except OSError:
                    pass
                return p
        return None

    def lookup(self, url):
        p = self.paths.get(url)
        if p is not None or url in self.failed:
            return p
        if url in self.loading:
            return None
        p = self._on_disk(url)
        if p is not None:
            self.paths[url] = p
            return p
        self.loading.add(url)
        _executor().submit(self._download, url)
        return None

    def _download(self, url):
        """Worker thread: touches no state but the cache files (under the lock); the result
        reaches loading/failed/paths only through _done on the main thread."""
        import sublime
        path = None
        try:
            data = fetch(url)
            ext = image_ext(data) if data else None
            if ext is not None:
                path = self._store(url, ext, data)
        except Exception:       # a url must leave `loading` whatever happens
            path = None
        sublime.set_timeout(lambda: self._done(url, path), 0)

    def _store(self, url, ext, data):
        name = cache_name(url, ext)
        path = os.path.join(self.folder, name)
        with self._lock:
            try:
                os.makedirs(self.folder, exist_ok=True)
                tmp = path + '.part'
                with open(tmp, 'wb') as f:
                    f.write(data)
                os.replace(tmp, path)
            except OSError:
                return None
            self._evict(keep=(name,))
        return path

    def _evict(self, keep=()):
        files = []
        try:
            for e in os.scandir(self.folder):
                if e.is_file() and not e.name.endswith('.part'):
                    st = e.stat()
                    files.append((e.name, st.st_size, st.st_mtime))
        except OSError:
            return
        for name in eviction(files, self.limit, keep):
            try:
                os.remove(os.path.join(self.folder, name))
            except OSError:
                pass

    def _done(self, url, path):
        self.loading.discard(url)
        if path is None:
            self.failed.add(url)
            return
        self.paths[url] = path
        # An evicted file must be looked up again rather than shown from a stale path.
        for u, p in list(self.paths.items()):
            if not os.path.isfile(p):
                del self.paths[u]
        self.on_ready(url)
