# main.py
from fastapi import FastAPI, HTTPException
from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient
import fastapi
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from get_cluster import Cluster
from sync_cluster import get_clusters_from_clouds
from get_cluster import get_one_cluster_data, get_clusters_data
from fastapi.responses import JSONResponse
uri = "mongodb://localhost:27017"
db_name = "lyricinfra"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    client = AsyncIOMotorClient(uri)
    await init_beanie(
        database=client[db_name],
        document_models=[Cluster]  # Add all your Beanie models here
    )
    yield
    # Shutdown
    client.close()

app = FastAPI(
    title="Infrastructure Provisioning API",
    lifespan=lifespan,
    description="""
    Provides REST endpoints for Self Service Portal for Lyric Infra
    """,
    version="2.0.0",
    openapi_url="/api/openapi.json",
    default_response_class=fastapi.responses.ORJSONResponse  # To handle NaN in json response
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    print("Health check")
    try:
        return {"status": "healthy", "database": "connected"}
    except Exception:
        raise HTTPException(status_code=500, detail="Database not connected")

@app.get("/api/clusters/sync")
async def sync_clusters():
    clusters = await get_clusters_from_clouds()
    return clusters

@app.get("/api/clusters")
async def get_clusters():
    clusters = await get_clusters_data()
    return JSONResponse(content=clusters)

@app.get("/api/clusters/{cluster_id}")
async def get_cluster_details(cluster_id: str):  
    details = await get_one_cluster_data(cluster_id)
    return JSONResponse(content=details)

@app.post("/api/provision")
async def provision_cluster():
    return JSONResponse(content={"message": "Cluster provisioned successfully"})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)