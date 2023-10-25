from pymongo import MongoClient
from dotenv import dotenv_values

config = dotenv_values(".env")
client = MongoClient(config.get('MONGODB_CONNECTION_STRING'))

# ANIME DATABASE
db = client['ANIME']
jikan_collection = db['jikan_collection']
cache_collection = db['seasonal_cache']
top_collection = db['top_cache']
id_collection = db['id_collection']
allanime_source_collection = db['allanime_sources']
episode_data_collection = db['mal_episode_data']
livechart_collection = db['livechart_timetable']
recommendations_collection = db['mal_recommendations']
statistics_collection = db['mal_statistics']
allanime_id_collection = db['allanime_ids']
anilist_cache_collection = db['anilist_cache']
allanime_episode_data_collection = db['allanime_episode_info']
cache_time_info_collection = db['cache_time_info']
anime_skip_collection = db['animeskip_data']
allanime_cache_collection = db['allanime_cache']
jikan_collection.create_index([('title', 'text')])
# USER DATABASE
db = client['USER']
