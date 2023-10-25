from fastapi import FastAPI
from routers import anime, auth
from fastapi.middleware.cors import CORSMiddleware



tags_metadata = [
    {
        "name": "ANIME Endpoints",
        "description": "Anime Endpoints"
    },
    {
        "name": "USER",
        "description": "User Endpoints"
    }
]

app = FastAPI(
    title="BAnimeAPI",
    description="",
    version="1.0.0",
    openapi_tags=tags_metadata, 
    swagger_ui_parameters={"defaultModelsExpandDepth": -1}
)

app.include_router(anime.router, prefix='/anime')
app.include_router(auth.router, prefix='/auth')

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)