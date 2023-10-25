import helpers.mongodb as mongodb
import requests
import json
import yarl
import re
import time


ALLANIME_API = "https://api.allanime.co/"
ALLANIME_WATCH = "https://allanime.to/"
ALLANIME_HEADERS = {
    "User-Agent": "blank/0.0.1", 
    "referer": ALLANIME_API
}
ONE_WEEK_IN_SECONDS = 604800
SOURCE_URLS = re.compile(r'sourceUrl[:=]"(?P<url>.+?)"[;,](?:.+?\.)?priority[:=](?P<priority>.+?)[;,](?:.+?\.)?sourceName[:=](?P<name>.+?)[,;]')
WIXMP_URL_REGEX = re.compile(r"https://.+?/(?P<base>.+?/),(?P<resolutions>(?:\d+p,)+)")


def to_json_url(url: "yarl.URL"):
    return url.with_name(url.name + ".json").with_query(url.query)


def parse_hls(url):
    stream_urls = []
    for link in url:
        if 'gofcdn' in link['link'] or '//cache.' in link['link']:
            source = {
                'type': 'hls',
                'sources': {'0': link['link']}
            }

            stream_urls.append(source)

    return stream_urls


def parse_sharepoint(url):
    stream_urls = {}
    for link in url:
        stream_urls['0'] = link['link']

    return {
        'type': 'mp4',
        'sources': stream_urls
    }


def parse_wixstatic(url):
    yarled_url = yarl.URL(url[0].get('link'))

    match = WIXMP_URL_REGEX.search(yarled_url.human_repr())

    if match is None:
        return

    base_url = match.group("base")

    temp = {
        'type': 'mp4',
        'sources': {}
    }

    for resolution in match.group("resolutions").split(",")[:-1]:
        temp['sources'][resolution.replace('p', '')] = f"https://{base_url}{resolution}/mp4/file.mp4"

    return temp


def parse_aapro(url):
    quality_conversion = {
        "1920": "1080",
        "1280": "720",
        "854": "480",
        "480": "360"
    }

    obj = {
        'type': 'mp4',
        'sources': {}
    }

    for link in url:
        obj['sources'][quality_conversion[str(link['resolution'])]] = link['link']

    return obj


def get_allanime_episode_data(anime_id):
    ep_data = mongodb.allanime_episode_data_collection.find_one({'mal_id': anime_id}, {'_id': False})
    if ep_data:
        if (int(time.time()) - ep_data['cached']) < ONE_WEEK_IN_SECONDS:
            return ep_data

    doc = mongodb.id_collection.find_one({'mal_id': anime_id}, {'_id': False})
    if doc:
        if doc.get('anilist_id'):
            name_query = "query ($id: Int) { Media (id: $id, type: ANIME) {id title{english romaji native}}}"
            r = requests.post('https://graphql.anilist.co', json={"query": name_query, "variables": {
                "id": doc['anilist_id'][0]
            }}, )

            data = r.json()
            name = data['data']['Media']['title']['english']
            
            if not name:
                if not data['data']['Media']['title']['romaji']:
                    return None

                name = data['data']['Media']['title']['romaji']
            try:
                r = requests.get(ALLANIME_API + "allanimeapi", params={
                    "variables": json.dumps(
                        {
                            "search": {
                                "allowAdult": True,
                                "allowUnknown": True,
                                "query": name,
                            },
                            "limit": 40,
                        }
                    ),
                    "extensions": json.dumps(
                        {
                            "persistedQuery": {
                                "version": 1,
                                "sha256Hash": "9c7a8bc1e095a34f2972699e8105f7aaf9082c6e1ccd56eab99c2f1a971152c6",
                            }
                        }
                    )
                }, headers=ALLANIME_HEADERS)
            except requests.exceptions.RequestException as e:
                return {"error": f"Exception {e}"}

            search_data = r.json()
            
            for x in search_data['data']['shows']['edges']:
                if x.get('englishName') == name:
                    allanime_id = x.get('_id')
                    obj = {
                        'mal_id': anime_id,
                        'allanime_id': allanime_id,
                        'cached': int(time.time()),
                        'latest_episode_data': {
                            'sub': None,
                            'dub': None,
                            'raw': None
                        }
                    }

                    if x.get('lastEpisodeInfo'):
                        if x['lastEpisodeInfo'].get('sub'):
                            obj['latest_episode_data']['sub'] = int(float(x.get('lastEpisodeInfo').get('sub').get('episodeString')))
                        if x['lastEpisodeInfo'].get('dub'):
                            obj['latest_episode_data']['dub'] = int(float(x.get('lastEpisodeInfo').get('dub').get('episodeString')))
                        if x['lastEpisodeInfo'].get('raw'):
                            obj['latest_episode_data']['raw'] = int(float(x.get('lastEpisodeInfo').get('raw').get('episodeString')))

                    found = mongodb.allanime_episode_data_collection.find_one({'mal_id': anime_id})
                    if found:
                        if (int(time.time() - found['cached']) > ONE_WEEK_IN_SECONDS):
                            mongodb.allanime_episode_data_collection.find_one_and_replace({'mal_id': anime_id}, obj)    
                    else:
                        mongodb.allanime_episode_data_collection.insert_one(obj)
                    
                    if obj.get('_id'):
                        del obj['_id']

                    return obj
                
    return None


def get_allanime_id(anime_id):
    id = mongodb.allanime_id_collection.find_one({'mal_id': anime_id}, {'_id': False})
    if id:
        return id['allanime_id']

    doc = mongodb.id_collection.find_one({'mal_id': anime_id}, {'_id': False})
    if doc['anilist_id']:
        name_query = "query ($id: Int) { Media (id: $id, type: ANIME) {id title{english}}}"
        r = requests.post('https://graphql.anilist.co', json={"query": name_query, "variables": {
            "id": doc['anilist_id'][0]
        }}, )

        name = r.json()['data']['Media']['title']['english']

        r = requests.get(ALLANIME_API + "allanimeapi", params={
            "variables": json.dumps(
                {
                    "search": {
                        "allowAdult": True,
                        "allowUnknown": True,
                        "query": name,
                    },
                    "limit": 40,
                }
            ),
            "extensions": json.dumps(
                {
                    "persistedQuery": {
                        "version": 1,
                        "sha256Hash": "9c7a8bc1e095a34f2972699e8105f7aaf9082c6e1ccd56eab99c2f1a971152c6",
                    }
                }
            )
        }, headers=ALLANIME_HEADERS)

        search_data = r.json()
        for x in search_data['data']['shows']['edges']:
            if x.get('englishName') == name:
                allanime_id = x.get('_id')
                
                obj = {
                    'mal_id': anime_id,
                    'allanime_id': allanime_id
                }

                mongodb.allanime_id_collection.insert_one(obj)
                return allanime_id

    return None


def get_allanime_sources(anime_id, episode_number):
    r = requests.get(ALLANIME_WATCH + f'watch/{anime_id}/episode-{episode_number}-sub', headers=ALLANIME_HEADERS)
    if r.status_code != 200:
        return None

    content = r.text

    providers = []
    for source in SOURCE_URLS.finditer(content):
        raw = source.group(1).encode("utf-8").decode("unicode_escape")
        parsed = yarl.URL(raw)
        if parsed.host is None:
            new_url = to_json_url(parsed)
            providers.append('https://allanimenews.com' + str(new_url))
    
    all_sources = []
    for provider in providers:
        r = requests.get(provider)
        if r.status_code == 200:
            data = r.json()['links']
            for x in data:
                if 'allanime.pro' in x['link']:
                    sources = parse_aapro(data)
                    all_sources.append(sources)
                    break

                if 'wixmp' in x['link']:
                    sources = parse_wixstatic(data)
                    all_sources.append(sources)
                    break

                if 'myanime.sharepoint' in x['link']:
                    sources = parse_sharepoint(data)
                    all_sources.append(sources)
                    break

                if x.get('hls') is True:
                    sources = parse_hls(data)
                    if sources:
                        for x in sources:
                            all_sources.append(x)
                    break

    return all_sources
