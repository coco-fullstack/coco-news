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
        'popular': 'https://www.themoviedb.org/movie?language=zh-CN',
        'now_playing': 'https://www.themoviedb.org/movie/now-playing?language=zh-CN',
        'upcoming': 'https://www.themoviedb.org/movie/upcoming?language=zh-CN',
        'top_rated': 'https://www.themoviedb.org/movie/top-rated?language=zh-CN',
    }
    return _parse_tmdb_list(fetch(url_map.get(category, url_map['popular'])), 'movie')


def scrape_tmdb_tv(category='popular'):
    url_map = {
        'popular': 'https://www.themoviedb.org/tv?language=zh-CN',
        'airing_today': 'https://www.themoviedb.org/tv/airing-today?language=zh-CN',
        'on_the_air': 'https://www.themoviedb.org/tv/on-the-air?language=zh-CN',
        'top_rated': 'https://www.themoviedb.org/tv/top-rated?language=zh-CN',
    }
    return _parse_tmdb_list(fetch(url_map.get(category, url_map['popular'])), 'tv')


def scrape_tmdb_trending(media='all'):
    """Scrape TMDB trending page — global hottest content today."""
    if media == 'movie':
        url = 'https://www.themoviedb.org/trending/movie/week?language=zh-CN'
        return _parse_tmdb_list(fetch(url), 'movie')
    elif media == 'tv':
        url = 'https://www.themoviedb.org/trending/tv/week?language=zh-CN'
        return _parse_tmdb_list(fetch(url), 'tv')
    else:
        # Mix trending movies and TV for the hero banner
        try:
            url_m = 'https://www.themoviedb.org/trending/movie/week?language=zh-CN'
            movies = _parse_tmdb_list(fetch(url_m), 'movie')[:8]
        except Exception:
            movies = []
        try:
            url_t = 'https://www.themoviedb.org/trending/tv/week?language=zh-CN'
            tv = _parse_tmdb_list(fetch(url_t), 'tv')[:8]
        except Exception:
            tv = []
        combined = []
        for i in range(max(len(movies), len(tv))):
            if i < len(movies):
                combined.append(movies[i])
            if i < len(tv):
                combined.append(tv[i])
        return combined


def scrape_tmdb_regional(media_type, country):
    url = f'https://www.themoviedb.org/{media_type}?with_origin_country={country}&language=zh-CN'
    return _parse_tmdb_list(fetch(url), media_type)


def _extract_tmdb_title(html):
    """Extract title from TMDB page using multiple strategies."""
    # Strategy 1: <h2><a>Title</a>
    m = re.search(r'<h2>\s*<a[^>]*>(.*?)</a>', html)
    if m and m.group(1).strip():
        return m.group(1).strip()
    # Strategy 2: class="title"...<a>Title</a>
    m = re.search(r'class="title".*?<a[^>]*>(.*?)</a>', html, re.DOTALL)
    if m and m.group(1).strip():
        return m.group(1).strip()
    # Strategy 3: <title>Title (Year) — TMDB</title>
    m = re.search(r'<title>\s*(.*?)\s*[\(（]', html)
    if m and m.group(1).strip():
        return m.group(1).strip()
    # Strategy 4: <title>Title — TMDB</title>
    m = re.search(r'<title>\s*(.*?)\s*[—\-–]', html)
    if m and m.group(1).strip():
        return m.group(1).strip()
    # Strategy 5: og:title meta
    m = re.search(r'og:title["\s]+content="([^"]*)"', html)
    if m and m.group(1).strip():
        t = m.group(1).strip()
        # Remove trailing "(Year)" or "— TMDB"
        t = re.sub(r'\s*[\(（].*$', '', t)
        return t
    return ''


def scrape_tmdb_detail(media_type, mid):
    # Fetch both Chinese and English pages
    url_cn = f'https://www.themoviedb.org/{media_type}/{mid}?language=zh-CN'
    url_en = f'https://www.themoviedb.org/{media_type}/{mid}'

    html_cn = None
    html_en = None
    title_cn = ''
    title_en = ''

    try:
        html_cn = fetch(url_cn)
        title_cn = _extract_tmdb_title(html_cn)
    except Exception:
        pass

    try:
        html_en = fetch(url_en)
        title_en = _extract_tmdb_title(html_en)
    except Exception:
        pass

    html = html_cn or html_en or ''
    detail = {'id': int(mid), 'media_type': media_type}

    # For TV shows, title_cn from zh-CN might just be "第X季" — need to fix
    # Use English title as display, Chinese title for 采集API search
    if title_cn and re.match(r'^第\s*\d+\s*季$', title_cn):
        # zh-CN returned only season label, use English title instead
        title_cn = title_en
    detail['title_cn'] = title_cn
    detail['title'] = title_en or title_cn

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
    url = f'https://www.themoviedb.org/search?query={encoded}&language=zh-CN'
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
    {'name': '非凡资源', 'key': 'ffzy', 'api': 'https://api.ffzyapi.com/api.php/provide/vod/', 'quality': 'HD'},
    {'name': '1080资源', 'key': '1080zy', 'api': 'https://api.1080zyku.com/inc/apijson.php?', 'quality': '1080P'},
    {'name': '无尽资源', 'key': 'wjzy', 'api': 'https://api.wujinapi.me/api.php/provide/vod/from/wjm3u8/', 'quality': 'HD'},
    {'name': '红牛资源', 'key': 'hnzy', 'api': 'https://www.hongniuzy2.com/api.php/provide/vod/from/hnm3u8/', 'quality': 'HD'},
    {'name': '金鹰资源', 'key': 'jyzy', 'api': 'https://jyzyapi.com/api.php/provide/vod/', 'quality': 'SD'},
]

# Keywords that indicate higher quality streams
_HD_KEYWORDS = ['1080', 'hd', '超清', '蓝光', '4k', 'uhd', 'ffm3u8', 'feifan']


_CN_NUM = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7, '八': 8, '九': 9, '十': 10}

def _extract_season(query):
    """Extract base title and season number from query like '剑来2' → ('剑来', 2)."""
    q = query.strip()
    # Match trailing season: "剑来2", "剑来第二季", "剑来 第2部"
    m = re.search(r'\s*[第]?([0-9一二三四五六七八九十]+)[季部]?\s*$', q)
    if m:
        num_str = m.group(1)
        base = q[:m.start()]
        if num_str in _CN_NUM:
            season = _CN_NUM[num_str]
        else:
            try:
                season = int(num_str)
            except ValueError:
                season = 0
        return (base if base else q, season)
    return (q, 0)


def _title_season_score(title, base_query, target_season):
    """Score how well a title matches the target season. Higher = better match."""
    if not target_season:
        return 0
    t = title.lower()
    # Check for season indicators in title
    season_patterns = [
        (rf'第{target_season}季', 10),
        (rf'第{target_season}部', 10),
    ]
    # Chinese numeral version
    cn_reverse = {v: k for k, v in _CN_NUM.items()}
    if target_season in cn_reverse:
        cn = cn_reverse[target_season]
        season_patterns.append((rf'第{cn}季', 10))
        season_patterns.append((rf'第{cn}部', 10))
    # "剑来第二季" style
    season_patterns.append((rf'{re.escape(base_query)}第.季', 8))
    season_patterns.append((rf'{re.escape(base_query)}第.部', 8))

    for pat, score in season_patterns:
        if re.search(pat, title):
            return score

    # If title is exactly the base (no season marker) = likely season 1
    if title == base_query or title == base_query + '第一季':
        return -5 if target_season != 1 else 5

    return 0


def _pick_best_episodes(play_urls, play_from=''):
    """Parse play URLs and pick the best quality group."""
    if not play_urls:
        return []
    groups = play_urls.split('$$$')
    froms = play_from.split('$$$') if play_from else [''] * len(groups)
    best_eps = []
    best_score = -1
    for i, group in enumerate(groups):
        grp_eps = []
        for ep in group.split('#'):
            parts = ep.split('$', 1)
            if len(parts) == 2 and parts[1].strip():
                ep_url = parts[1].strip()
                if ep_url.startswith('http'):
                    grp_eps.append({'name': parts[0], 'url': ep_url})
        if not grp_eps:
            continue
        # Score this group: prefer m3u8 URLs and HD keywords
        tag = (froms[i] if i < len(froms) else '').lower() + group[:200].lower()
        score = 0
        if 'm3u8' in tag or '.m3u8' in grp_eps[0]['url']:
            score += 10
        for kw in _HD_KEYWORDS:
            if kw in tag:
                score += 5
        if score > best_score:
            best_score = score
            best_eps = grp_eps
    return best_eps


def _title_match_score(title, original_query, base_query, target_season):
    """Score how well a result title matches the user's query. Higher = better."""
    t = title.strip()
    oq = original_query.strip()
    bq = base_query.strip()
    score = 0

    # Exact match is the best
    if t == oq:
        return 100

    # Title matches base query + correct season indicator
    if target_season:
        season_score = _title_season_score(t, bq, target_season)
        if season_score > 0:
            score += 50 + season_score
        elif season_score < 0:
            score -= 30  # Wrong season, heavily penalize
        # Title is exactly the base (no season) = probably season 1
        if t == bq:
            score += -20 if target_season > 1 else 40
    else:
        # No season specified — exact base match is best
        if t == bq:
            score += 60

    # Title contains the full original query
    if oq in t:
        score += 30
    elif bq in t:
        score += 15
    # Penalize titles much longer than query (likely unrelated, e.g. "美女总裁的保镖会剑来")
    if len(t) > len(bq) + 6:
        score -= 10
    # Title doesn't contain base query at all = irrelevant
    if bq not in t and t not in bq:
        score -= 50

    return score


def _fetch_source_results(src, search_query):
    """Fetch results from a single video source."""
    try:
        sep = '&' if '?' in src['api'] else '?'
        url = src['api'] + sep + 'ac=detail&wd=' + urllib.parse.quote(search_query)
        data = fetch(url, as_json=True)
        results = []
        for item in data.get('list', [])[:5]:
            play_urls = item.get('vod_play_url', '')
            play_from = item.get('vod_play_from', '')
            episodes = _pick_best_episodes(play_urls, play_from)
            if episodes:
                hits = 0
                try:
                    hits = int(item.get('vod_hits', 0) or item.get('vod_hits_day', 0) or 0)
                except (ValueError, TypeError):
                    pass
                results.append({
                    'id': item.get('vod_id'),
                    'title': item.get('vod_name', ''),
                    'type': item.get('type_name', ''),
                    'pic': item.get('vod_pic', ''),
                    'remarks': item.get('vod_remarks', ''),
                    'year': item.get('vod_year', ''),
                    'area': item.get('vod_area', ''),
                    'hits': hits,
                    'source': src['key'],
                    'source_name': src['name'],
                    'quality': src.get('quality', ''),
                    'episodes': episodes,
                })
        return results
    except Exception:
        return []


def video_search(query):
    """Search video sources with precise title matching."""
    original_query = query.strip()
    base_query, target_season = _extract_season(original_query)
    quality_rank = {'1080P': 4, 'HD': 3, 'SD': 1}

    all_results = []

    # Step 1: Try exact original query first (e.g. "剑来2" or "流浪地球2")
    for src in VIDEO_SOURCES:
        all_results.extend(_fetch_source_results(src, original_query))

    # Step 2: If original != base, also search with base query (e.g. "剑来")
    if base_query != original_query:
        existing_titles = {r['title'] for r in all_results}
        for src in VIDEO_SOURCES:
            for r in _fetch_source_results(src, base_query):
                if r['title'] not in existing_titles:
                    all_results.append(r)
                    existing_titles.add(r['title'])

    # Step 3: Filter out clearly irrelevant results
    filtered = [r for r in all_results if base_query in r['title'] or r['title'] in base_query]
    if not filtered:
        filtered = all_results

    # Step 4: Deduplicate by title — keep highest quality per title
    seen_titles = {}
    for r in filtered:
        t = r['title']
        q = quality_rank.get(r.get('quality', ''), 2)
        if t not in seen_titles or q > seen_titles[t][1]:
            seen_titles[t] = (r, q)
    deduped = [v[0] for v in seen_titles.values()]

    # Step 5: Sort by title match precision, then quality, then hits
    deduped.sort(key=lambda x: (
        _title_match_score(x['title'], original_query, base_query, target_season),
        quality_rank.get(x.get('quality', ''), 2),
        x.get('hits', 0)
    ), reverse=True)

    return deduped


def video_detail(source_key, vid):
    """Get video detail with play URLs from a specific source."""
    src = next((s for s in VIDEO_SOURCES if s['key'] == source_key), VIDEO_SOURCES[0])
    try:
        sep = '&' if '?' in src['api'] else '?'
        url = src['api'] + sep + 'ac=detail&ids=' + str(vid)
        data = fetch(url, as_json=True)
        if not data.get('list'):
            return {'error': 'not found'}
        item = data['list'][0]
        play_urls = item.get('vod_play_url', '')
        play_from = item.get('vod_play_from', '')
        episodes = _pick_best_episodes(play_urls, play_from)
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

    # M3U8 proxy (solve CORS)
    if path == 'proxy':
        m3u8_url = params.get('url', '')
        if not m3u8_url:
            return {'error': 'missing url'}
        return '__PROXY__' + m3u8_url

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

            # M3U8 proxy mode
            if isinstance(data, str) and data.startswith('__PROXY__'):
                m3u8_url = data[9:]
                m3u8_content = fetch(m3u8_url)
                # Rewrite relative URLs to absolute
                base_url = m3u8_url.rsplit('/', 1)[0] + '/'
                lines = []
                for line in m3u8_content.split('\n'):
                    line = line.strip()
                    if line and not line.startswith('#'):
                        if not line.startswith('http'):
                            line = base_url + line
                    lines.append(line)
                body = '\n'.join(lines).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'application/vnd.apple.mpegurl')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Cache-Control', 's-maxage=300')
                self.end_headers()
                self.wfile.write(body)
                return

            body = json.dumps(data, ensure_ascii=False).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Cache-Control', 's-maxage=1800, stale-while-revalidate=3600')
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            body = json.dumps({'error': str(e)}, ensure_ascii=False).encode('utf-8')
            self.send_response(500)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass  # Suppress logs in serverless
