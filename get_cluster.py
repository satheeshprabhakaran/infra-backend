from beanie import Document, Indexed, init_beanie
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime, timedelta, UTC
from typing import List, Dict, Optional
from pydantic import BaseModel
from logger import logger
# Models
class NodeGroup(BaseModel):
    name: str
    status: str
    instanceType: str
    minSize: int = 0
    maxSize: int = 0
    desiredSize: int = 0
    diskSize: int = 0
    capacityType: str = ""
    amiType: str = ""

class Cluster(Document):
    name: str
    provider: str
    type: str
    region: str
    customer_category: str = "Internal"
    account_type: str = "production"
    cluster_version: Optional[str] = None
    node_count: int = 0
    nodeGroups: List[NodeGroup] = []
    node_instance_types: List[str] = []
    tags: Dict[str, str] = {}
    status: str = "UNKNOWN"
    created_at: datetime = None
    timestamp: datetime = datetime.now(UTC)

    class Settings:
        name = "clusters"  # Collection name

def format_datetime(dt):
    """Convert datetime to ISO format string"""
    if isinstance(dt, datetime):
        return dt.isoformat()
    return dt

async def init_mongodb(uri: str, db_name: str):
    """Initialize MongoDB connection and Beanie models"""
    client = AsyncIOMotorClient(uri)
    await init_beanie(database=client[db_name], document_models=[Cluster])

async def get_clusters_data() -> List[Dict]:
    """
    Fetch all clusters data with selected fields only using aggregation
    """
    try:
        pipeline = [
            {
                "$project": {
                    "_id": 0,
                    "name": 1,
                    "provider": 1,
                    "type": 1,
                    "region": 1,
                    "customer_category": 1
                }
            }
        ]
        
        # Use aggregate instead of find
        clusters = await Cluster.aggregate(pipeline).to_list()
        return {"clusters": clusters}
        
    except Exception as e:
        logger.error(f"Error fetching clusters data: {str(e)}")
        return {"clusters": []}

async def get_one_cluster_data(cluster_id: str) -> Dict:
    """
    Fetch detailed data for a specific cluster
    """
    try:
        pipeline = [
            {
                "$match": {
                    "name": cluster_id
                }
            },
            {
                "$project": {
                    "_id": 0,
                    "name": 1,
                    "provider": 1,
                    "cluster_version": 1,
                    "region": 1,
                    "created_at": 1,
                    "status": 1,
                    "tags": 1,
                    "nodeGroups": 1
                }
            },
            {
                "$limit": 1
            }
        ]
        
        clusters = await Cluster.aggregate(pipeline).to_list()
        
        if not clusters:
            return {"cluster": None}
            
        # Transform the data to match required format
        cluster_data = clusters[0]
        
        # Format the response
        formatted_cluster = {
            "cluster": {
                "name": cluster_data.get("name"),
                "provider": cluster_data.get("provider"),
                "version": cluster_data.get("cluster_version"),
                "region": cluster_data.get("region"),
                "createdAt": format_datetime(cluster_data.get("created_at")),
                "status": cluster_data.get("status"),
                "tags": cluster_data.get("tags", {}),
                "nodeGroups": [
                    {
                        "name": ng.get("name"),
                        "status": ng.get("status"),
                        "instanceType": ng.get("instanceType"),
                        "minSize": ng.get("minSize"),
                        "maxSize": ng.get("maxSize"),
                        "desiredSize": ng.get("desiredSize"),
                        "diskSize": ng.get("diskSize"),
                        "capacityType": ng.get("capacityType"),
                        "amiType": ng.get("amiType")
                    }
                    for ng in cluster_data.get("nodeGroups", [])
                ]
            }
        }
        
        return formatted_cluster
        
    except Exception as e:
        logger.error(f"Error fetching cluster {cluster_id} data: {str(e)}")
        return None