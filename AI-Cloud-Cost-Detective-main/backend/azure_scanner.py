"""Azure resource scanner — scans a subscription for cost optimization opportunities."""

import concurrent.futures
import datetime
import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor, wait as _futures_wait
from dataclasses import dataclass
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# Thread-local storage for credential injection during scans
_tls = threading.local()


@dataclass
class AzureCredentials:
    subscription_id: str
    subscription_name: str = ""


def _dt(value) -> str:
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _age_days(dt_value) -> int:
    if dt_value is None:
        return 0
    now = datetime.datetime.now(datetime.timezone.utc)
    if getattr(dt_value, "tzinfo", None) is None:
        dt_value = dt_value.replace(tzinfo=datetime.timezone.utc)
    return (now - dt_value).days


def _rg_from_id(resource_id: str) -> str:
    """Extract resource group name from Azure resource ID."""
    parts = (resource_id or "").split("/")
    try:
        idx = next(i for i, p in enumerate(parts) if p.lower() == "resourcegroups")
        return parts[idx + 1]
    except (StopIteration, IndexError):
        return ""


def _b(type_: str, id_: str, name: str, location: str, creds: AzureCredentials) -> dict:
    return {
        "type": type_,
        "id": id_,
        "name": name or id_,
        "region": (location or "").lower().replace(" ", ""),
        "account_id": creds.subscription_id,
        "account_name": creds.subscription_name,
        "resource_group": _rg_from_id(id_),
    }


def _loc_set(locations: list[str]) -> Optional[set]:
    if not locations:
        return None
    return {loc.lower().replace(" ", "") for loc in locations}


def _get_credential(tenant_id: str = "", client_id: str = "", client_secret: str = ""):
    """
    Return an Azure credential.
    Priority: thread-local (set by scan workers) → explicit params from UI → env vars → DefaultAzureCredential.
    """
    try:
        from azure.identity import ClientSecretCredential, DefaultAzureCredential
    except ImportError:
        raise RuntimeError(
            "azure-identity not installed. Run: pip install azure-identity"
        )
    # Thread-local is injected into each worker thread during scan_resources execution
    if hasattr(_tls, 'credential') and _tls.credential is not None:
        return _tls.credential
    # Explicit credentials from UI
    if tenant_id and client_id and client_secret:
        return ClientSecretCredential(tenant_id, client_id, client_secret)
    # Env var fallback (only for DefaultAzureCredential-compatible setups like managed identity / CLI)
    t = os.getenv("AZURE_TENANT_ID", "").strip()
    c = os.getenv("AZURE_CLIENT_ID", "").strip()
    s = os.getenv("AZURE_CLIENT_SECRET", "").strip()
    if t and c and s:
        return ClientSecretCredential(t, c, s)
    return DefaultAzureCredential()


def _worker_init(cred) -> None:
    """Initializer for ThreadPoolExecutor workers — injects the credential into thread-local storage."""
    _tls.credential = cred


# ════════════════════════════════════════════════════════════════════════════════
#  COMPUTE
# ════════════════════════════════════════════════════════════════════════════════

def scan_virtual_machines(creds: AzureCredentials, locations: list[str]) -> list:
    try:
        from azure.mgmt.compute import ComputeManagementClient
    except ImportError:
        return []
    credential = _get_credential()
    client = ComputeManagementClient(credential, creds.subscription_id)
    locs = _loc_set(locations)
    resources = []
    try:
        vms = list(client.virtual_machines.list_all())
    except Exception:
        return []
    for vm in vms:
        loc = (vm.location or "").lower().replace(" ", "")
        if locs and loc not in locs:
            continue
        power_state = ""
        try:
            iv = client.virtual_machines.instance_view(
                resource_group_name=_rg_from_id(vm.id or ""),
                vm_name=vm.name,
            )
            for s in (iv.statuses or []):
                if s.code and s.code.startswith("PowerState/"):
                    power_state = s.code.replace("PowerState/", "")
                    break
        except Exception:
            pass
        r = _b("AzureVM", vm.id or vm.name, vm.name, vm.location, creds)
        r.update({
            "vm_size": (vm.hardware_profile.vm_size if vm.hardware_profile else "") or "",
            "power_state": power_state,
            "os_type": (
                vm.storage_profile.os_disk.os_type
                if vm.storage_profile and vm.storage_profile.os_disk
                else ""
            ) or "",
            "tags": dict(vm.tags or {}),
        })
        resources.append(r)
    return resources


def scan_managed_disks(creds: AzureCredentials, locations: list[str]) -> list:
    try:
        from azure.mgmt.compute import ComputeManagementClient
    except ImportError:
        return []
    credential = _get_credential()
    client = ComputeManagementClient(credential, creds.subscription_id)
    locs = _loc_set(locations)
    resources = []
    try:
        disks = list(client.disks.list())
    except Exception:
        return []
    for disk in disks:
        loc = (disk.location or "").lower().replace(" ", "")
        if locs and loc not in locs:
            continue
        r = _b("AzureDisk", disk.id or disk.name, disk.name, disk.location, creds)
        r.update({
            "disk_size_gb": disk.disk_size_gb or 0,
            "sku": (disk.sku.name if disk.sku else "") or "",
            "disk_state": disk.disk_state or "",
            "attached": (disk.disk_state or "") == "Attached",
            "tags": dict(disk.tags or {}),
        })
        resources.append(r)
    return resources


def scan_disk_snapshots(creds: AzureCredentials, locations: list[str]) -> list:
    try:
        from azure.mgmt.compute import ComputeManagementClient
    except ImportError:
        return []
    credential = _get_credential()
    client = ComputeManagementClient(credential, creds.subscription_id)
    locs = _loc_set(locations)
    resources = []
    try:
        snaps = list(client.snapshots.list())
    except Exception:
        return []
    for snap in snaps:
        loc = (snap.location or "").lower().replace(" ", "")
        if locs and loc not in locs:
            continue
        r = _b("AzureSnapshot", snap.id or snap.name, snap.name, snap.location, creds)
        r.update({
            "disk_size_gb": snap.disk_size_gb or 0,
            "age_days": _age_days(snap.time_created),
            "incremental": snap.incremental or False,
            "tags": dict(snap.tags or {}),
        })
        resources.append(r)
    return resources


def scan_aks_clusters(creds: AzureCredentials, locations: list[str]) -> list:
    try:
        from azure.mgmt.containerservice import ContainerServiceClient
    except ImportError:
        return []
    credential = _get_credential()
    client = ContainerServiceClient(credential, creds.subscription_id)
    locs = _loc_set(locations)
    resources = []
    try:
        clusters = list(client.managed_clusters.list())
    except Exception:
        return []
    for cluster in clusters:
        loc = (cluster.location or "").lower().replace(" ", "")
        if locs and loc not in locs:
            continue
        node_count = sum(p.count or 0 for p in (cluster.agent_pool_profiles or []))
        r = _b("AzureAKS", cluster.id or cluster.name, cluster.name, cluster.location, creds)
        r.update({
            "kubernetes_version": cluster.kubernetes_version or "",
            "provisioning_state": cluster.provisioning_state or "",
            "node_count": node_count,
            "tags": dict(cluster.tags or {}),
        })
        resources.append(r)
    return resources


# ════════════════════════════════════════════════════════════════════════════════
#  STORAGE & DATABASES
# ════════════════════════════════════════════════════════════════════════════════

def scan_storage_accounts(creds: AzureCredentials, locations: list[str]) -> list:
    try:
        from azure.mgmt.storage import StorageManagementClient
    except ImportError:
        return []
    credential = _get_credential()
    client = StorageManagementClient(credential, creds.subscription_id)
    locs = _loc_set(locations)
    resources = []
    try:
        accounts = list(client.storage_accounts.list())
    except Exception:
        return []
    for acct in accounts:
        loc = (acct.location or "").lower().replace(" ", "")
        if locs and loc not in locs:
            continue
        r = _b("AzureStorageAccount", acct.id or acct.name, acct.name, acct.location, creds)
        r.update({
            "kind": acct.kind or "",
            "sku": (acct.sku.name if acct.sku else "") or "",
            "access_tier": acct.access_tier or "",
            "creation_time": _dt(acct.creation_time),
            "tags": dict(acct.tags or {}),
        })
        resources.append(r)
    return resources


def scan_sql_databases(creds: AzureCredentials, locations: list[str]) -> list:
    try:
        from azure.mgmt.sql import SqlManagementClient
    except ImportError:
        return []
    credential = _get_credential()
    client = SqlManagementClient(credential, creds.subscription_id)
    locs = _loc_set(locations)
    resources = []
    try:
        servers = list(client.servers.list())
    except Exception:
        return []
    for server in servers:
        loc = (server.location or "").lower().replace(" ", "")
        if locs and loc not in locs:
            continue
        rg = _rg_from_id(server.id or "")
        try:
            dbs = list(client.databases.list_by_server(rg, server.name))
        except Exception:
            continue
        for db in dbs:
            if db.name == "master":
                continue
            r = _b("AzureSQLDatabase", db.id or db.name, db.name, db.location or server.location, creds)
            r.update({
                "server_name": server.name,
                "sku": (db.sku.name if db.sku else "") or "",
                "edition": (db.sku.tier if db.sku else "") or "",
                "status": db.status or "",
                "max_size_bytes": db.max_size_bytes or 0,
                "tags": dict(db.tags or {}),
            })
            resources.append(r)
    return resources


def scan_cosmosdb(creds: AzureCredentials, locations: list[str]) -> list:
    try:
        from azure.mgmt.cosmosdb import CosmosDBManagementClient
    except ImportError:
        return []
    credential = _get_credential()
    client = CosmosDBManagementClient(credential, creds.subscription_id)
    locs = _loc_set(locations)
    resources = []
    try:
        accounts = list(client.database_accounts.list())
    except Exception:
        return []
    for acct in accounts:
        loc = (acct.location or "").lower().replace(" ", "")
        if locs and loc not in locs:
            continue
        r = _b("AzureCosmosDB", acct.id or acct.name, acct.name, acct.location, creds)
        r.update({
            "kind": acct.kind or "",
            "consistency_policy": (
                acct.consistency_policy.default_consistency_level
                if acct.consistency_policy
                else ""
            ) or "",
            "tags": dict(acct.tags or {}),
        })
        resources.append(r)
    return resources


def scan_redis_cache(creds: AzureCredentials, locations: list[str]) -> list:
    try:
        from azure.mgmt.redis import RedisManagementClient
    except ImportError:
        return []
    credential = _get_credential()
    client = RedisManagementClient(credential, creds.subscription_id)
    locs = _loc_set(locations)
    resources = []
    try:
        caches = list(client.redis.list())
    except Exception:
        return []
    for cache in caches:
        loc = (cache.location or "").lower().replace(" ", "")
        if locs and loc not in locs:
            continue
        r = _b("AzureRedis", cache.id or cache.name, cache.name, cache.location, creds)
        r.update({
            "sku_name": (cache.sku.name if cache.sku else "") or "",
            "sku_capacity": (cache.sku.capacity if cache.sku else 0) or 0,
            "provisioning_state": cache.provisioning_state or "",
            "tags": dict(cache.tags or {}),
        })
        resources.append(r)
    return resources


# ════════════════════════════════════════════════════════════════════════════════
#  NETWORKING & WEB
# ════════════════════════════════════════════════════════════════════════════════

def scan_public_ips(creds: AzureCredentials, locations: list[str]) -> list:
    try:
        from azure.mgmt.network import NetworkManagementClient
    except ImportError:
        return []
    credential = _get_credential()
    client = NetworkManagementClient(credential, creds.subscription_id)
    locs = _loc_set(locations)
    resources = []
    try:
        ips = list(client.public_ip_addresses.list_all())
    except Exception:
        return []
    for ip in ips:
        loc = (ip.location or "").lower().replace(" ", "")
        if locs and loc not in locs:
            continue
        r = _b("AzurePublicIP", ip.id or ip.name, ip.name, ip.location, creds)
        r.update({
            "ip_address": ip.ip_address or "",
            "allocation_method": ip.public_ip_allocation_method or "",
            "associated": ip.ip_configuration is not None,
            "sku": (ip.sku.name if ip.sku else "") or "",
            "tags": dict(ip.tags or {}),
        })
        resources.append(r)
    return resources


def scan_app_services(creds: AzureCredentials, locations: list[str]) -> list:
    try:
        from azure.mgmt.web import WebSiteManagementClient
    except ImportError:
        return []
    credential = _get_credential()
    client = WebSiteManagementClient(credential, creds.subscription_id)
    locs = _loc_set(locations)
    resources = []
    try:
        sites = list(client.web_apps.list())
    except Exception:
        return []
    for site in sites:
        loc = (site.location or "").lower().replace(" ", "")
        if locs and loc not in locs:
            continue
        r = _b("AzureAppService", site.id or site.name, site.name, site.location, creds)
        r.update({
            "kind": site.kind or "",
            "state": site.state or "",
            "app_service_plan_id": site.server_farm_id or "",
            "tags": dict(site.tags or {}),
        })
        resources.append(r)
    return resources


def scan_app_service_plans(creds: AzureCredentials, locations: list[str]) -> list:
    try:
        from azure.mgmt.web import WebSiteManagementClient
    except ImportError:
        return []
    credential = _get_credential()
    client = WebSiteManagementClient(credential, creds.subscription_id)
    locs = _loc_set(locations)
    resources = []
    try:
        plans = list(client.app_service_plans.list())
    except Exception:
        return []
    for plan in plans:
        loc = (plan.location or "").lower().replace(" ", "")
        if locs and loc not in locs:
            continue
        r = _b("AzureAppServicePlan", plan.id or plan.name, plan.name, plan.location, creds)
        r.update({
            "sku_name": (plan.sku.name if plan.sku else "") or "",
            "sku_tier": (plan.sku.tier if plan.sku else "") or "",
            "number_of_sites": plan.number_of_sites or 0,
            "status": plan.status or "",
            "tags": dict(plan.tags or {}),
        })
        resources.append(r)
    return resources


def scan_load_balancers(creds: AzureCredentials, locations: list[str]) -> list:
    try:
        from azure.mgmt.network import NetworkManagementClient
    except ImportError:
        return []
    credential = _get_credential()
    client = NetworkManagementClient(credential, creds.subscription_id)
    locs = _loc_set(locations)
    resources = []
    try:
        lbs = list(client.load_balancers.list_all())
    except Exception:
        return []
    for lb in lbs:
        loc = (lb.location or "").lower().replace(" ", "")
        if locs and loc not in locs:
            continue
        r = _b("AzureLoadBalancer", lb.id or lb.name, lb.name, lb.location, creds)
        r.update({
            "sku": (lb.sku.name if lb.sku else "") or "",
            "frontend_count": len(lb.frontend_ip_configurations or []),
            "backend_count": len(lb.backend_address_pools or []),
            "tags": dict(lb.tags or {}),
        })
        resources.append(r)
    return resources


def scan_application_gateways(creds: AzureCredentials, locations: list[str]) -> list:
    try:
        from azure.mgmt.network import NetworkManagementClient
    except ImportError:
        return []
    credential = _get_credential()
    client = NetworkManagementClient(credential, creds.subscription_id)
    locs = _loc_set(locations)
    resources = []
    try:
        gateways = list(client.application_gateways.list_all())
    except Exception:
        return []
    for gw in gateways:
        loc = (gw.location or "").lower().replace(" ", "")
        if locs and loc not in locs:
            continue
        r = _b("AzureAppGateway", gw.id or gw.name, gw.name, gw.location, creds)
        r.update({
            "sku_name": (gw.sku.name if gw.sku else "") or "",
            "sku_tier": (gw.sku.tier if gw.sku else "") or "",
            "operational_state": gw.operational_state or "",
            "tags": dict(gw.tags or {}),
        })
        resources.append(r)
    return resources


def scan_nat_gateways(creds: AzureCredentials, locations: list[str]) -> list:
    try:
        from azure.mgmt.network import NetworkManagementClient
    except ImportError:
        return []
    credential = _get_credential()
    client = NetworkManagementClient(credential, creds.subscription_id)
    locs = _loc_set(locations)
    resources = []
    try:
        gateways = list(client.nat_gateways.list_all())
    except Exception:
        return []
    for gw in gateways:
        loc = (gw.location or "").lower().replace(" ", "")
        if locs and loc not in locs:
            continue
        r = _b("AzureNATGateway", gw.id or gw.name, gw.name, gw.location, creds)
        r.update({
            "sku_name": (gw.sku.name if gw.sku else "") or "",
            "idle_timeout_in_minutes": gw.idle_timeout_in_minutes or 0,
            "provisioning_state": gw.provisioning_state or "",
            "tags": dict(gw.tags or {}),
        })
        resources.append(r)
    return resources


def scan_key_vaults(creds: AzureCredentials, locations: list[str]) -> list:
    try:
        from azure.mgmt.keyvault import KeyVaultManagementClient
    except ImportError:
        return []
    credential = _get_credential()
    client = KeyVaultManagementClient(credential, creds.subscription_id)
    locs = _loc_set(locations)
    resources = []
    try:
        vaults = list(client.vaults.list())
    except Exception:
        return []
    for vault in vaults:
        loc = (vault.location or "").lower().replace(" ", "")
        if locs and loc not in locs:
            continue
        r = _b("AzureKeyVault", vault.id or vault.name, vault.name, vault.location, creds)
        r.update({
            "sku_name": (vault.properties.sku.name if vault.properties and vault.properties.sku else "") or "",
            "soft_delete_enabled": bool(vault.properties.enable_soft_delete if vault.properties else False),
            "tags": dict(vault.tags or {}),
        })
        resources.append(r)
    return resources


def scan_container_registry(creds: AzureCredentials, locations: list[str]) -> list:
    try:
        from azure.mgmt.containerregistry import ContainerRegistryManagementClient
    except ImportError:
        return []
    credential = _get_credential()
    client = ContainerRegistryManagementClient(credential, creds.subscription_id)
    locs = _loc_set(locations)
    resources = []
    try:
        registries = list(client.registries.list())
    except Exception:
        return []
    for reg in registries:
        loc = (reg.location or "").lower().replace(" ", "")
        if locs and loc not in locs:
            continue
        r = _b("AzureContainerRegistry", reg.id or reg.name, reg.name, reg.location, creds)
        r.update({
            "sku_name": (reg.sku.name if reg.sku else "") or "",
            "login_server": reg.login_server or "",
            "provisioning_state": reg.provisioning_state or "",
            "tags": dict(reg.tags or {}),
        })
        resources.append(r)
    return resources


def scan_service_bus(creds: AzureCredentials, locations: list[str]) -> list:
    try:
        from azure.mgmt.servicebus import ServiceBusManagementClient
    except ImportError:
        return []
    credential = _get_credential()
    client = ServiceBusManagementClient(credential, creds.subscription_id)
    locs = _loc_set(locations)
    resources = []
    try:
        namespaces = list(client.namespaces.list())
    except Exception:
        return []
    for ns in namespaces:
        loc = (ns.location or "").lower().replace(" ", "")
        if locs and loc not in locs:
            continue
        r = _b("AzureServiceBus", ns.id or ns.name, ns.name, ns.location, creds)
        r.update({
            "sku_name": (ns.sku.name if ns.sku else "") or "",
            "sku_tier": (ns.sku.tier if ns.sku else "") or "",
            "status": ns.status or "",
            "tags": dict(ns.tags or {}),
        })
        resources.append(r)
    return resources


def scan_event_hubs(creds: AzureCredentials, locations: list[str]) -> list:
    try:
        from azure.mgmt.eventhub import EventHubManagementClient
    except ImportError:
        return []
    credential = _get_credential()
    client = EventHubManagementClient(credential, creds.subscription_id)
    locs = _loc_set(locations)
    resources = []
    try:
        namespaces = list(client.namespaces.list())
    except Exception:
        return []
    for ns in namespaces:
        loc = (ns.location or "").lower().replace(" ", "")
        if locs and loc not in locs:
            continue
        r = _b("AzureEventHub", ns.id or ns.name, ns.name, ns.location, creds)
        r.update({
            "sku_name": (ns.sku.name if ns.sku else "") or "",
            "sku_capacity": (ns.sku.capacity if ns.sku else 0) or 0,
            "status": ns.status or "",
            "tags": dict(ns.tags or {}),
        })
        resources.append(r)
    return resources


def scan_postgresql(creds: AzureCredentials, locations: list[str]) -> list:
    try:
        from azure.mgmt.rdbms.postgresql import PostgreSQLManagementClient
    except ImportError:
        return []
    credential = _get_credential()
    client = PostgreSQLManagementClient(credential, creds.subscription_id)
    locs = _loc_set(locations)
    resources = []
    try:
        servers = list(client.servers.list())
    except Exception:
        return []
    for server in servers:
        loc = (server.location or "").lower().replace(" ", "")
        if locs and loc not in locs:
            continue
        r = _b("AzurePostgreSQL", server.id or server.name, server.name, server.location, creds)
        r.update({
            "sku_name": (server.sku.name if server.sku else "") or "",
            "sku_tier": (server.sku.tier if server.sku else "") or "",
            "state": server.user_visible_state or "",
            "version": server.version or "",
            "storage_mb": (server.storage_profile.storage_mb if server.storage_profile else 0) or 0,
            "tags": dict(server.tags or {}),
        })
        resources.append(r)
    return resources


def scan_mysql(creds: AzureCredentials, locations: list[str]) -> list:
    try:
        from azure.mgmt.rdbms.mysql import MySQLManagementClient
    except ImportError:
        return []
    credential = _get_credential()
    client = MySQLManagementClient(credential, creds.subscription_id)
    locs = _loc_set(locations)
    resources = []
    try:
        servers = list(client.servers.list())
    except Exception:
        return []
    for server in servers:
        loc = (server.location or "").lower().replace(" ", "")
        if locs and loc not in locs:
            continue
        r = _b("AzureMySQL", server.id or server.name, server.name, server.location, creds)
        r.update({
            "sku_name": (server.sku.name if server.sku else "") or "",
            "sku_tier": (server.sku.tier if server.sku else "") or "",
            "state": server.user_visible_state or "",
            "version": server.version or "",
            "storage_mb": (server.storage_profile.storage_mb if server.storage_profile else 0) or 0,
            "tags": dict(server.tags or {}),
        })
        resources.append(r)
    return resources


# ════════════════════════════════════════════════════════════════════════════════
#  Service dispatch
# ════════════════════════════════════════════════════════════════════════════════

_SERVICE_MAP: dict[str, Callable[..., list]] = {
    "virtual_machines":    scan_virtual_machines,
    "managed_disks":       scan_managed_disks,
    "snapshots":           scan_disk_snapshots,
    "storage_accounts":    scan_storage_accounts,
    "sql_databases":       scan_sql_databases,
    "cosmosdb":            scan_cosmosdb,
    "redis":               scan_redis_cache,
    "public_ips":          scan_public_ips,
    "app_services":        scan_app_services,
    "aks":                 scan_aks_clusters,
    "app_service_plans":   scan_app_service_plans,
    "load_balancers":      scan_load_balancers,
    "application_gateways": scan_application_gateways,
    "nat_gateways":        scan_nat_gateways,
    "key_vault":           scan_key_vaults,
    "container_registry":  scan_container_registry,
    "service_bus":         scan_service_bus,
    "event_hubs":          scan_event_hubs,
    "postgresql":          scan_postgresql,
    "mysql":               scan_mysql,
}


def scan_resources(
    subscription_id: str,
    locations: list[str],
    services: list[str],
    progress_callback: Optional[Callable[[str], None]] = None,
    subscription_name: str = "",
    credential=None,
) -> dict:
    """Scan Azure resources in a subscription and return resources keyed by service."""
    creds = AzureCredentials(
        subscription_id=subscription_id,
        subscription_name=subscription_name or subscription_id,
    )

    def _progress(msg: str):
        if progress_callback:
            progress_callback(msg)

    services_to_scan = [s for s in services if s in _SERVICE_MAP]
    result: dict[str, list] = {}

    _SCAN_TIMEOUT = int(os.environ.get("SCAN_TASK_TIMEOUT", "600"))

    def _scan_one(service_key: str) -> tuple[str, list]:
        _progress(f"Azure: scanning {service_key}...")
        try:
            return service_key, _SERVICE_MAP[service_key](creds, locations)
        except Exception as e:
            logger.warning("azure_scanner.error", extra={"service": service_key, "error": str(e)})
            _progress(f"Azure: {service_key} scan skipped (check server logs for details)")
            return service_key, []

    pool = ThreadPoolExecutor(max_workers=5, initializer=_worker_init, initargs=(credential,))
    try:
        futs = {pool.submit(_scan_one, s): s for s in services_to_scan}
        done, pending = _futures_wait(futs, timeout=_SCAN_TIMEOUT)
        if pending:
            logger.warning(
                "azure_scanner.timeout",
                extra={"detail": f"{len(pending)} Azure scan task(s) did not complete within {_SCAN_TIMEOUT}s"},
            )
        for fut in done:
            try:
                key, items = fut.result()
                result[key] = items
            except Exception as e:
                logger.warning("azure_scanner.task_error", extra={"error": str(e)})
    finally:
        pool.shutdown(wait=False, cancel_futures=True)

    return result
