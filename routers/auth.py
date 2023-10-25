from fastapi import APIRouter, Body
import secrets
import requests
import helpers.mongodb as mongodb
from dotenv import dotenv_values



config = dotenv_values(".env")

router = APIRouter(tags=["AUTH"])


@router.get("/myanimelist")
async def mal_link():
    token = secrets.token_urlsafe(100)
    state_token = secrets.token_urlsafe(16)
    code_challenge = token[:128]
    state = state_token[:16]
    
    mal_auth_link = f"https://myanimelist.net/v1/oauth2/authorize?response_type=code&client_id=040689570d3e9b69a7899d8ce769ae8f&code_challenge={code_challenge}&state={state}"

    return {
        "data": {
            "link": mal_auth_link
        }
    }


@router.get("/myanimelist/token")
async def mal_token(code: str = Body(...), code_verifier: str = Body(...), state: str = Body(default=None)):
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": "banime"
    }

    data = {
        "client_id": config.get("MAL_CLIENT_ID"),
        "client_secret": config.get("MAL_CLIENT_SECRET"),
        "code": code,
        "code_verifier": code_verifier,
        "grant_type": "authorization_code"
    }

    r = requests.post("https://myanimelist.net/v1/oauth2/token", data=data, headers=headers)
    
    return r.json()


@router.post("/kitsu")
async def kitsu_link(username: str = Body(...), password: str = Body(...)):
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "banime"
    }

    data = {
        "grant_type": "password",
        "username": username,
        "password": password
    }

    r = requests.post("https://kitsu.io/api/oauth/token", json=data, headers=headers)
    
    return r.json()


@router.get("/anilist")
async def anilist():
    client_id = config.get("ANILIST_CLIENT_ID")
    redirect_uri = "https://anime.blank.gg/"
    url = f"https://anilist.co/api/v2/oauth/authorize?client_id={client_id}&redirect_uri={redirect_uri}&response_type=code"

    return {
        'data': {
            'link': url
        }
    }


@router.get("/anilist/token")
async def anilist_token(code: str):
    client_id = config.get("ANILIST_CLIENT_ID")
    client_secret = config.get("ANILIST_CLIENT_SECRET")
    redirect_uri = "https://anime.blank.gg/"
    headers = {
        "Content-Type": "application/json",
        'Accept': 'application/json'
    }

    json = {
        "grant_type": "authorization_code",
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "redirect_uri": redirect_uri
    }
    
    r = requests.post("https://anilist.co/api/v2/oauth/token", json=json, headers=headers)

    return r.json()
