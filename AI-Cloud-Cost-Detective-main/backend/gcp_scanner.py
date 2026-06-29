"""GCP resource scanner — scans a project for cost optimization opportunities."""

import concurrent.futures
import datetime
import json
import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor, wait as _futures_wait
from dataclasses import dataclass
from typing import Callable, Optional

logger = logging.getLogger(__name__)

_creds_local = threading.local()


@dataclass
class GCPCredentials:
    project_id: str
    project_name: str = ""


def _age_days_from_str(dt_str: str) -> int:
    if not dt_str:
        return 0
    try:
        dt = datetime.datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        now = datetime.datetime.now(datetime.timezone.utc)
        return (now - dt).days
    except Exception:
        return 0


def _b(type_: str, id_: str, name: str, region: str, creds: GCPCredentials) -> dict:
    return {
        "type": type_,
        "id": str(id_),
        "name": name or str(id_),
        "region": region,
        "account_id": creds.project_id,
        "account_name": creds.project_name,
    }


def _region_from_zone(zone: str) -> str:
    """Convert 'us-central1-a' → 'us-central1'."""
    parts = zone.split("/")
    z = parts[-1] if parts else zone
    segs = z.split("-")
    return "-".join(segs[:-1]) if len(segs) >= 3 else z


def _get_credentials():
    """Return GCP credentials from env var JSON or Application Default Credentials."""
    try:
        import google.auth
        from google.oauth2 import service_account
    except ImportError:
        raise RuntimeError(
            "google-auth not installed. Run: pip install google-auth google-auth-httplib2 google-api-python-client"
        )
    creds_json = os.getenv("GCP_CREDENTIALS_JSON", "").strip()
    scopes = ["https://www.googleapis.com/auth/cloud-platform"]
    if creds_json:
        try:
            info = json.loads(creds_json)
        except (json.JSONDecodeError, ValueError) as exc:
            raise RuntimeError("GCP_CREDENTIALS_JSON is not valid JSON") from exc
        # Validate required service-account fields to prevent SSRF via crafted token_uri
        required = {"type", "project_id", "private_key_id", "private_key", "client_email"}
        missing = required - set(info.keys())
        if missing:
            raise RuntimeError(f"GCP_CREDENTIALS_JSON is missing fields: {', '.join(sorted(missing))}")
        if info.get("type") != "service_account":
            raise RuntimeError("GCP_CREDENTIALS_JSON must be a service_account key file")
        # Only allow Google's own token endpoint
        token_uri = info.get("token_uri", "https://oauth2.googleapis.com/token")
        if not token_uri.startswith("https://oauth2.googleapis.com/"):
            raise RuntimeError("GCP_CREDENTIALS_JSON contains an untrusted token_uri")
        return service_account.Credentials.from_service_account_info(info, scopes=scopes)
    credentials, _ = google.auth.default(scopes=scopes)
    return credentials


def _get_credentials_from_key(key_str: str):
    """Return Google credentials from a service account JSON string, or None for a raw API key."""
    val = (key_str or "").strip()
    if not val:
        return _get_credentials()
    if val.startswith("{"):
        try:
            from google.oauth2 import service_account
        except ImportError:
            raise RuntimeError("google-auth not installed. Run: pip install google-auth google-auth-httplib2 google-api-python-client")
        try:
            info = json.loads(val)
        except json.JSONDecodeError as exc:
            raise RuntimeError("GCP credentials is not valid JSON") from exc
        required = {"type", "project_id", "private_key_id", "private_key", "client_email"}
        missing = required - set(info.keys())
        if missing:
            raise RuntimeError(f"GCP credentials JSON missing fields: {', '.join(sorted(missing))}")
        if info.get("type") != "service_account":
            raise RuntimeError("GCP credentials must be a service_account key file")
        token_uri = info.get("token_uri", "https://oauth2.googleapis.com/token")
        if not token_uri.startswith("https://oauth2.googleapis.com/"):
            raise RuntimeError("GCP credentials contains an untrusted token_uri")
        scopes = ["https://www.googleapis.com/auth/cloud-platform"]
        return service_account.Credentials.from_service_account_info(info, scopes=scopes)
    # Raw API key — caller should use developerKey=; signal with None
    return None


def _build(service_name: str, version: str):
    from googleapiclient.discovery import build
    # Use thread-local credentials when set (e.g. from a user-supplied key)
    override_creds = getattr(_creds_local, "google_creds", None)
    override_key   = getattr(_creds_local, "api_key", None)
    if override_creds is not None:
        return build(service_name, version, credentials=override_creds)
    if override_key:
        return build(service_name, version, developerKey=override_key)
    return build(service_name, version, credentials=_get_credentials())


# ════════════════════════════════════════════════════════════════════════════════
#  COMPUTE
# ════════════════════════════════════════════════════════════════════════════════

def scan_compute_instances(creds: GCPCredentials, regions: list[str]) -> list:
    try:
        svc = _build("compute", "v1")
    except Exception:
        return []
    region_set = set(regions) if regions else None
    resources = []
    try:
        request = svc.instances().aggregatedList(project=creds.project_id, maxResults=500)
        while request is not None:
            resp = request.execute()
            for zone_key, zone_data in resp.get("items", {}).items():
                for inst in zone_data.get("instances", []):
                    zone = zone_key.split("/")[-1]
                    region = _region_from_zone(zone)
                    if region_set and region not in region_set:
                        continue
                    r = _b("GCEInstance", inst["id"], inst["name"], region, creds)
                    r.update({
                        "zone": zone,
                        "machine_type": inst.get("machineType", "").split("/")[-1],
                        "status": inst.get("status", ""),
                        "creation_timestamp": inst.get("creationTimestamp", ""),
                        "tags": dict(inst.get("labels", {})),
                    })
                    resources.append(r)
            request = svc.instances().aggregatedList_next(
                previous_request=request, previous_response=resp
            )
    except Exception:
        pass
    return resources


def scan_persistent_disks(creds: GCPCredentials, regions: list[str]) -> list:
    try:
        svc = _build("compute", "v1")
    except Exception:
        return []
    region_set = set(regions) if regions else None
    resources = []
    try:
        request = svc.disks().aggregatedList(project=creds.project_id, maxResults=500)
        while request is not None:
            resp = request.execute()
            for zone_key, zone_data in resp.get("items", {}).items():
                for disk in zone_data.get("disks", []):
                    zone = zone_key.split("/")[-1]
                    region = _region_from_zone(zone)
                    if region_set and region not in region_set:
                        continue
                    r = _b("GCEDisk", disk["id"], disk["name"], region, creds)
                    r.update({
                        "zone": zone,
                        "size_gb": int(disk.get("sizeGb", 0)),
                        "disk_type": disk.get("type", "").split("/")[-1],
                        "status": disk.get("status", ""),
                        "attached": bool(disk.get("users")),
                        "creation_timestamp": disk.get("creationTimestamp", ""),
                        "tags": dict(disk.get("labels", {})),
                    })
                    resources.append(r)
            request = svc.disks().aggregatedList_next(
                previous_request=request, previous_response=resp
            )
    except Exception:
        pass
    return resources


def scan_static_ips(creds: GCPCredentials, regions: list[str]) -> list:
    try:
        svc = _build("compute", "v1")
    except Exception:
        return []
    region_set = set(regions) if regions else None
    resources = []
    try:
        # Global addresses
        resp = svc.globalAddresses().list(project=creds.project_id).execute()
        for addr in resp.get("items", []):
            r = _b("GCPStaticIP", addr["id"], addr["name"], "global", creds)
            r.update({
                "address": addr.get("address", ""),
                "status": addr.get("status", ""),
                "in_use": addr.get("status") == "IN_USE",
                "address_type": addr.get("addressType", ""),
            })
            resources.append(r)
        # Regional addresses
        req2 = svc.addresses().aggregatedList(project=creds.project_id).execute()
        for region_key, region_data in req2.get("items", {}).items():
            region = region_key.split("/")[-1]
            if region_set and region not in region_set:
                continue
            for addr in region_data.get("addresses", []):
                r = _b("GCPStaticIP", addr["id"], addr["name"], region, creds)
                r.update({
                    "address": addr.get("address", ""),
                    "status": addr.get("status", ""),
                    "in_use": addr.get("status") == "IN_USE",
                    "address_type": addr.get("addressType", ""),
                })
                resources.append(r)
    except Exception:
        pass
    return resources


def scan_disk_snapshots(creds: GCPCredentials, regions: list[str]) -> list:
    try:
        svc = _build("compute", "v1")
    except Exception:
        return []
    resources = []
    try:
        request = svc.snapshots().list(project=creds.project_id, maxResults=500)
        while request is not None:
            resp = request.execute()
            for snap in resp.get("items", []):
                r = _b("GCPSnapshot", snap["id"], snap["name"], "global", creds)
                r.update({
                    "disk_size_gb": int(snap.get("diskSizeGb", 0)),
                    "storage_bytes": int(snap.get("storageBytes", 0)),
                    "status": snap.get("status", ""),
                    "creation_timestamp": snap.get("creationTimestamp", ""),
                    "age_days": _age_days_from_str(snap.get("creationTimestamp", "")),
                    "tags": dict(snap.get("labels", {})),
                })
                resources.append(r)
            request = svc.snapshots().list_next(
                previous_request=request, previous_response=resp
            )
    except Exception:
        pass
    return resources


def scan_gke_clusters(creds: GCPCredentials, regions: list[str]) -> list:
    try:
        svc = _build("container", "v1")
    except Exception:
        return []
    region_set = set(regions) if regions else None
    resources = []
    try:
        resp = svc.projects().locations().clusters().list(
            parent=f"projects/{creds.project_id}/locations/-"
        ).execute()
        for cluster in resp.get("clusters", []):
            loc = cluster.get("location", "")
            region = _region_from_zone(loc) if loc.count("-") >= 2 else loc
            if region_set and region not in region_set:
                continue
            node_count = sum(
                p.get("initialNodeCount", 0) for p in cluster.get("nodePools", [])
            )
            r = _b("GKECluster", cluster.get("selfLink", cluster["name"]), cluster["name"], region, creds)
            r.update({
                "status": cluster.get("status", ""),
                "master_version": cluster.get("currentMasterVersion", ""),
                "node_count": node_count,
                "tags": dict(cluster.get("resourceLabels", {})),
            })
            resources.append(r)
    except Exception:
        pass
    return resources


# ════════════════════════════════════════════════════════════════════════════════
#  STORAGE & DATABASES
# ════════════════════════════════════════════════════════════════════════════════

def scan_gcs_buckets(creds: GCPCredentials, regions: list[str]) -> list:
    try:
        svc = _build("storage", "v1")
    except Exception:
        return []
    resources = []
    try:
        request = svc.buckets().list(project=creds.project_id, maxResults=200)
        while request is not None:
            resp = request.execute()
            for bucket in resp.get("items", []):
                loc = bucket.get("location", "").lower()
                r = _b("GCSBucket", bucket["id"], bucket["name"], loc, creds)
                r.update({
                    "storage_class": bucket.get("storageClass", ""),
                    "creation_time": bucket.get("timeCreated", ""),
                    "location_type": bucket.get("locationType", ""),
                    "tags": dict(bucket.get("labels", {})),
                })
                resources.append(r)
            request = svc.buckets().list_next(
                previous_request=request, previous_response=resp
            )
    except Exception:
        pass
    return resources


def scan_cloud_sql(creds: GCPCredentials, regions: list[str]) -> list:
    try:
        svc = _build("sqladmin", "v1beta4")
    except Exception:
        return []
    region_set = set(regions) if regions else None
    resources = []
    try:
        resp = svc.instances().list(project=creds.project_id).execute()
        for inst in resp.get("items", []):
            region = inst.get("region", "")
            if region_set and region not in region_set:
                continue
            settings = inst.get("settings", {})
            r = _b("CloudSQLInstance", inst["name"], inst["name"], region, creds)
            r.update({
                "database_version": inst.get("databaseVersion", ""),
                "tier": settings.get("tier", ""),
                "state": inst.get("state", ""),
                "availability_type": settings.get("availabilityType", ""),
                "data_disk_size_gb": int(settings.get("dataDiskSizeGb", 0)),
                "tags": dict(settings.get("userLabels", {})),
            })
            resources.append(r)
    except Exception:
        pass
    return resources


# ════════════════════════════════════════════════════════════════════════════════
#  SERVERLESS
# ════════════════════════════════════════════════════════════════════════════════

def scan_cloud_functions(creds: GCPCredentials, regions: list[str]) -> list:
    try:
        svc = _build("cloudfunctions", "v1")
    except Exception:
        return []
    region_set = set(regions) if regions else None
    resources = []
    try:
        resp = svc.projects().locations().functions().list(
            parent=f"projects/{creds.project_id}/locations/-"
        ).execute()
        for func in resp.get("functions", []):
            parts = func.get("name", "").split("/")
            # name format: projects/{p}/locations/{loc}/functions/{name}
            region = parts[3] if len(parts) > 3 else ""
            if region_set and region not in region_set:
                continue
            r = _b("CloudFunction", func["name"], parts[-1] if parts else func["name"], region, creds)
            r.update({
                "status": func.get("status", ""),
                "runtime": func.get("runtime", ""),
                "available_memory_mb": func.get("availableMemoryMb", 0),
                "update_time": func.get("updateTime", ""),
                "tags": dict(func.get("labels", {})),
            })
            resources.append(r)
    except Exception:
        pass
    return resources


def scan_cloud_run(creds: GCPCredentials, regions: list[str]) -> list:
    try:
        svc = _build("run", "v1")
    except Exception:
        return []
    region_set = set(regions) if regions else None
    resources = []
    try:
        resp = svc.projects().locations().services().list(
            parent=f"projects/{creds.project_id}/locations/-"
        ).execute()
        for service in resp.get("items", []):
            meta = service.get("metadata", {})
            self_link = meta.get("selfLink", "")
            parts = self_link.split("/")
            try:
                region = parts[parts.index("locations") + 1]
            except (ValueError, IndexError):
                region = ""
            if region_set and region not in region_set:
                continue
            name = meta.get("name", "").split("/")[-1]
            r = _b("CloudRunService", meta.get("uid", name), name, region, creds)
            r.update({
                "url": service.get("status", {}).get("url", ""),
                "ready": any(
                    c.get("type") == "Ready" and c.get("status") == "True"
                    for c in service.get("status", {}).get("conditions", [])
                ),
                "tags": dict(meta.get("labels", {})),
            })
            resources.append(r)
    except Exception:
        pass
    return resources


def scan_bigquery_datasets(creds: GCPCredentials, regions: list[str]) -> list:
    try:
        svc = _build("bigquery", "v2")
    except Exception:
        return []
    resources = []
    try:
        req = svc.datasets().list(projectId=creds.project_id, all=True)
        while req is not None:
            resp = req.execute()
            for ds in resp.get("datasets", []):
                ds_ref = ds.get("datasetReference", {})
                ds_id = ds_ref.get("datasetId", "")
                location = ds.get("location", "").lower()
                r = _b("BigQueryDataset", f"{creds.project_id}.{ds_id}", ds_id, location, creds)
                r.update({
                    "location": location,
                    "tags": dict(ds.get("labels", {})),
                })
                try:
                    detail = svc.datasets().get(
                        projectId=creds.project_id, datasetId=ds_id
                    ).execute()
                    r["creation_time"] = detail.get("creationTime", "")
                    r["last_modified"] = detail.get("lastModifiedTime", "")
                except Exception:
                    pass
                resources.append(r)
            req = svc.datasets().list_next(previous_request=req, previous_response=resp)
    except Exception:
        pass
    return resources


def scan_cloud_spanner(creds: GCPCredentials, regions: list[str]) -> list:
    try:
        svc = _build("spanner", "v1")
    except Exception:
        return []
    resources = []
    try:
        resp = svc.projects().instances().list(
            parent=f"projects/{creds.project_id}"
        ).execute()
        for inst in resp.get("instances", []):
            config = inst.get("config", "").split("/")[-1]
            region = config.replace("regional-", "") if config.startswith("regional-") else config
            r = _b("SpannerInstance", inst["name"], inst["name"].split("/")[-1], region, creds)
            r.update({
                "display_name": inst.get("displayName", ""),
                "node_count": inst.get("nodeCount", 0),
                "processing_units": inst.get("processingUnits", 0),
                "state": inst.get("state", ""),
                "tags": dict(inst.get("labels", {})),
            })
            resources.append(r)
    except Exception:
        pass
    return resources


def scan_pubsub_topics(creds: GCPCredentials, regions: list[str]) -> list:
    try:
        svc = _build("pubsub", "v1")
    except Exception:
        return []
    resources = []
    try:
        req = svc.projects().topics().list(project=f"projects/{creds.project_id}")
        while req is not None:
            resp = req.execute()
            for topic in resp.get("topics", []):
                name = topic["name"].split("/")[-1]
                r = _b("PubSubTopic", topic["name"], name, "global", creds)
                r.update({
                    "message_retention_duration": topic.get("messageRetentionDuration", ""),
                    "tags": dict(topic.get("labels", {})),
                })
                resources.append(r)
            req = svc.projects().topics().list_next(previous_request=req, previous_response=resp)
    except Exception:
        pass
    return resources


def scan_dataproc_clusters(creds: GCPCredentials, regions: list[str]) -> list:
    try:
        svc = _build("dataproc", "v1")
    except Exception:
        return []
    region_set = set(regions) if regions else None
    resources = []
    target_regions = list(region_set) if region_set else ["global"]
    for region in target_regions:
        try:
            resp = svc.projects().regions().clusters().list(
                projectId=creds.project_id, region=region
            ).execute()
            for cluster in resp.get("clusters", []):
                config = cluster.get("config", {})
                worker_config = config.get("workerConfig", {})
                r = _b("DataprocCluster",
                       cluster.get("clusterUuid", cluster["clusterName"]),
                       cluster["clusterName"], region, creds)
                r.update({
                    "status": cluster.get("status", {}).get("state", ""),
                    "master_machine_type": config.get("masterConfig", {}).get("machineTypeUri", "").split("/")[-1],
                    "worker_count": worker_config.get("numInstances", 0),
                    "tags": dict(cluster.get("labels", {})),
                })
                resources.append(r)
        except Exception:
            continue
    return resources


def scan_app_engine(creds: GCPCredentials, regions: list[str]) -> list:
    try:
        svc = _build("appengine", "v1")
    except Exception:
        return []
    resources = []
    try:
        app = svc.apps().get(appsId=creds.project_id).execute()
        location = app.get("locationId", "")
        req = svc.apps().services().list(appsId=creds.project_id)
        while req is not None:
            resp = req.execute()
            for service in resp.get("services", []):
                r = _b("AppEngineService", service.get("name", ""), service["id"], location, creds)
                r.update({
                    "split_traffic": service.get("split", {}),
                })
                resources.append(r)
            req = svc.apps().services().list_next(previous_request=req, previous_response=resp)
    except Exception:
        pass
    return resources


def scan_memorystore_redis(creds: GCPCredentials, regions: list[str]) -> list:
    try:
        svc = _build("redis", "v1")
    except Exception:
        return []
    region_set = set(regions) if regions else None
    resources = []
    try:
        resp = svc.projects().locations().instances().list(
            parent=f"projects/{creds.project_id}/locations/-"
        ).execute()
        for inst in resp.get("instances", []):
            loc = inst.get("locationId", "")
            if not loc:
                name_parts = inst.get("name", "").split("/")
                loc = name_parts[3] if len(name_parts) > 3 else ""
            region = _region_from_zone(loc) if loc.count("-") >= 2 else loc
            if region_set and region not in region_set:
                continue
            r = _b("MemorystoreRedis", inst["name"], inst["name"].split("/")[-1], region, creds)
            r.update({
                "tier": inst.get("tier", ""),
                "memory_size_gb": inst.get("memorySizeGb", 0),
                "state": inst.get("state", ""),
                "redis_version": inst.get("redisVersion", ""),
                "tags": dict(inst.get("labels", {})),
            })
            resources.append(r)
    except Exception:
        pass
    return resources


def scan_artifact_registry(creds: GCPCredentials, regions: list[str]) -> list:
    try:
        svc = _build("artifactregistry", "v1")
    except Exception:
        return []
    region_set = set(regions) if regions else None
    resources = []
    try:
        resp = svc.projects().locations().repositories().list(
            parent=f"projects/{creds.project_id}/locations/-"
        ).execute()
        for repo in resp.get("repositories", []):
            parts = repo["name"].split("/")
            region = parts[3] if len(parts) > 3 else ""
            if region_set and region not in region_set:
                continue
            r = _b("ArtifactRegistry", repo["name"], parts[-1], region, creds)
            r.update({
                "format": repo.get("format", ""),
                "description": repo.get("description", ""),
                "tags": dict(repo.get("labels", {})),
            })
            resources.append(r)
    except Exception:
        pass
    return resources


def scan_cloud_bigtable(creds: GCPCredentials, regions: list[str]) -> list:
    try:
        svc = _build("bigtableadmin", "v2")
    except Exception:
        return []
    resources = []
    try:
        resp = svc.projects().instances().list(
            parent=f"projects/{creds.project_id}"
        ).execute()
        for inst in resp.get("instances", []):
            region = ""
            try:
                clusters_resp = svc.projects().instances().clusters().list(
                    parent=inst["name"]
                ).execute()
                for cluster in clusters_resp.get("clusters", []):
                    loc = cluster.get("location", "").split("/")[-1]
                    region = _region_from_zone(loc) if loc.count("-") >= 2 else loc
                    break
            except Exception:
                pass
            r = _b("BigtableInstance", inst["name"], inst["name"].split("/")[-1], region, creds)
            r.update({
                "display_name": inst.get("displayName", ""),
                "state": inst.get("state", ""),
                "instance_type": inst.get("type", ""),
                "tags": dict(inst.get("labels", {})),
            })
            resources.append(r)
    except Exception:
        pass
    return resources


def scan_vertex_ai_endpoints(creds: GCPCredentials, regions: list[str]) -> list:
    try:
        svc = _build("aiplatform", "v1")
    except Exception:
        return []
    region_set = set(regions) if regions else None
    resources = []
    try:
        resp = svc.projects().locations().endpoints().list(
            parent=f"projects/{creds.project_id}/locations/-"
        ).execute()
        for endpoint in resp.get("endpoints", []):
            parts = endpoint["name"].split("/")
            region = parts[3] if len(parts) > 3 else ""
            if region_set and region not in region_set:
                continue
            r = _b("VertexAIEndpoint", endpoint["name"],
                   endpoint.get("displayName", parts[-1]), region, creds)
            r.update({
                "deployed_models": len(endpoint.get("deployedModels", [])),
                "create_time": endpoint.get("createTime", ""),
                "tags": dict(endpoint.get("labels", {})),
            })
            resources.append(r)
    except Exception:
        pass
    return resources


# ════════════════════════════════════════════════════════════════════════════════
#  Service dispatch
# ════════════════════════════════════════════════════════════════════════════════

_SERVICE_MAP: dict[str, Callable[..., list]] = {
    "compute_instances":   scan_compute_instances,
    "persistent_disks":    scan_persistent_disks,
    "static_ips":          scan_static_ips,
    "snapshots":           scan_disk_snapshots,
    "gke_clusters":        scan_gke_clusters,
    "gcs_buckets":         scan_gcs_buckets,
    "cloud_sql":           scan_cloud_sql,
    "cloud_functions":     scan_cloud_functions,
    "cloud_run":           scan_cloud_run,
    "bigquery_datasets":   scan_bigquery_datasets,
    "cloud_spanner":       scan_cloud_spanner,
    "pubsub_topics":       scan_pubsub_topics,
    "dataproc_clusters":   scan_dataproc_clusters,
    "app_engine":          scan_app_engine,
    "memorystore_redis":   scan_memorystore_redis,
    "artifact_registry":   scan_artifact_registry,
    "cloud_bigtable":      scan_cloud_bigtable,
    "vertex_ai_endpoints": scan_vertex_ai_endpoints,
}


def scan_resources(
    project_id: str,
    regions: list[str],
    services: list[str],
    progress_callback: Optional[Callable[[str], None]] = None,
    project_name: str = "",
    api_key: str = "",
) -> dict:
    """Scan GCP resources in a project and return resources keyed by service."""
    creds = GCPCredentials(
        project_id=project_id,
        project_name=project_name or project_id,
    )

    # Resolve credentials from the supplied key once (thread-safe: propagated per worker)
    resolved_google_creds = None
    resolved_raw_key = None
    if api_key:
        resolved_google_creds = _get_credentials_from_key(api_key)
        if resolved_google_creds is None:
            resolved_raw_key = api_key  # plain API key

    def _progress(msg: str):
        if progress_callback:
            progress_callback(msg)

    services_to_scan = [s for s in services if s in _SERVICE_MAP]
    result: dict[str, list] = {}

    def _scan_one(service_key: str) -> tuple[str, list]:
        # Propagate credentials into this worker thread's local storage
        if resolved_google_creds is not None:
            _creds_local.google_creds = resolved_google_creds
            _creds_local.api_key = None
        elif resolved_raw_key:
            _creds_local.google_creds = None
            _creds_local.api_key = resolved_raw_key
        else:
            _creds_local.google_creds = None
            _creds_local.api_key = None
        _progress(f"GCP: scanning {service_key}...")
        try:
            return service_key, _SERVICE_MAP[service_key](creds, regions)
        except Exception as e:
            logger.warning("gcp_scanner.error", extra={"service": service_key, "error": str(e)})
            _progress(f"GCP: {service_key} scan skipped (check server logs for details)")
            return service_key, []

    _SCAN_TIMEOUT = int(os.environ.get("SCAN_TASK_TIMEOUT", "600"))
    pool = ThreadPoolExecutor(max_workers=5)
    try:
        futs = {pool.submit(_scan_one, s): s for s in services_to_scan}
        done, pending = _futures_wait(futs, timeout=_SCAN_TIMEOUT)
        if pending:
            logger.warning(
                "gcp_scanner.timeout",
                extra={"detail": f"{len(pending)} GCP scan task(s) did not complete within {_SCAN_TIMEOUT}s"},
            )
        for fut in done:
            try:
                key, items = fut.result()
                result[key] = items
            except Exception as e:
                logger.warning("gcp_scanner.task_error", extra={"error": str(e)})
    finally:
        pool.shutdown(wait=False, cancel_futures=True)

    return result
