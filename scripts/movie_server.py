#!/usr/bin/env python3
"""
CineVerse Scraper Server
Scrapes movie/TV/anime data from public websites, no API key needed.
Sources:
  - TMDB website (movies, TV shows)
  - Jikan API (anime from MyAnimeList, free, no key)
"""

import http.server
import json
import urllib.request
import urllib.parse
import re
import os
import time
import threading
from pathlib import Path

PORT = 8080
FRONT_DIR = str(Path(__file__).resolve().parent.parent / 'front')
CACHE = {}
CACHE_TTL = 1800  # 30 min

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
}


def fetch(url, as_json=False):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = resp.read().decode('utf-8')
        return json.loads(data) if as_json else data


def get_cached(key, fetcher):
    if key in CACHE and time.time() - CACHE[key]['t'] < CACHE_TTL:
        return CACHE[key]['d']
    try:
        data = fetcher()
        CACHE[key] = {'d': data, 't': time.time()}
        return data
    except Exception as e:
        print(f'[ERROR] {key}: {e}')
        if key in CACHE:
            return CACHE[key]['d']
        return []


# ========== TMDB SCRAPER ==========

def _upgrade_img(url, width=780):
    """Upgrade TMDB image URL to higher resolution."""
    if not url:
        return ''
    # Convert w220_and_h330_face to w780 for higher quality
    return re.sub(r'/t/p/w\d+(?:_and_h\d+_face)?/', f'/t/p/w{width}/', url)


def _parse_tmdb_list(html, media_type='movie'):
    """Parse TMDB listing page HTML into structured data."""
    items = []
    # Extract each card's data
    ids = re.findall(r'href="/' + media_type + r'/(\d+)[^"]*"\s+title="([^"]*)"', html)
    imgs = re.findall(r'class="poster[^"]*"\s+src="([^"]*)"', html)
    scores = re.findall(r'data-percent="([^"]*)"', html)
    dates_raw = re.findall(r'<p>\s*([^<]+?)\s*</p>', html)
    # Filter dates - look for date-like strings
    dates = []
    for d in dates_raw:
        d = d.strip()
        if re.match(r'\d{4}', d) or re.search(r'月|年|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec', d):
            dates.append(d)

    seen = set()
    img_idx = 0
    score_idx = 0
    date_idx = 0
    for mid, title in ids:
        if mid in seen:
            continue
        seen.add(mid)
        item = {
            'id': int(mid),
            'title': title,
            'media_type': media_type,
            'poster': _upgrade_img(imgs[img_idx]) if img_idx < len(imgs) else '',
            'rating': round(float(scores[score_idx]) / 10, 1) if score_idx < len(scores) and scores[score_idx] else 0,
            'year': '',
        }
        # Try to extract year from date
        if date_idx < len(dates):
            year_match = re.search(r'(\d{4})', dates[date_idx])
            if year_match:
                item['year'] = year_match.group(1)
            date_idx += 1
        img_idx += 1
        score_idx += 1
        items.append(item)
    return items


def scrape_tmdb_movies(category='popular'):
    """Scrape movies from TMDB website."""
    url_map = {
        'popular': 'https://www.themoviedb.org/movie',
        'now_playing': 'https://www.themoviedb.org/movie/now-playing',
        'upcoming': 'https://www.themoviedb.org/movie/upcoming',
        'top_rated': 'https://www.themoviedb.org/movie/top-rated',
    }
    url = url_map.get(category, url_map['popular'])
    html = fetch(url)
    return _parse_tmdb_list(html, 'movie')


def scrape_tmdb_tv(category='popular'):
    """Scrape TV shows from TMDB website."""
    url_map = {
        'popular': 'https://www.themoviedb.org/tv',
        'airing_today': 'https://www.themoviedb.org/tv/airing-today',
        'on_the_air': 'https://www.themoviedb.org/tv/on-the-air',
        'top_rated': 'https://www.themoviedb.org/tv/top-rated',
    }
    url = url_map.get(category, url_map['popular'])
    html = fetch(url)
    return _parse_tmdb_list(html, 'tv')


def scrape_tmdb_trending(media='all'):
    """Scrape trending/popular from TMDB. TMDB's /trending/ pages return 404,
    so we use the main listing pages which show popular (trending) content."""
    if media == 'movie':
        return scrape_tmdb_movies('popular')
    elif media == 'tv':
        return scrape_tmdb_tv('popular')
    else:
        # 'all' - combine movies and TV
        movies = scrape_tmdb_movies('popular')[:10]
        tv = scrape_tmdb_tv('popular')[:10]
        # Interleave
        combined = []
        for i in range(max(len(movies), len(tv))):
            if i < len(movies):
                combined.append(movies[i])
            if i < len(tv):
                combined.append(tv[i])
        return combined


def scrape_tmdb_detail(media_type, mid):
    """Scrape detail page for a movie or TV show."""
    url = f'https://www.themoviedb.org/{media_type}/{mid}'
    html = fetch(url)

    detail = {'id': int(mid), 'media_type': media_type}

    # Title
    title_m = re.search(r'<h2>\s*<a[^>]*>(.*?)</a>', html)
    if not title_m:
        title_m = re.search(r'class="title".*?<a[^>]*>(.*?)</a>', html, re.DOTALL)
    detail['title'] = title_m.group(1).strip() if title_m else ''

    # Overview
    ov = re.search(r'class="overview".*?<p>(.*?)</p>', html, re.DOTALL)
    detail['overview'] = ov.group(1).strip() if ov else ''

    # Score
    score = re.search(r'data-percent="(\d+)"', html)
    detail['rating'] = round(float(score.group(1)) / 10, 1) if score else 0

    # Genres
    genre_block = re.search(r'class="genres".*?>(.*?)</span>', html, re.DOTALL)
    detail['genres'] = re.findall(r'>([^<]+)</a>', genre_block.group(1)) if genre_block else []

    # Year / Date
    date_m = re.search(r'class="release".*?(\d{2}/\d{2}/\d{4})', html, re.DOTALL)
    if not date_m:
        date_m = re.search(r'(\d{4})年', html)
    detail['year'] = date_m.group(1)[-4:] if date_m else ''

    # Runtime
    runtime_m = re.search(r'class="runtime".*?(\d+)h\s*(\d+)?m?', html, re.DOTALL)
    if runtime_m:
        h = int(runtime_m.group(1))
        m = int(runtime_m.group(2)) if runtime_m.group(2) else 0
        detail['runtime'] = f'{h * 60 + m} min'
    else:
        detail['runtime'] = ''

    # Status
    status_m = re.search(r'<bdi>Status</bdi>.*?<p>(.*?)</p>', html, re.DOTALL)
    detail['status'] = status_m.group(1).strip() if status_m else ''

    # Language
    lang_m = re.search(r'<bdi>Original Language</bdi>.*?<p>(.*?)</p>', html, re.DOTALL)
    detail['language'] = lang_m.group(1).strip() if lang_m else ''

    # Poster
    poster_m = re.search(r'class="poster.*?src="([^"]*)"', html)
    detail['poster'] = _upgrade_img(poster_m.group(1)) if poster_m else ''

    # Backdrop
    bg = re.findall(r'url\(["\']?(https://media\.themoviedb\.org/t/p/[^"\')\s]+)', html)
    detail['backdrop'] = bg[0].replace('/w1920_and_h800_multi_faces/', '/original/') if bg else ''

    # Cast
    cast = []
    cast_block = re.findall(r'class="card".*?src="([^"]*)".*?<p>.*?<a[^>]*>(.*?)</a>.*?class="character">\s*(.*?)\s*</p>', html, re.DOTALL)
    for avatar, name, character in cast_block[:12]:
        character = re.sub(r'<.*?>', '', character).strip()
        cast.append({
            'name': name.strip(),
            'character': character,
            'avatar': _upgrade_img(avatar, 185)
        })
    detail['cast'] = cast

    return detail


def scrape_tmdb_search(query):
    """Search TMDB website."""
    encoded = urllib.parse.quote(query)
    url = f'https://www.themoviedb.org/search?query={encoded}'
    html = fetch(url)
    items = []

    # Parse search results
    results = re.findall(
        r'class="result".*?href="/(movie|tv)/(\d+)[^"]*".*?<h2>(.*?)</h2>.*?(?:src="([^"]*)")?.*?<p>(.*?)</p>',
        html, re.DOTALL
    )

    for mtype, mid, title, poster, overview in results[:20]:
        title = re.sub(r'<.*?>', '', title).strip()
        overview = re.sub(r'<.*?>', '', overview).strip()
        items.append({
            'id': int(mid),
            'title': title,
            'media_type': mtype,
            'poster': _upgrade_img(poster) if poster else '',
            'overview': overview[:200],
            'rating': 0,
            'year': '',
        })

    # Fallback: simpler parsing
    if not items:
        movie_ids = re.findall(r'href="/(movie|tv)/(\d+)[^"]*"\s*(?:title="([^"]*)")?', html)
        imgs = re.findall(r'class="poster[^"]*"\s+src="([^"]*)"', html)
        seen = set()
        img_idx = 0
        for mtype, mid, title in movie_ids:
            key = f'{mtype}/{mid}'
            if key in seen:
                continue
            seen.add(key)
            items.append({
                'id': int(mid),
                'title': title or f'ID {mid}',
                'media_type': mtype,
                'poster': _upgrade_img(imgs[img_idx]) if img_idx < len(imgs) else '',
                'rating': 0,
                'year': '',
            })
            img_idx += 1

    return items


# ========== TMDB REGIONAL ==========

def scrape_tmdb_regional(media_type, country, sort='popularity'):
    """Scrape TMDB discover with country filter."""
    # TMDB's discover URLs
    sort_map = {
        'popularity': 'popularity.desc',
        'rating': 'vote_average.desc',
    }
    sort_val = sort_map.get(sort, 'popularity.desc')
    url = f'https://www.themoviedb.org/{media_type}?with_origin_country={country}&sort_by={sort_val}'
    html = fetch(url)
    return _parse_tmdb_list(html, media_type)


# ========== JIKAN (ANIME) ==========

JIKAN_BASE = 'https://api.jikan.moe/v4'
jikan_lock = threading.Lock()
last_jikan_call = 0


def jikan_throttle():
    """Jikan has rate limits (3 req/sec). Throttle calls."""
    global last_jikan_call
    with jikan_lock:
        now = time.time()
        wait = max(0, 0.4 - (now - last_jikan_call))
        if wait > 0:
            time.sleep(wait)
        last_jikan_call = time.time()


def _transform_jikan(data):
    """Transform Jikan API response to our format."""
    items = []
    for a in data.get('data', []):
        img = a.get('images', {}).get('jpg', {})
        items.append({
            'id': a['mal_id'],
            'title': a.get('title_japanese') or a.get('title', ''),
            'title_en': a.get('title_english') or a.get('title', ''),
            'media_type': 'anime',
            'poster': img.get('large_image_url') or img.get('image_url', ''),
            'rating': round(a.get('score', 0), 1) if a.get('score') else 0,
            'year': str(a.get('year', '')) if a.get('year') else '',
            'overview': a.get('synopsis', ''),
            'episodes': a.get('episodes'),
            'status': a.get('status', ''),
            'genres': [g['name'] for g in a.get('genres', [])],
            'source': 'jikan',
        })
    return items


def get_anime(category='popular'):
    """Get anime from Jikan API."""
    jikan_throttle()
    url_map = {
        'popular': f'{JIKAN_BASE}/top/anime?filter=bypopularity&limit=25',
        'airing': f'{JIKAN_BASE}/top/anime?filter=airing&limit=25',
        'upcoming': f'{JIKAN_BASE}/seasons/upcoming?limit=25',
        'top_rated': f'{JIKAN_BASE}/top/anime?limit=25',
        'movie': f'{JIKAN_BASE}/top/anime?type=movie&limit=25',
    }
    url = url_map.get(category, url_map['popular'])
    data = fetch(url, as_json=True)
    return _transform_jikan(data)


def search_anime(query):
    """Search anime via Jikan."""
    jikan_throttle()
    encoded = urllib.parse.quote(query)
    data = fetch(f'{JIKAN_BASE}/anime?q={encoded}&limit=20', as_json=True)
    return _transform_jikan(data)


def get_anime_detail(mal_id):
    """Get anime detail from Jikan."""
    jikan_throttle()
    data = fetch(f'{JIKAN_BASE}/anime/{mal_id}/full', as_json=True)
    a = data.get('data', {})
    img = a.get('images', {}).get('jpg', {})
    return {
        'id': a['mal_id'],
        'title': a.get('title_japanese') or a.get('title', ''),
        'title_en': a.get('title_english') or a.get('title', ''),
        'media_type': 'anime',
        'poster': img.get('large_image_url', ''),
        'backdrop': img.get('large_image_url', ''),
        'rating': round(a.get('score', 0), 1) if a.get('score') else 0,
        'year': str(a.get('year', '')) if a.get('year') else '',
        'overview': a.get('synopsis', ''),
        'episodes': a.get('episodes'),
        'status': a.get('status', ''),
        'genres': [g['name'] for g in a.get('genres', [])],
        'runtime': f"{a.get('duration', '')}" if a.get('duration') else '',
        'language': 'JA',
        'cast': [],
        'source': 'jikan',
    }


# ========== HTTP SERVER ==========

class CineVerseHandler(http.server.SimpleHTTPRequestHandler):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=FRONT_DIR, **kwargs)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        params = dict(urllib.parse.parse_qsl(parsed.query))

        # Serve frontend
        if path == '/':
            self.path = '/streaming.html'
            return super().do_GET()

        # API routes
        if path.startswith('/api/'):
            try:
                data = self.handle_api(path, params)
                self.send_json(data)
            except Exception as e:
                print(f'[API ERROR] {path}: {e}')
                self.send_json({'error': str(e)}, 500)
            return

        # Static files
        return super().do_GET()

    def handle_api(self, path, params):
        # Movies
        if path == '/api/movies/popular':
            return get_cached('m_pop', lambda: scrape_tmdb_movies('popular'))
        if path == '/api/movies/now_playing':
            return get_cached('m_now', lambda: scrape_tmdb_movies('now_playing'))
        if path == '/api/movies/upcoming':
            return get_cached('m_up', lambda: scrape_tmdb_movies('upcoming'))
        if path == '/api/movies/top_rated':
            return get_cached('m_top', lambda: scrape_tmdb_movies('top_rated'))

        # TV
        if path == '/api/tv/popular':
            return get_cached('tv_pop', lambda: scrape_tmdb_tv('popular'))
        if path == '/api/tv/airing':
            return get_cached('tv_air', lambda: scrape_tmdb_tv('airing_today'))
        if path == '/api/tv/top_rated':
            return get_cached('tv_top', lambda: scrape_tmdb_tv('top_rated'))

        # Trending
        if path == '/api/trending/all':
            return get_cached('tr_all', lambda: scrape_tmdb_trending('all'))
        if path == '/api/trending/movie':
            return get_cached('tr_m', lambda: scrape_tmdb_trending('movie'))
        if path == '/api/trending/tv':
            return get_cached('tr_tv', lambda: scrape_tmdb_trending('tv'))

        # Regional
        if path == '/api/regional':
            mtype = params.get('type', 'movie')
            country = params.get('country', 'CN')
            sort = params.get('sort', 'popularity')
            key = f'reg_{mtype}_{country}_{sort}'
            return get_cached(key, lambda: scrape_tmdb_regional(mtype, country, sort))

        # Anime
        if path == '/api/anime/popular':
            return get_cached('a_pop', lambda: get_anime('popular'))
        if path == '/api/anime/airing':
            return get_cached('a_air', lambda: get_anime('airing'))
        if path == '/api/anime/upcoming':
            return get_cached('a_up', lambda: get_anime('upcoming'))
        if path == '/api/anime/top_rated':
            return get_cached('a_top', lambda: get_anime('top_rated'))
        if path == '/api/anime/movies':
            return get_cached('a_mov', lambda: get_anime('movie'))

        # Detail
        if path.startswith('/api/detail/anime/'):
            mal_id = path.split('/')[-1]
            return get_cached(f'd_a_{mal_id}', lambda: get_anime_detail(mal_id))
        if path.startswith('/api/detail/movie/'):
            mid = path.split('/')[-1]
            return get_cached(f'd_m_{mid}', lambda: scrape_tmdb_detail('movie', mid))
        if path.startswith('/api/detail/tv/'):
            tid = path.split('/')[-1]
            return get_cached(f'd_t_{tid}', lambda: scrape_tmdb_detail('tv', tid))

        # Search
        if path == '/api/search':
            q = params.get('q', '')
            if not q:
                return []
            tmdb_results = get_cached(f's_tmdb_{q}', lambda: scrape_tmdb_search(q))
            anime_results = get_cached(f's_anime_{q}', lambda: search_anime(q))
            return tmdb_results + anime_results[:5]

        return {'error': 'not found'}

    def send_json(self, data, code=200):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', len(body))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        if '/api/' in (args[0] if args else ''):
            print(f'[API] {args[0]}')


if __name__ == '__main__':
    print(f'CineVerse Server starting on port {PORT}...')
    print(f'Serving frontend from: {FRONT_DIR}')
    print(f'Open http://localhost:{PORT}')
    print('No API key required! Data scraped from public sources.')
    with http.server.ThreadingHTTPServer(('', PORT), CineVerseHandler) as server:
        server.serve_forever()
