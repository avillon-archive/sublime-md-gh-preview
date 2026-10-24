# -*- coding: utf-8 -*-
import re
import struct

import pytest

from mdgh import remote

PNG = b'\x89PNG\r\n\x1a\n' + struct.pack('>I', 13) + b'IHDR' + struct.pack('>II', 3, 2) + b'\0' * 9
GIF = b'GIF89a' + struct.pack('<HH', 4, 5) + b'\0' * 20
JPG = (b'\xff\xd8' + b'\xff\xe0' + struct.pack('>H', 4) + b'\0\0'
       + b'\xff\xc0' + struct.pack('>H', 11) + b'\x08' + struct.pack('>HH', 7, 6) + b'\0' * 6)


def test_cache_names_are_stable_per_url_and_safe_file_names():
    a = remote.cache_name('https://x.test/a.png?s=1', 'png')
    assert a == remote.cache_name('https://x.test/a.png?s=1', 'png')
    assert a != remote.cache_name('https://x.test/a.png?s=2', 'png')
    assert re.fullmatch(r'[0-9a-f]+\.png', a)
    # The extension comes from the downloaded header, the stem from the URL alone.
    assert remote.cache_name('http://y.test/한글 이름.gif', 'jpg').split('.')[0] == \
        remote.cache_name('http://y.test/한글 이름.gif', 'gif').split('.')[0]


@pytest.mark.parametrize('data,ext', [(PNG, 'png'), (GIF, 'gif'), (JPG, 'jpg'), (b'<html>404</html>', None),
                                      (PNG[:12], None)])
def test_image_format_comes_from_the_header_not_the_url(data, ext):
    assert remote.image_ext(data) == ext


def test_eviction_deletes_oldest_first_until_the_cache_fits():
    files = [('new', 40, 300.0), ('old', 30, 100.0), ('mid', 50, 200.0)]
    assert remote.eviction(files, 120) == []
    assert remote.eviction(files, 90) == ['old']
    assert remote.eviction(files, 50) == ['old', 'mid']
    assert remote.eviction(files, 0) == ['old', 'mid', 'new']


def test_eviction_never_picks_the_file_just_written():
    files = [('just', 100, 1.0), ('other', 10, 2.0)]
    assert remote.eviction(files, 50, keep=('just',)) == ['other']


class FakeResponse:
    def __init__(self, data, length=None, fail_at=None):
        self.data = data
        self.pos = 0
        self.headers = {} if length is None else {'Content-Length': str(length)}
        self.fail_at = fail_at

    def read(self, n):
        if self.fail_at is not None and self.pos >= self.fail_at:
            raise OSError('connection reset')
        chunk = self.data[self.pos:self.pos + n]
        self.pos += len(chunk)
        return chunk

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def opener_for(resp, seen=None):
    def opener(req, timeout):
        if seen is not None:
            seen.append(timeout)
        if isinstance(resp, Exception):
            raise resp
        return resp
    return opener


def test_fetch_returns_the_body_within_the_size_limit():
    data = PNG * 1000
    seen = []
    assert remote.fetch('http://x.test/a', timeout=3,
                        opener=opener_for(FakeResponse(data), seen)) == data
    assert seen == [3]      # fetch hands its timeout to the opener


@pytest.mark.parametrize('resp', [
    FakeResponse(b'x' * 11, length=11),            # announced size over the limit
    FakeResponse(b'x' * 11),                      # streamed past the limit without a length
    FakeResponse(b'x' * 8, fail_at=4),            # broken connection
    OSError('refused'),
])
def test_fetch_gives_none_for_oversized_or_failed_downloads(resp):
    assert remote.fetch('http://x.test/a', max_bytes=10, opener=opener_for(resp)) is None


def test_worker_result_changes_state_only_through_the_main_thread_handler(monkeypatch, tmp_path):
    import sys
    import types
    queued = []
    fake = types.SimpleNamespace(set_timeout=lambda fn, ms: queued.append(fn))
    monkeypatch.setitem(sys.modules, 'sublime', fake)
    monkeypatch.setattr(remote, 'fetch', lambda url: None)
    ready = []
    images = remote.RemoteImages(str(tmp_path), ready.append)
    images.loading.add('http://x/a.png')

    images._download('http://x/a.png')      # what a pool worker runs

    assert images.loading == {'http://x/a.png'} and not images.failed
    assert len(queued) == 1
    queued[0]()                             # the main thread runs the posted handler
    assert images.loading == set() and images.failed == {'http://x/a.png'}
