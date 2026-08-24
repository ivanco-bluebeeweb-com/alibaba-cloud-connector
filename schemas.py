"""Pydantic params models + SDL entity contracts for Alibaba Cloud
Connector.

All params models are module-scope (V17 federal invariant, same rule as
AWS/Azure/GCP/OCI/DigitalOcean Connector's schemas.py).
"""
from __future__ import annotations

from pydantic import BaseModel, Field
from imperal_sdk import sdl


class NoParams(BaseModel):
    """Explicit empty params model -- V17 disallows untyped handlers."""
    pass


# ──────────────────────────────────────────────────────────────────────────
# Connection
# ──────────────────────────────────────────────────────────────────────────


class ConnectAlibabaCloudParams(BaseModel):
    access_key_id: str = Field(..., description="Your Alibaba Cloud AccessKey ID, from the RAM console.")
    access_key_secret: str = Field(..., description="Your Alibaba Cloud AccessKey Secret.")
    region_id: str = Field("cn-hangzhou", description="Default region for requests that need one, e.g. cn-hangzhou.")
    label: str = Field("", description="Optional friendly name for this Alibaba Cloud account connection.")


class ProviderConnection(sdl.Entity):
    id: str = ""
    title: str = ""
    connected: bool = False
    detail: str = ""
    region_id: str = ""
    account_id: str = ""


class ProviderConnectionList(sdl.Entity):
    connections: list[ProviderConnection] = []


class DisconnectAlibabaCloudParams(BaseModel):
    connection_id: str = Field(..., description="The connection id to disconnect, from list_connections.")


class DeleteResult(sdl.Entity):
    deleted: bool = False
    id: str = ""


class ConnectionIdParams(BaseModel):
    connection_id: str = Field("", description="Which connection to use; omit if only one is connected.")
    region_id: str = Field("", description="Region to query; omit to use the connection's default region.")


# ──────────────────────────────────────────────────────────────────────────
# Cloud Overview
# ──────────────────────────────────────────────────────────────────────────


class GetCloudOverviewParams(BaseModel):
    connection_id: str = Field("", description="Which connection to use; omit if only one is connected.")


class CloudOverview(sdl.Entity):
    ecs_running: int = 0
    ecs_stopped: int = 0
    oss_buckets_count: int = 0
    rds_instances_count: int = 0
    ack_clusters_count: int = 0
    account_balance: str = ""


# ──────────────────────────────────────────────────────────────────────────
# ECS (Elastic Compute Service)
# ──────────────────────────────────────────────────────────────────────────


class ListInstancesParams(BaseModel):
    connection_id: str = Field("", description="Which connection to use; omit if only one is connected.")
    region_id: str = Field("", description="Region to list instances in; omit to use the connection's default region.")


class EcsInstance(sdl.Entity):
    instance_id: str = ""
    instance_name: str = ""
    status: str = ""
    instance_type: str = ""
    region_id: str = ""
    zone_id: str = ""
    image_id: str = ""
    public_ip: str = ""
    private_ip: str = ""
    creation_time: str = ""


class EcsInstanceList(sdl.Entity):
    instances: list[EcsInstance] = []


class InstanceResourceParams(BaseModel):
    connection_id: str = Field("", description="Which connection to use; omit if only one is connected.")
    region_id: str = Field("", description="Region the instance lives in; omit to use the connection's default region.")
    instance_id: str = Field(..., description="The ECS instance id.")


class InstanceActionResult(sdl.Entity):
    instance_id: str = ""
    action: str = ""


# ──────────────────────────────────────────────────────────────────────────
# OSS (Object Storage Service)
# ──────────────────────────────────────────────────────────────────────────


class ListBucketsParams(BaseModel):
    connection_id: str = Field("", description="Which connection to use; omit if only one is connected.")


class OssBucket(sdl.Entity):
    name: str = ""
    location: str = ""
    storage_class: str = ""
    creation_date: str = ""


class OssBucketList(sdl.Entity):
    buckets: list[OssBucket] = []


# ──────────────────────────────────────────────────────────────────────────
# ApsaraDB RDS
# ──────────────────────────────────────────────────────────────────────────


class ListRdsInstancesParams(BaseModel):
    connection_id: str = Field("", description="Which connection to use; omit if only one is connected.")
    region_id: str = Field("", description="Region to list databases in; omit to use the connection's default region.")


class RdsInstance(sdl.Entity):
    dbinstance_id: str = ""
    dbinstance_description: str = ""
    engine: str = ""
    engine_version: str = ""
    dbinstance_status: str = ""
    region_id: str = ""


class RdsInstanceList(sdl.Entity):
    instances: list[RdsInstance] = []


# ──────────────────────────────────────────────────────────────────────────
# ACK (Container Service for Kubernetes) -- read-only
# ──────────────────────────────────────────────────────────────────────────


class ListClustersParams(BaseModel):
    connection_id: str = Field("", description="Which connection to use; omit if only one is connected.")
    region_id: str = Field("", description="Region to list clusters in; omit to use the connection's default region.")


class AckCluster(sdl.Entity):
    cluster_id: str = ""
    name: str = ""
    state: str = ""
    cluster_type: str = ""
    region_id: str = ""
    kubernetes_version: str = ""


class AckClusterList(sdl.Entity):
    clusters: list[AckCluster] = []


# ──────────────────────────────────────────────────────────────────────────
# CloudMonitor
# ──────────────────────────────────────────────────────────────────────────


class ListAlertsParams(BaseModel):
    connection_id: str = Field("", description="Which connection to use; omit if only one is connected.")


class MonitorAlert(sdl.Entity):
    rule_id: str = ""
    rule_name: str = ""
    namespace: str = ""
    metric_name: str = ""
    state: str = ""


class MonitorAlertList(sdl.Entity):
    alerts: list[MonitorAlert] = []


# ──────────────────────────────────────────────────────────────────────────
# Billing (BSS OpenAPI)
# ──────────────────────────────────────────────────────────────────────────


class GetBillingParams(BaseModel):
    connection_id: str = Field("", description="Which connection to use; omit if only one is connected.")


class BillingBalance(sdl.Entity):
    available_amount: str = ""
    credit_amount: str = ""
    currency: str = ""
