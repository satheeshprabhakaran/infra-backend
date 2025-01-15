from typing import List, Dict, Any
import os
import yaml
import boto3
from concurrent.futures import ThreadPoolExecutor, as_completed
import asyncio
from google.cloud import container_v1
from google.cloud.container_v1.types import ListClustersRequest

from azure.identity import ClientSecretCredential
from azure.mgmt.compute import ComputeManagementClient
from dataclasses import dataclass
import logging
from datetime import datetime

@dataclass
class ClusterInfo:
    name: str
    provider: str
    type: str
    region: str
    customer_category: str = "Internal"
    account_type: str = "production"
    cluster_version: str = None
    node_count: int = 0
    nodeGroups: List[Dict[str, Any]] = None
    node_instance_types: List[str] = None
    tags: Dict[str, str] = None
    status: str = None
    created_at: datetime = None

class CloudConfigLoader:
    def __init__(self, config_path: str):
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)
        self.clouds = self.config.get('clouds', {})

    def get_enabled_clouds(self) -> Dict[str, Dict]:
        return {
            cloud: config for cloud, config in self.clouds.items()
            if config.get('enabled', False)
        }

    def _resolve_env_vars(self, value: str) -> str:
        if isinstance(value, str) and value.startswith('${') and value.endswith('}'):
            env_var = value[2:-1]
            return os.getenv(env_var, '')
        return value

    def get_cloud_credentials(self, cloud: str, account: str) -> Dict[str, str]:
        cloud_config = self.clouds.get(cloud, {})
        accounts = cloud_config.get('accounts', cloud_config.get('projects', cloud_config.get('subscriptions', {})))
        account_config = accounts.get(account, {})
        credentials = account_config.get('credentials', {})
        return {k: self._resolve_env_vars(v) for k, v in credentials.items()}

class CloudClustersCollector:
    def __init__(self, config_path: str, max_workers: int = 10):
        self.config_loader = CloudConfigLoader(config_path)
        self.logger = logging.getLogger(__name__)
        self.max_workers = max_workers

    def __init__(self, config_path: str):
        self.config_loader = CloudConfigLoader(config_path)
        self.logger = logging.getLogger(__name__)

    async def get_aws_clusters(self, credentials: Dict[str, str], account_type: str) -> List[ClusterInfo]:
        try:
            session = boto3.Session(
                aws_access_key_id=credentials['access_key'],
                aws_secret_access_key=credentials['secret_key']
            )
            
            eks = session.client('eks')
            ec2 = session.client('ec2')
            regions = [region['RegionName'] for region in ec2.describe_regions()['Regions']]
            clusters = []

            for region in regions:
                try:
                    eks_regional = session.client('eks', region_name=region)
                    cluster_list = eks_regional.list_clusters()['clusters']
                    
                    for cluster_name in cluster_list:
                        # Get detailed cluster information
                        cluster_info = eks_regional.describe_cluster(name=cluster_name)['cluster']
                        
                        # Get node group information
                        nodegroups = eks_regional.list_nodegroups(clusterName=cluster_name)['nodegroups']
                        node_count = 0
                        instance_types = set()
                        customer_tags = {
                            key: value for key, value in cluster_info.get('tags', {}).items() 
                            if key.lower().startswith('customer')
                        }
                        # If you want just one value, you could prioritize them or take the first one
                        customer_category = next(iter(customer_tags.values()), None) if customer_tags else None
                        # If you want to store all customer-related tags:
                        customer_info = customer_category
                        
                        nodeGroups = []

                        for nodegroup in nodegroups:
                            ng_info = eks_regional.describe_nodegroup(
                                clusterName=cluster_name,
                                nodegroupName=nodegroup
                            )['nodegroup']
                            
                            # Transform the API response into the desired format
                            node_group_data = {
                                "name": nodegroup,
                                "status": ng_info.get('status'),
                                "instanceType": ng_info.get('instanceTypes', [''])[0],  # Taking first instance type if multiple exist
                                "minSize": ng_info.get('scalingConfig', {}).get('minSize', 0),
                                "maxSize": ng_info.get('scalingConfig', {}).get('maxSize', 0),
                                "desiredSize": ng_info.get('scalingConfig', {}).get('desiredSize', 0),
                                "diskSize": ng_info.get('diskSize', 0),
                                "capacityType": ng_info.get('capacityType', 'ON_DEMAND'),
                                "amiType": ng_info.get('amiType', '')
                            }
                            
                            nodeGroups.append(node_group_data)                            
                            ng_info = eks_regional.describe_nodegroup(
                                clusterName=cluster_name,
                                nodegroupName=nodegroup
                            )['nodegroup']
                            node_count += ng_info.get('scalingConfig', {}).get('desiredSize', 0)
                            instance_types.update(ng_info.get('instanceTypes', []))

                        clusters.append(ClusterInfo(
                            name=cluster_name,
                            provider='AWS',
                            type='Production' if account_type == 'production' else 'Non-Production',
                            region=region,
                            customer_category=customer_info,
                            account_type=account_type,
                            cluster_version=cluster_info.get('version'),
                            node_instance_types=list(instance_types),
                            nodeGroups=nodeGroups,
                            tags=cluster_info.get('tags', {}),
                            status='ACTIVE' if node_count != 0 else 'DORMANT',
                            created_at=cluster_info.get('createdAt')
                        ))
                except Exception as e:
                    self.logger.error(f"Error fetching AWS clusters in region {region}: {str(e)}")
            return clusters
        except Exception as e:
            self.logger.error(f"Error in get_aws_clusters: {str(e)}")
            return []

    async def get_gcp_clusters(self, credentials: Dict[str, str], account_type: str) -> List[ClusterInfo]:

        try:
            os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = credentials['credentials_path']
            client = container_v1.ClusterManagerClient()
            # Get all locations (regions and zones)
            project_id = credentials['project_id']
            parent = f"projects/{project_id}/locations/-"
            clusters = []
            # Create the list request
            request = ListClustersRequest(parent=parent)
            response = client.list_clusters(request)
            instance_types = []

            for cluster in response.clusters:
                nodeGroups = []

                for nodegroup in cluster.node_pools:
                    if nodegroup.status == 2:
                        status = "ACTIVE"
                    else:
                        status = "DORMANT"
                    node_group_data = {
                        "name": nodegroup.name,
                        "status": status,
                        "instanceType": nodegroup.config.machine_type,  # Taking first instance type if multiple exist
                        "minSize": nodegroup.autoscaling.total_min_node_count if nodegroup.autoscaling.total_min_node_count else 0,
                        "maxSize": nodegroup.autoscaling.total_max_node_count if nodegroup.autoscaling.total_max_node_count else 0,
                        "desiredSize": nodegroup.initial_node_count if nodegroup.initial_node_count else 0,
                        "diskSize": nodegroup.config.disk_size_gb,
                        "capacityType": nodegroup.autoscaling.location_policy,
                        "amiType": nodegroup.config.image_type
                    }
                    if not nodegroup.config.machine_type in instance_types:
                        instance_types.append(nodegroup.config.machine_type)
                    nodeGroups.append(node_group_data)
                
                tags = {}
                for tag in cluster.resource_labels:
                    tags[tag] = cluster.resource_labels[tag]
                
                clusters.append(ClusterInfo(
                    name=cluster.name,
                    provider='GCP',
                    type='Production' if account_type == 'production' else 'Non-Production',
                    region=cluster.location,
                    customer_category=cluster.resource_labels.get('customer_category', 'Lyric'),
                    account_type=account_type,
                    cluster_version=cluster.current_master_version,
                    node_instance_types=list(instance_types),
                    node_count=cluster.current_node_count,
                    nodeGroups=nodeGroups,
                    tags=tags,
                    status='ACTIVE' if cluster.current_node_count != 0 else 'DORMANT',
                    created_at=cluster.create_time
                ))
                
            return clusters
        except Exception as e:
            self.logger.error(f"Error in get_gcp_clusters: {str(e)}")
            return []

    async def get_azure_clusters(self, credentials: Dict[str, str], account_type: str) -> List[ClusterInfo]:
        try:
            credential = ClientSecretCredential(
                tenant_id=credentials['tenant_id'],
                client_id=credentials['client_id'],
                client_secret=credentials['client_secret']
            )
            
            compute_client = ComputeManagementClient(
                credential=credential,
                subscription_id=credentials['subscription_id']
            )
            
            clusters = []
            locations = compute_client.locations.list()

            for location in locations:
                try:
                    aks_client = compute_client.container_services
                    aks_clusters = aks_client.list_by_location(location.name)
                    
                    for cluster in aks_clusters:
                        # Get node pool information
                        node_pools = cluster.agent_pool_profiles
                        node_count = sum(pool.count for pool in node_pools)
                        instance_types = list(set(pool.vm_size for pool in node_pools))

                        clusters.append(ClusterInfo(
                            name=cluster.name,
                            provider='AZURE',
                            type='Production' if account_type == 'production' else 'Non-Production',
                            region=location.name,
                            account_type=account_type,
                            cluster_version=cluster.kubernetes_version,
                            node_count=node_count,
                            node_instance_types=instance_types,
                            tags=dict(cluster.tags or {}),
                            status=cluster.provisioning_state,
                            created_at=cluster.created_time
                        ))
                except Exception as e:
                    self.logger.error(f"Error fetching Azure clusters in region {location.name}: {str(e)}")
            return clusters
        except Exception as e:
            self.logger.error(f"Error in get_azure_clusters: {str(e)}")
            return []

    async def get_all_clusters(self) -> Dict[str, List[Dict]]:
        """Get all clusters from cloud providers."""
        try:
            all_clusters = []
            enabled_clouds = self.config_loader.get_enabled_clouds()
            with ThreadPoolExecutor(max_workers=len(enabled_clouds)) as executor:
                for cloud, config in enabled_clouds.items():
                    future_to_cloud = {}
                    
                    for cloud, config in enabled_clouds.items():
                        if cloud == 'aws':
                            for account_type in ['production', 'notproduction']:
                                credentials = self.config_loader.get_cloud_credentials(cloud, account_type)
                                future = executor.submit(
                                    asyncio.run,
                                    self.get_aws_clusters(credentials, account_type)
                                )
                                future_to_cloud[future] = (cloud, account_type)
                        
                        elif cloud == 'gcp':
                            for account_type in ['production', 'development']:
                                credentials = self.config_loader.get_cloud_credentials(cloud, account_type)
                                future = executor.submit(
                                    asyncio.run,
                                    self.get_gcp_clusters(credentials, account_type)
                                )
                                future_to_cloud[future] = (cloud, account_type)
                        
                        elif cloud == 'azure' and config.get('enabled', False):
                            for account_type in ['production', 'development']:
                                credentials = self.config_loader.get_cloud_credentials(cloud, account_type)
                                future = executor.submit(
                                    asyncio.run,
                                    self.get_azure_clusters(credentials, account_type)
                                )
                                future_to_cloud[future] = (cloud, account_type)

                    for future in as_completed(future_to_cloud):
                        cloud, account_type = future_to_cloud[future]
                        try:
                            clusters = future.result()
                            all_clusters.extend(clusters)
                        except Exception as e:
                            self.logger.error(f"Error processing {cloud} {account_type}: {str(e)}")

            return {"clusters": [cluster.__dict__ for cluster in all_clusters]}

        except Exception as e:
            self.logger.error(f"Error in get_all_clusters: {str(e)}")
            return {"clusters": []}

async def get_clusters_from_clouds() -> Dict[str, List[Dict]]:
    """Fetch cluster configurations from cloud providers."""
    try:
        collector = CloudClustersCollector('config/cloud_config.yaml')
        return await collector.get_all_clusters()
    except Exception as e:
        logging.error(f"Error fetching clusters: {str(e)}")
        return {"clusters": []}