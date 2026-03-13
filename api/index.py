"""
CineVerse Vercel Serverless Function
Single catch-all handler for all /api/* routes.
Scrapes movie/TV/anime data from public sources, no API key needed.
"""

from http.server import BaseHTTPRequestHandler
import json
import urllib.request
import urllib.parse
import re
import time

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
}

JIKAN_BASE = 'https://api.jikan.moe/v4'


def fetch(url, as_json=False):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = resp.read().decode('utf-8')
        return json.loads(data) if as_json else data


def _upgrade_img(url, width=780):
    if not url:
        return ''
    return re.sub(r'/t/p/w\d+(?:_and_h\d+_face)?/', f'/t/p/w{width}/', url)


def _parse_tmdb_list(html, media_type='movie'):
    items = []
    ids = re.findall(r'href="/' + media_type + r'/(\d+)[^"]*"\s+title="([^"]*)"', html)
    imgs = re.findall(r'class="poster[^"]*"\s+src="([^"]*)"', html)
    scores = re.findall(r'data-percent="([^"]*)"', html)

    seen = set()
    img_idx = 0
    score_idx = 0
    for mid, title in ids:
        if mid in seen:
            continue
        seen.add(mid)
        items.append({
            'id': int(mid),
            'title': title,
            'media_type': media_type,
            'poster': _upgrade_img(imgs[img_idx]) if img_idx < len(imgs) else '',
            'rating': round(float(scores[score_idx]) / 10, 1) if score_idx < len(scores) and scores[score_idx] else 0,
            'year': '',
        })
        img_idx += 1
        score_idx += 1
    return items


def scrape_tmdb_movies(category='popular'):
    url_map = {
        'popular': 'https://www.themoviedb.org/movie',
        'now_playing': 'https://www.themoviedb.org/movie/now-playing',
        'upcoming': 'https://www.themoviedb.org/movie/upcoming',
        'top_rated': 'https://www.themoviedb.org/movie/top-rated',
    }
    return _parse_tmdb_list(fetch(url_map.get(category, url_map['popular'])), 'movie')


def scrape_tmdb_tv(category='popular'):
    url_map = {
        'popular': 'https://www.themoviedb.org/tv',
        'airing_today': 'https://www.themoviedb.org/tv/airing-today',
        'on_the_air': 'https://www.themoviedb.org/tv/on-the-air',
        'top_rated': 'https://www.themoviedb.org/tv/top-rated',
    }
    return _parse_tmdb_list(fetch(url_map.get(category, url_map['popular'])), 'tv')


def scrape_tmdb_trending(media='all'):
    if media == 'movie':
        return scrape_tmdb_movies('popular')
    elif media == 'tv':
        return scrape_tmdb_tv('popular')
    else:
        movies = scrape_tmdb_movies('popular')[:10]
        tv = scrape_tmdb_tv('popular')[:10]
        combined = []
        for i in range(max(len(movies), len(tv))):
            if i < len(movies):
                combined.append(movies[i])
            if i < len(tv):
                combined.append(tv[i])
        return combined


def scrape_tmdb_regional(media_type, country):
    url = f'https://www.themoviedb.org/{media_type}?with_origin_country={country}'
    return _parse_tmdb_list(fetch(url), media_type)


def scrape_tmdb_detail(media_type, mid):
    url = f'https://www.themoviedb.org/{media_type}/{mid}'
    html = fetch(url)
    detail = {'id': int(mid), 'media_type': media_type}

    title_m = re.search(r'<h2>\s*<a[^>]*>(.*?)</a>', html)
    if not title_m:
        title_m = re.search(r'class="title".*?<a[^>]*>(.*?)</a>', html, re.DOTALL)
    detail['title'] = title_m.group(1).strip() if title_m else ''

    ov = re.search(r'class="overview".*?<p>(.*?)</p>', html, re.DOTALL)
    detail['overview'] = ov.group(1).strip() if ov else ''

    score = re.search(r'data-percent="(\d+)"', html)
    detail['rating'] = round(float(score.group(1)) / 10, 1) if score else 0

    genre_block = re.search(r'class="genres".*?>(.*?)</span>', html, re.DOTALL)
    detail['genres'] = re.findall(r'>([^<]+)</a>', genre_block.group(1)) if genre_block else []

    date_m = re.search(r'(\d{4})', html[html.find('class="release"'):html.find('class="release"') + 200]) if 'class="release"' in html else None
    detail['year'] = date_m.group(1) if date_m else ''

    runtime_m = re.search(r'class="runtime".*?(\d+)h\s*(\d+)?m?', html, re.DOTALL)
    if runtime_m:
        h = int(runtime_m.group(1))
        m = int(runtime_m.group(2)) if runtime_m.group(2) else 0
        detail['runtime'] = f'{h * 60 + m} min'
    else:
        detail['runtime'] = ''

    status_m = re.search(r'<bdi>Status</bdi>.*?<p>(.*?)</p>', html, re.DOTALL)
    detail['status'] = status_m.group(1).strip() if status_m else ''

    lang_m = re.search(r'<bdi>Original Language</bdi>.*?<p>(.*?)</p>', html, re.DOTALL)
    detail['language'] = lang_m.group(1).strip() if lang_m else ''

    poster_m = re.search(r'class="poster.*?src="([^"]*)"', html)
    detail['poster'] = _upgrade_img(poster_m.group(1)) if poster_m else ''

    bg = re.findall(r'url\(["\']?(https://media\.themoviedb\.org/t/p/[^"\')\s]+)', html)
    detail['backdrop'] = bg[0].replace('/w1920_and_h800_multi_faces/', '/original/') if bg else ''

    cast = []
    cast_block = re.findall(r'class="card".*?src="([^"]*)".*?<p>.*?<a[^>]*>(.*?)</a>.*?class="character">\s*(.*?)\s*</p>', html, re.DOTALL)
    for avatar, name, character in cast_block[:12]:
        character = re.sub(r'<.*?>', '', character).strip()
        cast.append({'name': name.strip(), 'character': character, 'avatar': _upgrade_img(avatar, 185)})
    detail['cast'] = cast
    return detail


def scrape_tmdb_search(query):
    encoded = urllib.parse.quote(query)
    url = f'https://www.themoviedb.org/search?query={encoded}'
    html = fetch(url)
    items = []
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


# ===== JIKAN (ANIME) =====

def _transform_jikan(data):
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
    url_map = {
        'popular': f'{JIKAN_BASE}/top/anime?filter=bypopularity&limit=25',
        'airing': f'{JIKAN_BASE}/top/anime?filter=airing&limit=25',
        'upcoming': f'{JIKAN_BASE}/seasons/upcoming?limit=25',
        'top_rated': f'{JIKAN_BASE}/top/anime?limit=25',
        'movies': f'{JIKAN_BASE}/top/anime?type=movie&limit=25',
    }
    return _transform_jikan(fetch(url_map.get(category, url_map['popular']), as_json=True))


def search_anime(query):
    encoded = urllib.parse.quote(query)
    return _transform_jikan(fetch(f'{JIKAN_BASE}/anime?q={encoded}&limit=10', as_json=True))


def get_anime_detail(mal_id):
    a = fetch(f'{JIKAN_BASE}/anime/{mal_id}/full', as_json=True).get('data', {})
    img = a.get('images', {}).get('jpg', {})
    return {
        'id': a.get('mal_id', mal_id),
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
        'runtime': a.get('duration', ''),
        'language': 'JA',
        'cast': [],
        'source': 'jikan',
    }


# ===== VIDEO SOURCES (采集API) =====

VIDEO_SOURCES = [
    {'name': '暴风资源', 'key': 'bfzy', 'api': 'https://bfzyapi.com/api.php/provide/vod/'},
    {'name': '红牛资源', 'key': 'hnzy', 'api': 'https://www.hongniuzy2.com/api.php/provide/vod/from/hnm3u8/'},
]


def video_search(query):
    """Search across video sources for playable content."""
    results = []
    for src in VIDEO_SOURCES:
        try:
            url = src['api'] + '?ac=videolist&wd=' + urllib.parse.quote(query)
            data = fetch(url, as_json=True)
            for item in data.get('list', [])[:5]:
                play_urls = item.get('vod_play_url', '')
                episodes = []
                if play_urls:
                    # Use first source group only (before $$$)
                    first_group = play_urls.split('$$$')[0]
                    for ep in first_group.split('#'):
                        parts = ep.split('$', 1)
                        if len(parts) == 2 and parts[1].strip():
                            episodes.append({'name': parts[0], 'url': parts[1]})
                if episodes:  # Only add if has playable episodes
                    results.append({
                        'id': item.get('vod_id'),
                        'title': item.get('vod_name', ''),
                        'type': item.get('type_name', ''),
                        'pic': item.get('vod_pic', ''),
                        'remarks': item.get('vod_remarks', ''),
                        'year': item.get('vod_year', ''),
                        'area': item.get('vod_area', ''),
                        'source': src['key'],
                        'source_name': src['name'],
                        'episodes': episodes,
                    })
            if results:
                break
        except Exception:
            continue
    return results


def video_detail(source_key, vid):
    """Get video detail with play URLs from a specific source."""
    src = next((s for s in VIDEO_SOURCES if s['key'] == source_key), VIDEO_SOURCES[0])
    try:
        url = src['api'] + '?ac=detail&ids=' + str(vid)
        data = fetch(url, as_json=True)
        if not data.get('list'):
            return {'error': 'not found'}
        item = data['list'][0]
        play_urls = item.get('vod_play_url', '')
        episodes = []
        if play_urls:
            for group in play_urls.split('$$$'):
                for ep in group.split('#'):
                    parts = ep.split('$', 1)
                    if len(parts) == 2 and parts[1].strip():
                        episodes.append({'name': parts[0], 'url': parts[1]})
        return {
            'id': item.get('vod_id'),
            'title': item.get('vod_name', ''),
            'type': item.get('type_name', ''),
            'pic': item.get('vod_pic', ''),
            'desc': item.get('vod_content', '').replace('<p>', '').replace('</p>', ''),
            'year': item.get('vod_year', ''),
            'area': item.get('vod_area', ''),
            'director': item.get('vod_director', ''),
            'actor': item.get('vod_actor', ''),
            'remarks': item.get('vod_remarks', ''),
            'source': src['key'],
            'source_name': src['name'],
            'episodes': episodes,
        }
    except Exception as e:
        return {'error': str(e)}


# ===== ROUTER =====

def route(path, params):
    # Movies
    if path == 'movies/popular':
        return scrape_tmdb_movies('popular')
    if path == 'movies/now_playing':
        return scrape_tmdb_movies('now_playing')
    if path == 'movies/upcoming':
        return scrape_tmdb_movies('upcoming')
    if path == 'movies/top_rated':
        return scrape_tmdb_movies('top_rated')

    # TV
    if path == 'tv/popular':
        return scrape_tmdb_tv('popular')
    if path == 'tv/airing':
        return scrape_tmdb_tv('airing_today')
    if path == 'tv/top_rated':
        return scrape_tmdb_tv('top_rated')

    # Trending
    if path.startswith('trending/'):
        media = path.split('/')[-1]
        return scrape_tmdb_trending(media)

    # Regional
    if path == 'regional':
        mtype = params.get('type', 'movie')
        country = params.get('country', 'CN')
        return scrape_tmdb_regional(mtype, country)

    # Anime
    if path == 'anime/popular':
        return get_anime('popular')
    if path == 'anime/airing':
        return get_anime('airing')
    if path == 'anime/upcoming':
        return get_anime('upcoming')
    if path == 'anime/top_rated':
        return get_anime('top_rated')
    if path == 'anime/movies':
        return get_anime('movies')

    # Detail
    if path.startswith('detail/anime/'):
        mal_id = path.split('/')[-1]
        return get_anime_detail(mal_id)
    if path.startswith('detail/movie/'):
        mid = path.split('/')[-1]
        return scrape_tmdb_detail('movie', mid)
    if path.startswith('detail/tv/'):
        tid = path.split('/')[-1]
        return scrape_tmdb_detail('tv', tid)

    # Search
    if path == 'search':
        q = params.get('q', '')
        if not q:
            return []
        results = scrape_tmdb_search(q)
        try:
            results += search_anime(q)[:5]
        except Exception:
            pass
        return results

    # Video search & play
    if path == 'video/search':
        q = params.get('q', '')
        if not q:
            return []
        return video_search(q)

    if path == 'video/detail':
        source = params.get('source', 'bfzy')
        vid = params.get('id', '')
        if not vid:
            return {'error': 'missing id'}
        return video_detail(source, vid)

    return {'error': 'not found'}


# ===== VERCEL HANDLER =====

class handler(BaseHTTPRequestHandler):

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = dict(urllib.parse.parse_qsl(parsed.query))

        # Extract the route path from query param (set by vercel.json rewrite)
        api_path = params.pop('_path', '')
        if not api_path:
            # Fallback: parse from URL path
            api_path = parsed.path.replace('/api/', '').strip('/')

        try:
            data = route(api_path, params)
            body = json.dumps(data, ensure_ascii=False).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            # CDN cache for 30 minutes, serve stale for 1 hour while revalidating
            self.send_header('Cache-Control', 's-maxage=1800, stale-while-revalidate=3600')
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            body = json.dumps({'error': str(e)}, ensure_ascii=False).encode('utf-8')
            self.send_response(500)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.end_headers()
            self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass  # Suppress logs in serverless
