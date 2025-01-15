#!/usr/bin/env python3
import os
import yaml
from github import Github
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
import typer
from pydantic import BaseModel, Field, validator
from typing import Optional
from rich.console import Console
from rich.prompt import Prompt
from rich.panel import Panel
from typing import List
from pydantic import BaseModel



# Initialize rich console for better output
console = Console()

class ProvisionRequest(BaseModel):
    cluster_name: str
    customer_category: str
    cloud_provider: str = "aws"
    region: str = "us-east-1"
    environment_type: str = "notprod"
    compute_plan: str = "standard"

class ClusterInfo(BaseModel):
    name: str
    provider: str
    type: str
    region: str
    customer_category: str

class InfrastructureConfig(BaseModel):
    cluster_name: str = str
    customer_category: str
    region: str = Field(default="us-east-1")
    environment_type: str = Field(default="prod")
    compute_plan: str = Field(default="standard")
    oidc_endpoint_thumbprint: str = Field(
        default="32f9e66ae934e90332545a9e7494591af3f34938"
    )

    @validator('region')
    def validate_region(cls, v):
        valid_regions = ['us-east-1', 'us-west-2', 'eu-west-1', 'ap-southeast-1']
        if v not in valid_regions:
            raise ValueError(f'Region must be one of {valid_regions}')
        return v

    @validator('environment_type')
    def validate_env_type(cls, v):
        valid_envs = ['prod', 'notprod']
        if v not in valid_envs:
            raise ValueError(f'Environment type must be one of {valid_envs}')
        return v

    @validator('compute_plan')
    def validate_compute_plan(cls, v):
        valid_plans = ['standard', 'premium', 'enterprise']
        if v not in valid_plans:
            raise ValueError(f'Compute plan must be one of {valid_plans}')
        return v

def generate_argo_application(config: InfrastructureConfig) -> dict:
    """Generate ArgoCD Application configuration."""
    return {
        "apiVersion": "argoproj.io/v1alpha1",
        "kind": "Application",
        "metadata": {
            "name": f"lyric-infrastructure-{config.cluster_name}",
            "namespace": "argo"
        },
        "spec": {
            "project": "default",
            "sources": [
                {
                    "repoURL": "https://github.com/Lyric-Engineering/argocd-apps.git",
                    "path": "crossplane/aws",
                    "targetRevision": "main",
                    "helm": {
                        "valueFiles": ["values.yaml"],
                        "parameters": [
                            {"name": "clusterName", "value": config.cluster_name},
                            {"name": "cloudProvider", "value": "aws"},
                            {"name": "environmentType", "value": config.environment_type},
                            {"name": "region", "value": config.region},
                            {"name": "computePlan", "value": config.compute_plan},
                            {"name": "customer_category", "value": config.customer_category},
                            {"name": "oidcEndpointThumbprint", "value": config.oidc_endpoint_thumbprint}
                        ]
                    }
                },
                {
                    "repoURL": "https://github.com/Lyric-Engineering/argocd-apps.git",
                    "path": "crossplane/commons",
                    "targetRevision": "main",
                    "helm": {
                        "valueFiles": ["values.yaml"],
                        "parameters": [
                            {"name": "clusterName", "value": config.cluster_name},
                            {"name": "cloudProvider", "value": "aws"},
                            {"name": "environmentType", "value": config.environment_type},
                            {"name": "region", "value": config.region},
                            {"name": "computePlan", "value": config.compute_plan},
                            {"name": "oidcEndpointThumbprint", "value": config.oidc_endpoint_thumbprint}
                        ]
                    }
                }
            ],
            "destination": {
                "server": "https://kubernetes.default.svc",
                "namespace": "crossplane-system"
            },
            "syncPolicy": {
                "automated": {
                    "prune": True,
                    "selfHeal": True
                }
            }
        }
    }

def commit_to_github(config: InfrastructureConfig, yaml_content: str):
    """Commit the YAML configuration to GitHub."""
    try:
        github_token = os.getenv("GITHUB_TOKEN")
        if not github_token:
            raise ValueError("GITHUB_TOKEN environment variable not set")

        g = Github(github_token)
        repo = g.get_repo("Lyric-Engineering/argocd-apps")
        
        # Create file path
        file_path = f"applications/{config.cluster_name}/application.yaml"
        
        # Create commit message
        commit_message = f"Add infrastructure configuration for {config.cluster_name}"
        
        try:
            # Try to get the file first (to update if it exists)
            contents = repo.get_contents(file_path)
            repo.update_file(
                file_path,
                commit_message,
                yaml_content,
                contents.sha,
                branch="main"
            )
            console.print(f"[green]Updated configuration at {file_path}[/green]")
        except Exception:
            # File doesn't exist, create it
            repo.create_file(
                file_path,
                commit_message,
                yaml_content,
                branch="main"
            )
            console.print(f"[green]Created new configuration at {file_path}[/green]")

    except Exception as e:
        console.print(f"[red]Error committing to GitHub: {str(e)}[/red]")
        raise

def send_slack_notification(config: InfrastructureConfig):
    """Send Slack notification about the new infrastructure."""
    try:
        slack_token = os.getenv("SLACK_TOKEN")
        if not slack_token:
            raise ValueError("SLACK_TOKEN environment variable not set")

        client = WebClient(token=slack_token)
        
        message = f"""
:rocket: New infrastructure configuration created:
• Cluster: {config.cluster_name}
• Customer: {config.customer_category}
• Environment: {config.environment_type}
• Region: {config.region}
• Compute Plan: {config.compute_plan}
        """
        
        response = client.chat_postMessage(
            channel="#infrastructure-deployments",
            text=message
        )
        console.print("[green]Slack notification sent successfully[/green]")

    except SlackApiError as e:
        console.print(f"[red]Error sending Slack notification: {str(e)}[/red]")
        raise

def main():
    console.print(Panel.fit("Infrastructure Provisioning Tool", style="bold blue"))
    
    try:
        # Gather input with rich prompts
        cluster_name = Prompt.ask("Enter cluster name", default="dev")
        customer_category = Prompt.ask("Enter customer category", default="lyric")
        region = Prompt.ask(
            "Enter region",
            choices=['us-east-1', 'us-west-2', 'eu-west-1', 'ap-southeast-1'],
            default="us-east-1"
        )
        environment_type = Prompt.ask(
            "Enter environment type",
            choices=['prod','notprod'],
            default="notprod"
        )
        compute_plan = Prompt.ask(
            "Enter compute plan",
            choices=['standard', 'premium', 'enterprise'],
            default="standard"
        )

        # Create configuration object
        config = InfrastructureConfig(
            cluster_name=cluster_name,
            customer_category=customer_category,
            region=region,
            environment_type=environment_type,
            compute_plan=compute_plan
        )

        # Generate ArgoCD application configuration
        argo_app = generate_argo_application(config)
        yaml_content = yaml.dump(argo_app, default_flow_style=False)

        # Commit to GitHub
        with console.status("Committing to GitHub..."):
            commit_to_github(config, yaml_content)

        # Send Slack notification
        with console.status("Sending Slack notification..."):
            send_slack_notification(config)

        console.print("[green]Infrastructure configuration completed successfully![/green]")

    except Exception as e:
        console.print(f"[red]Error: {str(e)}[/red]")
        raise typer.Exit(1)
    
def get_clusters_from_github() -> List[ClusterInfo]:
    """Fetch cluster configurations from GitHub repository."""
    try:
        github_token = os.getenv("GITHUB_TOKEN")
        if not github_token:
            raise ValueError("GITHUB_TOKEN environment variable not set")

        # Initialize GitHub client
        g = Github(github_token)
        repo = g.get_repo("Lyric-Engineering/argocd-apps")
        
        clusters = []
        # Get contents of the environments directory
        contents = repo.get_contents("crossplane/environments")
        
        for content in contents:
            if content.name.endswith('.yaml'):
                # Get the YAML content
                yaml_content = content.decoded_content.decode()
                # Parse all YAML documents in the file
                yaml_documents = list(yaml.safe_load_all(yaml_content))
                
                # Find the ArgoCD Application document
                argo_app = None
                for doc in yaml_documents:
                    if doc and doc.get('kind') == 'Application':
                        argo_app = doc
                        break
                
                if not argo_app:
                    print(f"No ArgoCD Application found in {content.name}")
                    continue
                
                try:
                    # Get the first source's parameters
                    sources = argo_app.get('spec', {}).get('sources', [])
                    if not sources:
                        print(f"No sources found in {content.name}")
                        continue
                        
                    params = {
                        param['name']: param['value'] 
                        for param in sources[0].get('helm', {}).get('parameters', [])
                    }
                    
                    cluster_info = ClusterInfo(
                        name=params.get('clusterName', ''),
                        provider=params.get('cloudProvider', '').upper(),
                        type='Production' if params.get('environmentType') == 'prod' else 'Non-Production',
                        region=params.get('region', ''),
                        customer_category=params.get('customer_category', 'Lyric')
                    )
                    clusters.append(cluster_info)
                    print(f"Successfully parsed cluster config for {cluster_info.name}")
                    
                except (KeyError, TypeError, IndexError) as e:
                    print(f"Error parsing cluster config {content.name}: {str(e)}")
                    continue
                
        return {"clusters": [cluster.dict() for cluster in clusters]}
    
    except Exception as e:
        print(f"Error fetching clusters from GitHub: {str(e)}")
        return {"clusters": []}

if __name__ == "__main__":
    typer.run(main)