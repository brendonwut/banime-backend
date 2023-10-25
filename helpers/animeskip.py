import requests
import helpers.mongodb as mongodb
import time 
from dotenv import dotenv_values



config = dotenv_values(".env")

headers = {
    "X-Client-ID": config.get('ANIMESKIP_CLIENT_ID'),
    "Content-Type": "application/json"
}

SEARCH_SHOWS_QUERY = """
    query search($search: String, $limit: Int) {
        searchShows(search:$search, limit:$limit)
        {
            id
            name
        }
    }
"""

FIND_TIMESTAMPS_QUERY = """
query x($showId: ID!) {
    findEpisodesByShowId(showId:$showId) {
        id
        name
        show {
            id
        }
        number
        timestamps {
            at
            type {
                description
            } 
            typeId
        }
    }
}
"""


def search_anime(name):
    query_variables = {
        "search": name,
        "limit": 10
    }

    r = requests.post('https://api.anime-skip.com/graphql', headers=headers, json={"query": SEARCH_SHOWS_QUERY, "variables": query_variables})

    return r.json()


def find_timestamps(id):
    query_variables = {
        "showId": id
    }

    r = requests.post('https://api.anime-skip.com/graphql', headers=headers, json={"query": FIND_TIMESTAMPS_QUERY, "variables": query_variables})
    return r.json()


def check_cache(anime_id):
    last_cached = mongodb.cache_time_info_collection.find_one({'mal_id': anime_id, 'type': 'timestamps'})
    if last_cached:
        if (int(time.time()) - last_cached['cached']) < 86400:
            return None
        
        mongodb.cache_time_info_collection.find_one_and_replace({'mal_id': anime_id, 'type': 'timestamps'}, {
            'mal_id': anime_id,
            'type': 'timestamps',
            'cached': int(time.time())
        })
        cache_timestamps(anime_id)
    else:
        mongodb.cache_time_info_collection.insert_one({
            'mal_id': anime_id,
            'type': 'timestamps',
            'cached': int(time.time())
        })

        cache_timestamps(anime_id)


def cache_timestamps(anime_id):
    doc = mongodb.id_collection.find_one({'mal_id': anime_id}, {'_id': False})
    if doc:
        if doc.get('anilist_id'):
            name_query = "query ($id: Int) { Media (id: $id, type: ANIME) {id title{english romaji native}}}"
            r = requests.post('https://graphql.anilist.co', json={"query": name_query, "variables": {
                "id": doc['anilist_id'][0]
            }}, )

            data = r.json()
            name = data['data']['Media']['title']['english'].lower()

            if name:
                id = search_anime(name)
                for x in id['data']['searchShows']:
                    if x['name'].lower() == name:
                        timestamps = find_timestamps(x['id'])
                        if timestamps:
                            for ep in timestamps['data']['findEpisodesByShowId']:
                                if ep.get('number'):
                                    if ep.get('timestamps'):
                                        ep['episode'] = int(ep['number'])
                                        ep['mal_id'] = anime_id
                                        del ep['number']
                                        doc2 = mongodb.anime_skip_collection.find_one({'mal_id': anime_id, 'episode': ep['episode']})
                                        if doc2:
                                            mongodb.anime_skip_collection.find_one_and_replace({'mal_id': anime_id, 'episode': ep['episode']}, ep)
                                        else:
                                            mongodb.anime_skip_collection.insert_one(ep)

                            return None
                                    


