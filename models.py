# models.py
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime

class NodeGroupInfo(BaseModel):
    name: str
    status: str
    instanceType: str
    minSize: int
    maxSize: int
    desiredSize: int
    diskSize: Optional[int] = None
    capacityType: Optional[str] = None
    amiType: Optional[str] = None

class ClusterDetailsDB(BaseModel):
    name: str
    provider: str
    version: str
    region: str
    createdAt: datetime
    status: str
    account_type: str
    endpoint: Optional[str] = None
    tags: Dict[str, str] = None
    vpcId: Optional[str] = None
    serviceIpv4Cidr: Optional[str] = None
    platformVersion: Optional[str] = None
    nodeGroups: List[NodeGroupInfo] = []
    last_updated: Optional[datetime] = None

class ClusterInfo(BaseModel):
    name: str
    provider: str
    type: str
    region: str
    account_type: str
    customer_category: str = "Internal"
    last_updated: Optional[datetime] = None