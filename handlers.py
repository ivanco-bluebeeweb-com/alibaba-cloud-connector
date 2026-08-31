"""Chat functions for Alibaba Cloud Connector: connection management,
ECS instances, OSS buckets, ApsaraDB (RDS), ACK clusters (read-only),
CloudMonitor alerts, Billing, and a cloud overview (Tier 3 value-add).
Built on alibaba_client.py / schemas.py, following the same shape as
AWS/Azure/GCP/OCI/DigitalOcean Connector's handlers.py.
"""
from __future__ import annotations

import json
import uuid

from imperal_sdk import ActionResult

import alibaba_client as ali
from app import ext, chat
from schemas import (
    NoParams,
    ConnectAlibabaCloudParams, ProviderConnection, ProviderConnectionList,
    DisconnectAlibabaCloudParams, DeleteResult, ConnectionIdParams,
    GetCloudOverviewParams, CloudOverview,
    ListInstancesParams, EcsInstance, EcsInstanceList,
    InstanceResourceParams, InstanceActionResult,
    ListBucketsParams, OssBucket, OssBucketList,
    ListRdsInstancesParams, RdsInstance, RdsInstanceList,
    ListClustersParams, AckCluster, AckClusterList,
    ListAlertsParams, MonitorAlert, MonitorAlertList,
    GetBillingParams, BillingBalance,
)

_SECRET_NAME = "alibaba_cloud_connections"


async def _load_connections(ctx) -> list[dict]:
    raw = await ctx.secrets.get(_SECRET_NAME)
    if not raw:
        return []
    try:
        return json.loads(raw)
    except Exception:
        return []


async def _save_connections(ctx, connections: list[dict]) -> None:
    await ctx.secrets.set(_SECRET_NAME, json.dumps(connections))


async def _find_connection(ctx, connection_id: str) -> dict | None:
    connections = await _load_connections(ctx)
    if not connection_id and len(connections) == 1:
        return connections[0]
    for c in connections:
        if c.get("id") == connection_id:
            return c
    return None


async def _resolve(ctx, connection_id: str) -> dict | None:
    return await _find_connection(ctx, connection_id)


def _no_connection() -> ActionResult:
    return ActionResult.error("No Alibaba Cloud account connected yet. Use connect_alibaba_cloud first.")


def _err(prefix: str, e: ali.ProviderError) -> ActionResult:
    return ActionResult.error(f"{prefix}: {e.message}")


def _region(conn: dict, override: str) -> str:
    return override or conn.get("region_id", "cn-hangzhou")


# ──────────────────────────────────────────────────────────────────────────
# Connection management
# ──────────────────────────────────────────────────────────────────────────


@chat.function(
    "connect_alibaba_cloud",
    "Connect your own Alibaba Cloud account by saving an AccessKey ID + AccessKey Secret pair (from the RAM console), after checking it actually works via a harmless DescribeRegions read.",
    action_type="write",
    chain_callable=True,
    data_model=ProviderConnection,
    event="alibaba-cloud-connector.connect_alibaba_cloud",
    effects=["alibaba_cloud.provider.connected"],
)
async def connect_alibaba_cloud(ctx, params: ConnectAlibabaCloudParams) -> ActionResult:
    """Connect an Alibaba Cloud account after verifying the AccessKey pair actually works."""
    try:
        body = await ali.call(
            ctx, "ecs", "", "DescribeRegions", params.access_key_id, params.access_key_secret,
            "verify your AccessKey pair",
        )
    except ali.ProviderError as e:
        return _err("Couldn't verify your Alibaba Cloud AccessKey pair", e)

    connections = await _load_connections(ctx)
    conn_id = str(uuid.uuid4())
    title = params.label or f"Alibaba Cloud ({params.access_key_id[:8]}...)"
    entry = {
        "id": conn_id, "title": title,
        "access_key_id": params.access_key_id,
        "access_key_secret": params.access_key_secret,
        "region_id": params.region_id or "cn-hangzhou",
    }
    connections.append(entry)
    await _save_connections(ctx, connections)
    return ActionResult.success(ProviderConnection(
        id=conn_id, title=title, connected=True, detail="Connected",
        region_id=entry["region_id"], account_id=params.access_key_id[:8] + "...",
    ), summary="Alibaba cloud connected.")


@chat.function(
    "disconnect_alibaba_cloud",
    "Disconnect an Alibaba Cloud account: deletes the saved AccessKey pair. Nothing in Alibaba Cloud itself is changed.",
    action_type="write",
    chain_callable=True,
    data_model=DeleteResult,
    event="alibaba-cloud-connector.disconnect_alibaba_cloud",
    effects=["alibaba_cloud.provider.disconnected"],
)
async def disconnect_alibaba_cloud(ctx, params: DisconnectAlibabaCloudParams) -> ActionResult:
    """Disconnect an Alibaba Cloud account by deleting its saved AccessKey pair."""
    connections = await _load_connections(ctx)
    remaining = [c for c in connections if c.get("id") != params.connection_id]
    if len(remaining) == len(connections):
        return ActionResult.error("No connection found with that id.")
    await _save_connections(ctx, remaining)
    return ActionResult.success(DeleteResult(deleted=True, id=params.connection_id), summary="Alibaba cloud disconnected.")


@chat.function(
    "list_connections",
    "List the connected Alibaba Cloud accounts.",
    action_type="read",
    chain_callable=True,
    data_model=ProviderConnectionList,
)
async def list_connections(ctx, params: NoParams) -> ActionResult:
    """List the connected Alibaba Cloud accounts."""
    connections = await _load_connections(ctx)
    out = [
        ProviderConnection(
            id=c.get("id", ""), title=c.get("title", ""), connected=True,
            detail="Connected", region_id=c.get("region_id", ""),
            account_id=(c.get("access_key_id", "")[:8] + "...") if c.get("access_key_id") else "",
        )
        for c in connections
    ]
    return ActionResult.success(ProviderConnectionList(connections=out), summary="Connections listed.")


# ──────────────────────────────────────────────────────────────────────────
# Cloud Overview
# ──────────────────────────────────────────────────────────────────────────


@chat.function(
    "get_cloud_overview",
    "Value-add report: one-glance Alibaba Cloud account health snapshot -- ECS instance counts by status, OSS bucket/RDS instance/ACK cluster counts, and current account balance.",
    action_type="read",
    chain_callable=True,
    data_model=CloudOverview,
)
async def get_cloud_overview(ctx, params: GetCloudOverviewParams) -> ActionResult:
    """One-glance Alibaba Cloud account health snapshot."""
    conn = await _resolve(ctx, params.connection_id)
    if not conn:
        return _no_connection()
    ak, sk, region = conn.get("access_key_id", ""), conn.get("access_key_secret", ""), conn.get("region_id", "cn-hangzhou")
    try:
        ecs_body = await ali.call(ctx, "ecs", region, "DescribeInstances", ak, sk, "list ECS instances", {"PageSize": "100"})
        instances = ((ecs_body.get("Instances") or {}).get("Instance")) or []
        oss_buckets = await ali.list_oss_buckets(ctx, ak, sk, region)
        rds_body = await ali.call(ctx, "rds", region, "DescribeDBInstances", ak, sk, "list RDS instances", {"PageSize": "100"})
        rds_instances = ((rds_body.get("Items") or {}).get("DBInstance")) or []
        cs_body = await ali.call(ctx, "cs", region, "DescribeClusters", ak, sk, "list ACK clusters")
        clusters = cs_body if isinstance(cs_body, list) else cs_body.get("clusters", [])
        balance = await ali.call(ctx, "bssopenapi", "", "QueryAccountBalance", ak, sk, "read account balance")
    except ali.ProviderError as e:
        return _err("Couldn't build the cloud overview", e)
    running = sum(1 for i in instances if i.get("Status") == "Running")
    stopped = sum(1 for i in instances if i.get("Status") != "Running")
    bal_data = (balance.get("Data") or {})
    return ActionResult.success(CloudOverview(
        ecs_running=running, ecs_stopped=stopped,
        oss_buckets_count=len(oss_buckets), rds_instances_count=len(rds_instances),
        ack_clusters_count=len(clusters) if isinstance(clusters, list) else 0,
        account_balance=str(bal_data.get("AvailableAmount", "")),
    ), summary="Cloud overview retrieved.")


# ──────────────────────────────────────────────────────────────────────────
# ECS (Elastic Compute Service)
# ──────────────────────────────────────────────────────────────────────────


@chat.function(
    "list_virtual_machines",
    "List ECS (Elastic Compute Service) instances in the connected Alibaba Cloud account, optionally filtered by region.",
    action_type="read",
    chain_callable=True,
    data_model=EcsInstanceList,
)
async def list_virtual_machines(ctx, params: ListInstancesParams) -> ActionResult:
    """List ECS instances in the connected account."""
    conn = await _resolve(ctx, params.connection_id)
    if not conn:
        return _no_connection()
    region = _region(conn, params.region_id)
    try:
        body = await ali.call(
            ctx, "ecs", region, "DescribeInstances", conn.get("access_key_id", ""),
            conn.get("access_key_secret", ""), "list ECS instances", {"PageSize": "100"},
        )
    except ali.ProviderError as e:
        return _err("Couldn't list ECS instances", e)
    items = ((body.get("Instances") or {}).get("Instance")) or []
    out = [
        EcsInstance(
            instance_id=i.get("InstanceId", ""), instance_name=i.get("InstanceName", ""),
            status=i.get("Status", ""), instance_type=i.get("InstanceType", ""),
            region_id=i.get("RegionId", ""), zone_id=i.get("ZoneId", ""),
            image_id=i.get("ImageId", ""),
            public_ip=",".join((i.get("PublicIpAddress") or {}).get("IpAddress", [])),
            private_ip=",".join((i.get("VpcAttributes") or {}).get("PrivateIpAddress", {}).get("IpAddress", [])),
            creation_time=i.get("CreationTime", ""),
        )
        for i in items
    ]
    return ActionResult.success(EcsInstanceList(instances=out), summary="Virtual machines listed.")


@chat.function(
    "get_virtual_machine",
    "Read one ECS instance in full.",
    action_type="read",
    chain_callable=True,
    data_model=EcsInstance,
)
async def get_virtual_machine(ctx, params: InstanceResourceParams) -> ActionResult:
    """Read one ECS instance in full."""
    conn = await _resolve(ctx, params.connection_id)
    if not conn:
        return _no_connection()
    region = _region(conn, params.region_id)
    try:
        body = await ali.call(
            ctx, "ecs", region, "DescribeInstances", conn.get("access_key_id", ""),
            conn.get("access_key_secret", ""), "read that ECS instance",
            {"InstanceIds": json.dumps([params.instance_id])},
        )
    except ali.ProviderError as e:
        return _err("Couldn't read that ECS instance", e)
    items = ((body.get("Instances") or {}).get("Instance")) or []
    if not items:
        return ActionResult.error("No ECS instance found with that id.")
    i = items[0]
    return ActionResult.success(EcsInstance(
        instance_id=i.get("InstanceId", ""), instance_name=i.get("InstanceName", ""),
        status=i.get("Status", ""), instance_type=i.get("InstanceType", ""),
        region_id=i.get("RegionId", ""), zone_id=i.get("ZoneId", ""),
        image_id=i.get("ImageId", ""),
        public_ip=",".join((i.get("PublicIpAddress") or {}).get("IpAddress", [])),
        private_ip=",".join((i.get("VpcAttributes") or {}).get("PrivateIpAddress", {}).get("IpAddress", [])),
        creation_time=i.get("CreationTime", ""),
    ), summary="Virtual machine retrieved.")


@chat.function(
    "start_virtual_machine",
    "Start a stopped ECS instance.",
    action_type="write",
    chain_callable=True,
    data_model=InstanceActionResult,
    event="alibaba-cloud-connector.start_instance",
    effects=["alibaba_cloud.instance.started"],
)
async def start_virtual_machine(ctx, params: InstanceResourceParams) -> ActionResult:
    """Start a stopped ECS instance."""
    conn = await _resolve(ctx, params.connection_id)
    if not conn:
        return _no_connection()
    region = _region(conn, params.region_id)
    try:
        await ali.call(
            ctx, "ecs", region, "StartInstance", conn.get("access_key_id", ""),
            conn.get("access_key_secret", ""), "start that ECS instance",
            {"InstanceId": params.instance_id}, http_method="POST",
        )
    except ali.ProviderError as e:
        return _err("Couldn't start that ECS instance", e)
    return ActionResult.success(InstanceActionResult(instance_id=params.instance_id, action="start_requested"), summary="Virtual machine start requested.")


@chat.function(
    "stop_virtual_machine",
    "Stop a running ECS instance.",
    action_type="write",
    chain_callable=True,
    data_model=InstanceActionResult,
    event="alibaba-cloud-connector.stop_instance",
    effects=["alibaba_cloud.instance.stopped"],
)
async def stop_virtual_machine(ctx, params: InstanceResourceParams) -> ActionResult:
    """Stop a running ECS instance."""
    conn = await _resolve(ctx, params.connection_id)
    if not conn:
        return _no_connection()
    region = _region(conn, params.region_id)
    try:
        await ali.call(
            ctx, "ecs", region, "StopInstance", conn.get("access_key_id", ""),
            conn.get("access_key_secret", ""), "stop that ECS instance",
            {"InstanceId": params.instance_id}, http_method="POST",
        )
    except ali.ProviderError as e:
        return _err("Couldn't stop that ECS instance", e)
    return ActionResult.success(InstanceActionResult(instance_id=params.instance_id, action="stop_requested"), summary="Virtual machine stop requested.")


@chat.function(
    "restart_virtual_machine",
    "Reboot a running ECS instance, restarting its operating system.",
    action_type="write",
    chain_callable=True,
    data_model=InstanceActionResult,
    event="alibaba-cloud-connector.restart_instance",
    effects=["alibaba_cloud.instance.restarted"],
)
async def restart_virtual_machine(ctx, params: InstanceResourceParams) -> ActionResult:
    """Reboot a running ECS instance."""
    conn = await _resolve(ctx, params.connection_id)
    if not conn:
        return _no_connection()
    region = _region(conn, params.region_id)
    try:
        await ali.call(
            ctx, "ecs", region, "RebootInstance", conn.get("access_key_id", ""),
            conn.get("access_key_secret", ""), "restart that ECS instance",
            {"InstanceId": params.instance_id}, http_method="POST",
        )
    except ali.ProviderError as e:
        return _err("Couldn't restart that ECS instance", e)
    return ActionResult.success(InstanceActionResult(instance_id=params.instance_id, action="restart_requested"), summary="Virtual machine restart requested.")


# ──────────────────────────────────────────────────────────────────────────
# OSS (Object Storage Service)
# ──────────────────────────────────────────────────────────────────────────


@chat.function(
    "list_storage_accounts",
    "List OSS (Object Storage Service) buckets visible to the connected Alibaba Cloud account.",
    action_type="read",
    chain_callable=True,
    data_model=OssBucketList,
)
async def list_storage_accounts(ctx, params: ListBucketsParams) -> ActionResult:
    """List OSS buckets visible to the connected account."""
    conn = await _resolve(ctx, params.connection_id)
    if not conn:
        return _no_connection()
    try:
        items = await ali.list_oss_buckets(
            ctx, conn.get("access_key_id", ""), conn.get("access_key_secret", ""),
            _region(conn, params.region_id),
        )
    except ali.ProviderError as e:
        return _err("Couldn't list OSS buckets", e)
    out = [
        OssBucket(name=b.get("name", ""), location=b.get("location", ""), creation_date=b.get("creation_date", ""))
        for b in items
    ]
    return ActionResult.success(OssBucketList(buckets=out), summary="Storage accounts listed.")


# ──────────────────────────────────────────────────────────────────────────
# ApsaraDB (RDS)
# ──────────────────────────────────────────────────────────────────────────


@chat.function(
    "list_sql_databases",
    "List ApsaraDB RDS instances on the connected Alibaba Cloud account, optionally filtered by region.",
    action_type="read",
    chain_callable=True,
    data_model=RdsInstanceList,
)
async def list_sql_databases(ctx, params: ListRdsInstancesParams) -> ActionResult:
    """List ApsaraDB RDS instances on the connected account."""
    conn = await _resolve(ctx, params.connection_id)
    if not conn:
        return _no_connection()
    region = _region(conn, params.region_id)
    try:
        body = await ali.call(
            ctx, "rds", region, "DescribeDBInstances", conn.get("access_key_id", ""),
            conn.get("access_key_secret", ""), "list RDS instances", {"PageSize": "100"},
        )
    except ali.ProviderError as e:
        return _err("Couldn't list RDS instances", e)
    items = ((body.get("Items") or {}).get("DBInstance")) or []
    out = [
        RdsInstance(
            dbinstance_id=i.get("DBInstanceId", ""), dbinstance_description=i.get("DBInstanceDescription", ""),
            engine=i.get("Engine", ""), engine_version=i.get("EngineVersion", ""),
            dbinstance_status=i.get("DBInstanceStatus", ""), region_id=i.get("RegionId", ""),
        )
        for i in items
    ]
    return ActionResult.success(RdsInstanceList(instances=out), summary="Sql databases listed.")


# ──────────────────────────────────────────────────────────────────────────
# ACK (Container Service for Kubernetes) -- read-only
# ──────────────────────────────────────────────────────────────────────────


@chat.function(
    "list_kubernetes_clusters",
    "List ACK (Container Service for Kubernetes) clusters on the connected Alibaba Cloud account (read-only).",
    action_type="read",
    chain_callable=True,
    data_model=AckClusterList,
)
async def list_kubernetes_clusters(ctx, params: ListClustersParams) -> ActionResult:
    """List ACK clusters on the connected account (read-only)."""
    conn = await _resolve(ctx, params.connection_id)
    if not conn:
        return _no_connection()
    region = _region(conn, params.region_id)
    try:
        body = await ali.call(
            ctx, "cs", region, "DescribeClusters", conn.get("access_key_id", ""),
            conn.get("access_key_secret", ""), "list ACK clusters",
        )
    except ali.ProviderError as e:
        return _err("Couldn't list ACK clusters", e)
    items = body if isinstance(body, list) else body.get("clusters", [])
    out = [
        AckCluster(
            cluster_id=c.get("cluster_id", ""), name=c.get("name", ""),
            state=c.get("state", ""), region_id=c.get("region_id", ""),
            cluster_type=c.get("cluster_type", ""), size=c.get("size", 0),
        )
        for c in items
    ]
    return ActionResult.success(AckClusterList(clusters=out), summary="Kubernetes clusters listed.")


# ──────────────────────────────────────────────────────────────────────────
# CloudMonitor
# ──────────────────────────────────────────────────────────────────────────


@chat.function(
    "list_metric_alerts",
    "List CloudMonitor alarm rules configured on the connected Alibaba Cloud account.",
    action_type="read",
    chain_callable=True,
    data_model=MonitorAlertList,
)
async def list_metric_alerts(ctx, params: ListAlertsParams) -> ActionResult:
    """List CloudMonitor alarm rules configured on the connected account."""
    conn = await _resolve(ctx, params.connection_id)
    if not conn:
        return _no_connection()
    try:
        body = await ali.call(
            ctx, "cms", "", "DescribeMetricRuleList", conn.get("access_key_id", ""),
            conn.get("access_key_secret", ""), "list CloudMonitor alarm rules",
            {"PageSize": "100"},
        )
    except ali.ProviderError as e:
        return _err("Couldn't list CloudMonitor alarm rules", e)
    items = ((body.get("Alarms") or {}).get("Alarm")) or []
    out = [
        MonitorAlert(
            rule_id=a.get("RuleId", ""), rule_name=a.get("RuleName", ""),
            metric_name=a.get("MetricName", ""), namespace=a.get("Namespace", ""),
            state=a.get("State", ""),
        )
        for a in items
    ]
    return ActionResult.success(MonitorAlertList(alerts=out), summary="Metric alerts listed.")


# ──────────────────────────────────────────────────────────────────────────
# Billing
# ──────────────────────────────────────────────────────────────────────────


@chat.function(
    "query_costs",
    "Read the connected Alibaba Cloud account's current balance via BSS OpenAPI.",
    action_type="read",
    chain_callable=True,
    data_model=BillingBalance,
)
async def query_costs(ctx, params: GetBillingParams) -> ActionResult:
    """Read the connected account's current balance via BSS OpenAPI."""
    conn = await _resolve(ctx, params.connection_id)
    if not conn:
        return _no_connection()
    try:
        body = await ali.call(
            ctx, "bssopenapi", "", "QueryAccountBalance", conn.get("access_key_id", ""),
            conn.get("access_key_secret", ""), "read the account balance",
        )
    except ali.ProviderError as e:
        return _err("Couldn't read the account balance", e)
    data = body.get("Data", {}) if isinstance(body, dict) else {}
    return ActionResult.success(BillingBalance(
        available_amount=data.get("AvailableAmount", ""),
        available_cash_amount=data.get("AvailableCashAmount", ""),
        credit_amount=data.get("CreditAmount", ""),
        currency=data.get("Currency", "CNY"),
    ), summary="Query costs done.")
