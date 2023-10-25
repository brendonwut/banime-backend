from fastapi import APIRouter, BackgroundTasks, status
from fastapi.responses import JSONResponse 
import helpers.mongodb as mongodb
import math
import requests
import re
import helpers.allanime as allanime
import helpers.animeskip as animeskip
import bson.json_util as json_util
import time
import pytz
from datetime import datetime
from Levenshtein import distance as levenstein_distance



TOKYO_TZ = pytz.timezone('Asia/Tokyo')
DATE_REGEX = "(\d{4})/(\d{1,2})/(\d{1,2})"
ONE_WEEK_IN_SECONDS = 604800
ONE_DAY_IN_SECONDS = 86400


router = APIRouter(tags=["BANIME"])


def scrape_all_data(anime_id):
    page_start = 1
    page_end = page_start
    while page_start <= page_end:
        time.sleep(1)
        r = requests.get(f'https://api.jikan.moe/v4/anime/{anime_id}/episodes?page={page_start}')
        data = r.json()
        page_end = data['pagination']['last_visible_page']

        for episode in data['data']:
            episode['episode'] = episode['mal_id']
            episode['mal_id'] = anime_id

            found = mongodb.episode_data_collection.find_one({'mal_id': anime_id, 'episode': episode['episode']})
            if not found:
                mongodb.episode_data_collection.insert_one(json_util.loads(json_util.dumps(episode)))

        page_start += 1


@router.get('/search')
async def search_anime(query: str | None = None, page: int | None = 1, limit: int | None = 5):
    query_str = ""
    qs = query.split(" ")
    for x in qs:
        query_str += x + ".*"
    
    doc = mongodb.jikan_collection.find({"title": { "$regex": f".*{query_str}", "$options": 'i'}}, {'_id': False})
    #testdoc = mongodb.jikan_collection.find({"$text": {"$search": f"\"{query.strip()}\""}}).limit(limit)
    retarray = {"data": []}
    for x in doc:
        json = {
            'mal_id': x['mal_id'],
            'title': x['title'],
            'status': x['status'],
            'images': x['images'],
            'levenshtein': levenstein_distance(query, x['title'])
        }
        
        if x['season'] and x['year']:
            json['season'] =  str(x['season']).capitalize() + " " + str(x['year'])
        else:
            json['season'] = None

        retarray['data'].append(json)

    sortedarray = sorted(retarray['data'], key=lambda x: x.get('levenshtein'))
    total_results = len(sortedarray)
    start = (page - 1) * limit
    end = start + limit

    return {
        'data': sortedarray[start:end],
        'pagination': {
            'results': len(sortedarray[start:end]),
            'total_results': total_results,
            'current_page': page,
            'total_pages': math.ceil(total_results / limit)
        }
    }


@router.get('/season/{year}/{season}')
async def get_seasonal_anime(year: int, season: str, limit: int | None = 25, page: int | None = 1):
    seasons = ['winter', 'fall', 'summer', 'spring']
    if season not in seasons or year > 2023 or year < 1917:
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={
            'error': 'Invalid year or season'
        })

    result = mongodb.cache_collection.aggregate([{"$match": {"year": year, "season": season}}, {"$project": {"_id": False, "count":{"$size": "$data"}}}])
    try:
        total_results = list(result)[0]['count']
    except:
        return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={
            'error': 'Could not find seasonal data'
        })
    
    num_to_skip = limit * (page - 1)
    doc = mongodb.cache_collection.find_one({'year': year, 'season': season}, {"data": {"$slice": [num_to_skip, limit]}, '_id': False})

    doc['pagination'] = {
        'results': len(doc['data']),
        'total_results': total_results,
        'current_page': page,
        'total_pages': math.ceil(total_results / limit)
    }

    return doc


@router.get('/season/now')
async def get_seasonal_now(limit: int | None = 25, page: int | None = 1):
    result = mongodb.cache_collection.aggregate([{"$match": {"year": 2023, "season": 'winter'}}, {"$project": {"_id": False, "count":{"$size": "$data"}}}])
    try:
        total_results = list(result)[0]['count']
    except:
        return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={
            'error': 'Could not find seasonal data'
        })

    num_to_skip = limit * (page - 1)
    doc = mongodb.cache_collection.find_one({'year': 2023, 'season': 'winter'}, {"data": {"$slice": [num_to_skip, limit]}, '_id': False})

    doc['pagination'] = {
        'results': len(doc['data']),
        'total_results': total_results,
        'current_page': page,
        'total_pages': math.ceil(total_results / limit)
    }

    return doc


@router.get('/season')
async def get_season_list():
    doc = mongodb.cache_collection.find_one({'type': 'season_list'}, {'_id': False})

    return doc


@router.get('/top/{list_type}')
async def get_top_anime(list_type: str, limit: int | None = 25, page: int | None = 1):
    result = mongodb.top_collection.aggregate([{"$match": {"type": list_type}}, {"$project": {"_id": False, "count":{"$size": "$data"}}}])
    total_results = list(result)[0]['count']

    num_to_skip = limit * (page - 1)
    doc = mongodb.top_collection.find_one({'type': list_type}, {"data": {"$slice": [num_to_skip, limit]}, '_id': False})

    doc['pagination'] = {
        'results': len(doc['data']),
        'total_results': total_results,
        'current_page': page,
        'total_pages': math.ceil(total_results / limit)
    }

    return doc


@router.get('/recent')
async def get_recent_anime():
    result = mongodb.allanime_cache_collection.find_one({"type": "recently_updated"}, {'_id': False})
    if not result:
        return None

    return result


@router.get('/{anime_id}/timestamps/{episode}')
async def get_episode_timestamps(anime_id: int, episode: int, background_tasks: BackgroundTasks = BackgroundTasks()):
    found = mongodb.anime_skip_collection.find_one({'mal_id': anime_id, 'episode': episode}, {'_id': False})
    if not found:
        background_tasks.add_task(animeskip.check_cache, anime_id)
        return None

    obj = {
        'data': {
            'mal_id': found.get('mal_id'),
            'episode': found.get('episode'),
            'timestamps': []
        }
    }

    for x in found['timestamps']:
        if x['typeId'] == "14550023-2589-46f0-bfb4-152976506b4c":
            obj['data']['timestamps'].append({
                'type': 'opening',
                'at': x['at']
            })

        if x['typeId'] == "2a730a51-a601-439b-bc1f-7b94a640ffb9":
            obj['data']['timestamps'].append({
                'type': 'ending',
                'at': x['at']
            })

    background_tasks.add_task(animeskip.check_cache, anime_id)

    return obj

            
@router.get('/{anime_id}/source/{episode}')
async def get_episode_source(anime_id: int, episode: int):
    source_found = mongodb.allanime_source_collection.find_one({'mal_id': anime_id, "episode": episode}, {'_id': False})
    if source_found:
        obj = {
            'data': source_found
        }

        return obj

    allanime_id = allanime.get_allanime_id(anime_id)
    sources = allanime.get_allanime_sources(allanime_id, episode)

    mal_data = mongodb.jikan_collection.find_one({'mal_id': anime_id}, {'_id': False})
    if mal_data['title_english']:
        anime_title = mal_data['title_english']
    else:
        anime_title = mal_data['title']

    obj = {
        "mal_id": anime_id,
        "title": anime_title,
        "episode": episode,
        'cached': int(time.time()),
        'sources': sources
    }

    mongodb.allanime_source_collection.insert_one(obj)
    del obj['_id']

    return {
        'data': obj
    }


@router.get('/timetable')
async def get_timetable(date: str | None = datetime.now(TOKYO_TZ).strftime('%Y/%m/%d')):
    utc = datetime(1970, 1, 1, tzinfo=pytz.utc)
    date = re.search(DATE_REGEX, date)

    if not date:
        return None

    year = int(date.group(1))
    month = int(date.group(2))
    day = int(date.group(3))

    dt_tz_lower = TOKYO_TZ.localize(datetime(year, month, day, 0), is_dst=None)
    dt_tz_upper = TOKYO_TZ.localize(datetime(year, month, day, 23, 59, 59), is_dst=None)
    ts_lower = (dt_tz_lower - utc).total_seconds()
    ts_upper = (dt_tz_upper - utc).total_seconds()
    
    eps = mongodb.livechart_collection.find({"epoch": { "$gte": int(ts_lower), "$lte": int(ts_upper) }}, {'_id': False}).sort('epoch', 1)
    
    return {
        'data': list(eps)
    }


@router.get('/anilist/trending')
async def get_anilist_trending(page: int | None = 1, limit: int | None = 10):
    trending = mongodb.anilist_cache_collection.find_one({'type': 'trending'}, {"data": {"$slice": [limit * (page - 1), limit]}, '_id': False})
    if trending:
        if (int(time.time()) - trending['cached']) < ONE_DAY_IN_SECONDS:
            trending['pagination'] = {
                'results': len(trending['data']),
                'total_results': 50,
                'current_page': page,
                'total_pages': math.ceil(50 / limit)
            }

            return trending 

    query = "query($page:Int, $perPage:Int, $id:Int $type:MediaType $isAdult:Boolean = false $search:String $format:[MediaFormat]$status:MediaStatus $countryOfOrigin:CountryCode $source:MediaSource $season:MediaSeason $seasonYear:Int $year:String $onList:Boolean $yearLesser:FuzzyDateInt $yearGreater:FuzzyDateInt $episodeLesser:Int $episodeGreater:Int $durationLesser:Int $durationGreater:Int $chapterLesser:Int $chapterGreater:Int $volumeLesser:Int $volumeGreater:Int $licensedBy:[Int]$isLicensed:Boolean $genres:[String]$excludedGenres:[String]$tags:[String]$excludedTags:[String]$minimumTagRank:Int $sort:[MediaSort]=[POPULARITY_DESC,SCORE_DESC]){Page(page:$page,perPage:$perPage){pageInfo{total perPage currentPage lastPage hasNextPage}media(id:$id type:$type season:$season format_in:$format status:$status countryOfOrigin:$countryOfOrigin source:$source search:$search onList:$onList seasonYear:$seasonYear startDate_like:$year startDate_lesser:$yearLesser startDate_greater:$yearGreater episodes_lesser:$episodeLesser episodes_greater:$episodeGreater duration_lesser:$durationLesser duration_greater:$durationGreater chapters_lesser:$chapterLesser chapters_greater:$chapterGreater volumes_lesser:$volumeLesser volumes_greater:$volumeGreater licensedById_in:$licensedBy isLicensed:$isLicensed genre_in:$genres genre_not_in:$excludedGenres tag_in:$tags tag_not_in:$excludedTags minimumTagRank:$minimumTagRank sort:$sort isAdult:$isAdult){id idMal title{english romaji native}coverImage{extraLarge large color}startDate{year month day}endDate{year month day}bannerImage season seasonYear description type format status(version:2)episodes duration chapters volumes genres isAdult averageScore popularity nextAiringEpisode{airingAt timeUntilAiring episode}mediaListEntry{id status}studios(isMain:true){edges{isMain node{id name}}}}}}"
    query_variables = {
        "page": page, 
        "perPage": 50, 
        "type": "ANIME", 
        "sort": ["TRENDING_DESC", "POPULARITY_DESC"]
    }

    r = requests.post('https://graphql.anilist.co/', json={"query": query, "variables": query_variables})

    mal_array = []
    for x in r.json()['data']['Page']['media']:
        mal_doc = mongodb.jikan_collection.find_one({'mal_id': x['idMal']}, {'_id': False})
        if mal_doc:
            mal_doc['bannerImage'] = x['bannerImage']
            mal_array.append(mal_doc)
    
    obj = {
        'type': 'trending',
        'cached': int(time.time()),
        'data': mal_array
    }

    mongodb.anilist_cache_collection.find_one_and_replace({'type': 'trending'}, obj)
    
    new_doc = mongodb.anilist_cache_collection.find_one({'type': 'trending'}, {"data": {"$slice": [limit * (page - 1), limit]}})
    del new_doc['_id']

    return new_doc


@router.get('/anilist/popular')
async def get_anilist_popular(page: int | None = 1, limit: int | None = 10):
    popular = mongodb.anilist_cache_collection.find_one({'type': 'popular'}, {"data": {"$slice": [limit * (page - 1), limit]}, '_id': False})
    if popular:
        if (int(time.time()) - popular['cached']) < ONE_DAY_IN_SECONDS:
            popular['pagination'] = {
                'results': len(popular['data']),
                'total_results': 50,
                'current_page': page,
                'total_pages': math.ceil(50 / limit)
            }

            return popular

    query = "query($page:Int, $perPage:Int $id:Int $type:MediaType $isAdult:Boolean = false $search:String $format:[MediaFormat]$status:MediaStatus $countryOfOrigin:CountryCode $source:MediaSource $season:MediaSeason $seasonYear:Int $year:String $onList:Boolean $yearLesser:FuzzyDateInt $yearGreater:FuzzyDateInt $episodeLesser:Int $episodeGreater:Int $durationLesser:Int $durationGreater:Int $chapterLesser:Int $chapterGreater:Int $volumeLesser:Int $volumeGreater:Int $licensedBy:[Int]$isLicensed:Boolean $genres:[String]$excludedGenres:[String]$tags:[String]$excludedTags:[String]$minimumTagRank:Int $sort:[MediaSort]=[POPULARITY_DESC,SCORE_DESC]){Page(page:$page,perPage:$perPage){pageInfo{total perPage currentPage lastPage hasNextPage}media(id:$id type:$type season:$season format_in:$format status:$status countryOfOrigin:$countryOfOrigin source:$source search:$search onList:$onList seasonYear:$seasonYear startDate_like:$year startDate_lesser:$yearLesser startDate_greater:$yearGreater episodes_lesser:$episodeLesser episodes_greater:$episodeGreater duration_lesser:$durationLesser duration_greater:$durationGreater chapters_lesser:$chapterLesser chapters_greater:$chapterGreater volumes_lesser:$volumeLesser volumes_greater:$volumeGreater licensedById_in:$licensedBy isLicensed:$isLicensed genre_in:$genres genre_not_in:$excludedGenres tag_in:$tags tag_not_in:$excludedTags minimumTagRank:$minimumTagRank sort:$sort isAdult:$isAdult){id idMal title{english romaji native}coverImage{extraLarge large color}startDate{year month day}endDate{year month day}bannerImage season seasonYear description type format status(version:2)episodes duration chapters volumes genres isAdult averageScore popularity nextAiringEpisode{airingAt timeUntilAiring episode}mediaListEntry{id status}studios(isMain:true){edges{isMain node{id name}}}}}}"
    query_variables = {
        "page": page, 
        "perPage": 50, 
        "type": "ANIME", 
        "season": "WINTER", 
        "sort": ["TRENDING_DESC", "POPULARITY_DESC"], 
        "seasonYear": 2023
    }

    r = requests.post('https://graphql.anilist.co/', json={"query": query, "variables": query_variables})

    obj = {
        'type': 'popular',
        'cached': int(time.time()),
        'data': r.json()['data']['Page']['media']
    }

    mongodb.anilist_cache_collection.find_one_and_replace({'type': 'popular'}, obj)

    new_doc = mongodb.anilist_cache_collection.find_one({'type': 'popular'}, {"data": {"$slice": [limit * (page - 1), limit]}, '_id': False})

    return new_doc
    

@router.get('/{anime_id}')
async def get_anime_by_id(anime_id: int):
    doc = mongodb.jikan_collection.find_one({'mal_id': anime_id}, {'_id': False})
    doc2 = mongodb.id_collection.find_one({'mal_id': anime_id}, {'_id': False})
    
    if not doc['episodes']:
        doc['episodes'] = doc2['episodes']

    if doc.get('kitsu_cover'):
        return {
            'data': doc
        }

    if not doc2.get('kitsu_id'):
        doc['kitsu_cover'] = None
        return {
            'data': doc
        }

    r = requests.get(f'https://kitsu.io/api/edge/anime/{doc2["kitsu_id"][0]}')
    kitsu_data = r.json()
    cover = kitsu_data['data']['attributes']['coverImage']
    doc['kitsu_cover'] = cover
    mongodb.jikan_collection.find_one_and_update({'mal_id': anime_id}, {"$set": { "kitsu_cover": cover }})

    return {
        'data': doc
    }


@router.get('/{anime_id}/recommendations')
async def get_anime_recommendations(anime_id: int, limit: int | None = 10, page: int | None = 1):
    doc = mongodb.recommendations_collection.find_one({'mal_id': anime_id}, {"data": {"$slice": [limit * (page - 1), limit]}, '_id': False})
    if doc:
        if (int(time.time()) - doc['cached']) < ONE_DAY_IN_SECONDS:
            sizedoc = mongodb.recommendations_collection.aggregate([{"$match": {'mal_id': anime_id}}, {"$project": {"_id": False, "count":{"$size": "$data"}}}])
            total_results = list(sizedoc)[0]['count']

            doc['pagination'] = {
                'results': len(doc['data']),
                'total_results': total_results,
                'current_page': page,
                'total_pages': math.ceil(total_results / limit)
            }

            return doc

    r = requests.get(f'https://api.jikan.moe/v4/anime/{anime_id}/recommendations')
    
    data = r.json()['data']
    
    obj = {
        'mal_id': anime_id,
        'data': []
    }

    for entry in data:
        temp = {
            'mal_id': entry['entry']['mal_id'],
            'images': entry['entry']['images']
        }

        jdoc = mongodb.jikan_collection.find_one({'mal_id': entry['entry']['mal_id']}, {'_id': False})
        if jdoc:
            if jdoc['title_english']:
                temp['title'] = jdoc['title_english']
            else:
                temp['title'] = jdoc['title']
        else:
            temp['title'] = entry['entry']['title']

        obj['data'].append(temp)

    obj['cached'] = int(time.time())
    mongodb.recommendations_collection.insert_one(obj)

    sizedoc = mongodb.recommendations_collection.aggregate([{"$match": {'mal_id': anime_id}}, {"$project": {"_id": False, "count":{"$size": "$data"}}}])
    total_results = list(sizedoc)[0]['count']

    res = mongodb.recommendations_collection.find_one({'mal_id': anime_id}, {"data": {"$slice": [limit * (page - 1), limit]}, '_id': False})
    res['pagination'] = {
        'results': len(res['data']),
        'total_results': total_results,
        'current_page': page,
        'total_pages': math.ceil(total_results / limit)
    }

    return res


@router.get('/{anime_id}/statistics')
async def get_anime_statistics(anime_id: int):
    doc = mongodb.statistics_collection.find_one({'mal_id': anime_id}, {'_id': False})
    if doc:
        if (int(time.time()) - doc['cached']) < ONE_DAY_IN_SECONDS:
            return doc

    r = requests.get(f'https://api.jikan.moe/v4/anime/{anime_id}/statistics')

    obj = {
        'mal_id': anime_id,
        'cached': int(time.time()),
        'data': r.json()['data']
    }

    if doc:
        filter = {'mal_id': anime_id}
        mongodb.statistics_collection.find_one_and_replace(filter, obj, {'_id': False})
        new_doc = mongodb.statistics_collection.find_one(filter)
        return new_doc
    
    mongodb.statistics_collection.insert_one(obj)
    del obj['_id']

    return obj


@router.get('/{anime_id}/episode')
async def get_anime_episode_data(anime_id: int, page: int | None = 1, limit: int | None = 13, background_tasks: BackgroundTasks = BackgroundTasks()): 
    allanime_doc = allanime.get_allanime_episode_data(anime_id)
    if not allanime_doc:
        return {
            "Error": "Does not exist"
        }

    obj = {
        'data':{},
        "pagination": {
            'results': None,
            'current_page': page
        },
        'allanime_info': allanime_doc
    }

    if page == 1:
        lower_limit = 0
    else:
        lower_limit = (page - 1) * limit

    upper_limit = limit * page

    cached_count = mongodb.episode_data_collection.count_documents({'mal_id': anime_id, 'episode': { "$gt": lower_limit, "$lte": upper_limit }})
    if cached_count > 0:
        doc = mongodb.episode_data_collection.find({'mal_id': anime_id, 'episode': { "$gt": lower_limit, "$lte": upper_limit }}, {'_id': False})
        for x in doc:
            obj['data'][x['episode']] = x 

        obj['pagination']['results'] = len(obj['data'])
    else:
        page_start = 1
        page_end = math.ceil(upper_limit / 100) 

        if math.ceil(lower_limit / 100) > 0:
            page_start = math.ceil(lower_limit / 100)

        all_eps = []
        while page_start <= page_end:
            r = requests.get(f'https://api.jikan.moe/v4/anime/{anime_id}/episodes?page={page_start}')
            data = r.json()['data']

            eps = [ep for ep in data if ep['mal_id'] > lower_limit and ep['mal_id'] <= upper_limit]
            all_eps.extend(eps)
            
            page_start += 1

        for eps in all_eps:
            eps['episode'] = eps['mal_id']
            eps['mal_id'] = anime_id
            obj['data'][eps['episode']] = eps

            found = mongodb.episode_data_collection.find_one({'mal_id': anime_id, 'episode': eps['episode']})
            if not found:
                mongodb.episode_data_collection.insert_one(json_util.loads(json_util.dumps(eps)))

        obj['pagination']['results'] = len(obj['data'])

    total_results = mongodb.episode_data_collection.count_documents({'mal_id': anime_id})
    obj['pagination']['total_results'] = total_results
    obj['pagination']['total_pages'] = math.ceil(total_results / limit)

    cti = mongodb.cache_time_info_collection.find_one({'mal_id': anime_id, 'type': 'episode_data'})
    if cti:
        if (int(time.time() - cti['cached']) > ONE_WEEK_IN_SECONDS):
            background_tasks.add_task(scrape_all_data, anime_id)
            mongodb.cache_time_info_collection.find_one_and_replace({'mal_id': anime_id}, {'mal_id': anime_id, 'type': 'episode_data', 'cached': int(time.time())})
    else:
        mongodb.cache_time_info_collection.insert_one({
            'mal_id': anime_id,
            'type': 'episode_data',
            'cached': int(time.time())
        })
        background_tasks.add_task(scrape_all_data, anime_id)

    return obj