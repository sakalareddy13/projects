"""AWS resource scanner — single account and AWS Organizations multi-account mode.

Covers ~87 services across compute, storage, databases, networking, analytics,
AI/ML, messaging, security, developer tools, management, media, and more.
"""

import datetime
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Optional

from botocore.exceptions import ClientError, NoCredentialsError

from cloud_organizations import AccountCredentials


# ════════════════════════════════════════════════════════════════════════════════
#  Shared helpers
# ════════════════════════════════════════════════════════════════════════════════

def _tag(resource: dict, key: str) -> str:
    for t in resource.get("Tags", []):
        if t.get("Key") == key:
            return t.get("Value", "")
    return ""

def _tags(resource: dict) -> dict:
    return {t["Key"]: t["Value"] for t in resource.get("Tags", [])}

def _dt(value) -> str:
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)

def _age(dt_value) -> int:
    if dt_value is None:
        return 0
    now = datetime.datetime.now(dt_value.tzinfo)
    return (now - dt_value).days

def _b(type_: str, id_: str, name: str, region: str, creds: AccountCredentials) -> dict:
    return {
        "type": type_,
        "id": id_,
        "name": name or id_,
        "region": region,
        "account_id": creds.account_id,
        "account_name": creds.account_name,
    }


# ════════════════════════════════════════════════════════════════════════════════
#  COMPUTE
# ════════════════════════════════════════════════════════════════════════════════

def scan_ec2(creds: AccountCredentials, region: str) -> list:
    resources = []
    try:
        ec2 = creds.get_client("ec2", region)

        # Instances
        for page in ec2.get_paginator("describe_instances").paginate():
            for res in page.get("Reservations", []):
                for inst in res.get("Instances", []):
                    name = _tag(inst, "Name") or inst["InstanceId"]
                    resources.append({
                        **_b("EC2Instance", inst["InstanceId"], name, region, creds),
                        "instance_type": inst.get("InstanceType", "unknown"),
                        "state": inst["State"]["Name"],
                        "launch_time": _dt(inst.get("LaunchTime")),
                        "platform": inst.get("Platform", "linux"),
                        "monitoring": inst.get("Monitoring", {}).get("State", "disabled"),
                        "tags": _tags(inst),
                    })

        # EBS Volumes
        for page in ec2.get_paginator("describe_volumes").paginate():
            for vol in page.get("Volumes", []):
                resources.append({
                    **_b("EBSVolume", vol["VolumeId"], _tag(vol, "Name") or vol["VolumeId"], region, creds),
                    "size_gb": vol.get("Size", 0),
                    "volume_type": vol.get("VolumeType", "gp2"),
                    "state": vol["State"],
                    "attached": len(vol.get("Attachments", [])) > 0,
                    "iops": vol.get("Iops", 0),
                    "tags": _tags(vol),
                })

        # EBS Snapshots (owned by this account)
        for page in ec2.get_paginator("describe_snapshots").paginate(OwnerIds=["self"]):
            for snap in page.get("Snapshots", []):
                resources.append({
                    **_b("EBSSnapshot", snap["SnapshotId"], _tag(snap, "Name") or snap["SnapshotId"], region, creds),
                    "size_gb": snap.get("VolumeSize", 0),
                    "state": snap.get("State", ""),
                    "age_days": _age(snap.get("StartTime")),
                    "description": snap.get("Description", ""),
                    "tags": _tags(snap),
                })

        # Elastic IPs
        for eip in ec2.describe_addresses().get("Addresses", []):
            resources.append({
                **_b("ElasticIP", eip.get("AllocationId", eip.get("PublicIp", "")), eip.get("PublicIp", ""), region, creds),
                "associated": bool(eip.get("AssociationId")),
                "instance_id": eip.get("InstanceId", ""),
                "tags": _tags(eip),
            })

        # NAT Gateways
        for page in ec2.get_paginator("describe_nat_gateways").paginate():
            for nat in page.get("NatGateways", []):
                resources.append({
                    **_b("NatGateway", nat["NatGatewayId"], _tag(nat, "Name") or nat["NatGatewayId"], region, creds),
                    "state": nat.get("State", ""),
                    "tags": _tags(nat),
                })

        # Dedicated Hosts
        for page in ec2.get_paginator("describe_hosts").paginate():
            for host in page.get("Hosts", []):
                props = host.get("HostProperties", {})
                resources.append({
                    **_b("DedicatedHost", host["HostId"], _tag(host, "Name") or host["HostId"], region, creds),
                    "instance_type": props.get("InstanceType", ""),
                    "instance_family": props.get("InstanceFamily", ""),
                    "state": host.get("State", ""),
                    "available_vcpus": host.get("AvailableCapacity", {}).get("AvailableVCpus", 0),
                    "tags": _tags(host),
                })

    except (ClientError, NoCredentialsError) as e:
        print(f"EC2 scan error in {region} ({creds.account_id}): {e}")
    return resources


def scan_elb(creds: AccountCredentials, region: str) -> list:
    resources = []
    try:
        # ALB / NLB
        elbv2 = creds.get_client("elbv2", region)
        for page in elbv2.get_paginator("describe_load_balancers").paginate():
            for lb in page.get("LoadBalancers", []):
                resources.append({
                    **_b("LoadBalancer", lb["LoadBalancerArn"], lb["LoadBalancerName"], region, creds),
                    "lb_type": lb.get("Type", ""),
                    "scheme": lb.get("Scheme", ""),
                    "state": lb.get("State", {}).get("Code", ""),
                    "dns_name": lb.get("DNSName", ""),
                    "created_time": _dt(lb.get("CreatedTime")),
                })
    except (ClientError, NoCredentialsError) as e:
        print(f"ELBv2 scan error in {region} ({creds.account_id}): {e}")
    try:
        # Classic LB
        elb = creds.get_client("elb", region)
        for page in elb.get_paginator("describe_load_balancers").paginate():
            for lb in page.get("LoadBalancerDescriptions", []):
                resources.append({
                    **_b("ClassicLoadBalancer", lb["LoadBalancerName"], lb["LoadBalancerName"], region, creds),
                    "lb_type": "classic",
                    "scheme": lb.get("Scheme", ""),
                    "instance_count": len(lb.get("Instances", [])),
                    "dns_name": lb.get("DNSName", ""),
                    "created_time": _dt(lb.get("CreatedTime")),
                })
    except (ClientError, NoCredentialsError) as e:
        print(f"ELB classic scan error in {region} ({creds.account_id}): {e}")
    return resources


def scan_autoscaling(creds: AccountCredentials, region: str) -> list:
    resources = []
    try:
        asg = creds.get_client("autoscaling", region)
        for page in asg.get_paginator("describe_auto_scaling_groups").paginate():
            for group in page.get("AutoScalingGroups", []):
                resources.append({
                    **_b("AutoScalingGroup", group["AutoScalingGroupARN"], group["AutoScalingGroupName"], region, creds),
                    "desired_capacity": group.get("DesiredCapacity", 0),
                    "min_size": group.get("MinSize", 0),
                    "max_size": group.get("MaxSize", 0),
                    "instance_count": len(group.get("Instances", [])),
                    "health_check_type": group.get("HealthCheckType", ""),
                    "tags": {t["Key"]: t["Value"] for t in group.get("Tags", [])},
                })
    except (ClientError, NoCredentialsError) as e:
        print(f"ASG scan error in {region} ({creds.account_id}): {e}")
    return resources


def scan_ecs(creds: AccountCredentials, region: str) -> list:
    resources = []
    try:
        ecs = creds.get_client("ecs", region)
        cluster_arns = []
        for page in ecs.get_paginator("list_clusters").paginate():
            cluster_arns.extend(page.get("clusterArns", []))
        if cluster_arns:
            for i in range(0, len(cluster_arns), 100):
                batch = cluster_arns[i:i+100]
                for cluster in ecs.describe_clusters(clusters=batch).get("clusters", []):
                    resources.append({
                        **_b("ECSCluster", cluster["clusterArn"], cluster["clusterName"], region, creds),
                        "status": cluster.get("status", ""),
                        "running_tasks": cluster.get("runningTasksCount", 0),
                        "pending_tasks": cluster.get("pendingTasksCount", 0),
                        "active_services": cluster.get("activeServicesCount", 0),
                        "registered_containers": cluster.get("registeredContainerInstancesCount", 0),
                    })
                    # Services in each cluster
                    svc_arns = []
                    for sp in ecs.get_paginator("list_services").paginate(cluster=cluster["clusterArn"]):
                        svc_arns.extend(sp.get("serviceArns", []))
                    for j in range(0, len(svc_arns), 10):
                        sbatch = svc_arns[j:j+10]
                        for svc in ecs.describe_services(cluster=cluster["clusterArn"], services=sbatch).get("services", []):
                            resources.append({
                                **_b("ECSService", svc["serviceArn"], svc["serviceName"], region, creds),
                                "cluster": cluster["clusterName"],
                                "status": svc.get("status", ""),
                                "desired_count": svc.get("desiredCount", 0),
                                "running_count": svc.get("runningCount", 0),
                                "launch_type": svc.get("launchType", ""),
                                "task_definition": svc.get("taskDefinition", "").split("/")[-1],
                            })
    except (ClientError, NoCredentialsError) as e:
        print(f"ECS scan error in {region} ({creds.account_id}): {e}")
    return resources


def scan_eks(creds: AccountCredentials, region: str) -> list:
    resources = []
    try:
        eks = creds.get_client("eks", region)
        for page in eks.get_paginator("list_clusters").paginate():
            for name in page.get("clusters", []):
                try:
                    cluster = eks.describe_cluster(name=name)["cluster"]
                    resources.append({
                        **_b("EKSCluster", cluster["arn"], cluster["name"], region, creds),
                        "status": cluster.get("status", ""),
                        "kubernetes_version": cluster.get("version", ""),
                        "endpoint": cluster.get("endpoint", ""),
                        "created_at": _dt(cluster.get("createdAt")),
                    })
                except ClientError:
                    pass
    except (ClientError, NoCredentialsError) as e:
        print(f"EKS scan error in {region} ({creds.account_id}): {e}")
    return resources


def scan_ecr(creds: AccountCredentials, region: str) -> list:
    resources = []
    try:
        ecr = creds.get_client("ecr", region)
        for page in ecr.get_paginator("describe_repositories").paginate():
            for repo in page.get("repositories", []):
                image_count = 0
                try:
                    img_pages = ecr.get_paginator("describe_images").paginate(repositoryName=repo["repositoryName"])
                    for ip in img_pages:
                        image_count += len(ip.get("imageDetails", []))
                except ClientError:
                    pass
                resources.append({
                    **_b("ECRRepository", repo["repositoryArn"], repo["repositoryName"], region, creds),
                    "uri": repo.get("repositoryUri", ""),
                    "image_count": image_count,
                    "image_tag_mutability": repo.get("imageTagMutability", ""),
                    "scan_on_push": repo.get("imageScanningConfiguration", {}).get("scanOnPush", False),
                    "created_at": _dt(repo.get("createdAt")),
                })
    except (ClientError, NoCredentialsError) as e:
        print(f"ECR scan error in {region} ({creds.account_id}): {e}")
    return resources


def scan_app_runner(creds: AccountCredentials, region: str) -> list:
    resources = []
    try:
        ar = creds.get_client("apprunner", region)
        for page in ar.get_paginator("list_services").paginate():
            for svc in page.get("ServiceSummaryList", []):
                resources.append({
                    **_b("AppRunnerService", svc["ServiceArn"], svc["ServiceName"], region, creds),
                    "status": svc.get("Status", ""),
                    "service_url": svc.get("ServiceUrl", ""),
                    "created_at": _dt(svc.get("CreatedAt")),
                })
    except (ClientError, NoCredentialsError) as e:
        print(f"AppRunner scan error in {region} ({creds.account_id}): {e}")
    return resources


def scan_elastic_beanstalk(creds: AccountCredentials, region: str) -> list:
    resources = []
    try:
        eb = creds.get_client("elasticbeanstalk", region)
        for page in eb.get_paginator("describe_environments").paginate():
            for env in page.get("Environments", []):
                resources.append({
                    **_b("ElasticBeanstalkEnvironment", env["EnvironmentId"], env["EnvironmentName"], region, creds),
                    "application_name": env.get("ApplicationName", ""),
                    "solution_stack": env.get("SolutionStackName", ""),
                    "tier": env.get("Tier", {}).get("Name", ""),
                    "health": env.get("Health", ""),
                    "status": env.get("Status", ""),
                    "cname": env.get("CNAME", ""),
                })
    except (ClientError, NoCredentialsError) as e:
        print(f"ElasticBeanstalk scan error in {region} ({creds.account_id}): {e}")
    return resources


def scan_batch(creds: AccountCredentials, region: str) -> list:
    resources = []
    try:
        batch = creds.get_client("batch", region)
        for page in batch.get_paginator("describe_compute_environments").paginate():
            for ce in page.get("computeEnvironments", []):
                resources.append({
                    **_b("BatchComputeEnvironment", ce["computeEnvironmentArn"], ce["computeEnvironmentName"], region, creds),
                    "type": ce.get("type", ""),
                    "state": ce.get("state", ""),
                    "status": ce.get("status", ""),
                    "instance_type": ce.get("computeResources", {}).get("instanceType", []),
                    "min_vcpus": ce.get("computeResources", {}).get("minvCpus", 0),
                    "max_vcpus": ce.get("computeResources", {}).get("maxvCpus", 0),
                })
    except (ClientError, NoCredentialsError) as e:
        print(f"Batch scan error in {region} ({creds.account_id}): {e}")
    return resources


def scan_lightsail(creds: AccountCredentials, region: str) -> list:
    resources = []
    try:
        ls = creds.get_client("lightsail", region)
        for page in ls.get_paginator("get_instances").paginate():
            for inst in page.get("instances", []):
                resources.append({
                    **_b("LightsailInstance", inst["arn"], inst["name"], region, creds),
                    "bundle_id": inst.get("bundleId", ""),
                    "blueprint_id": inst.get("blueprintId", ""),
                    "state": inst.get("state", {}).get("name", ""),
                    "public_ip": inst.get("publicIpAddress", ""),
                    "created_at": _dt(inst.get("createdAt")),
                })
    except (ClientError, NoCredentialsError) as e:
        print(f"Lightsail scan error in {region} ({creds.account_id}): {e}")
    return resources


# ════════════════════════════════════════════════════════════════════════════════
#  STORAGE
# ════════════════════════════════════════════════════════════════════════════════

def scan_s3(creds: AccountCredentials, target_regions: list) -> list:
    resources = []
    try:
        s3 = creds.get_client("s3", "us-east-1")
        for bucket in s3.list_buckets().get("Buckets", []):
            name = bucket["Name"]
            try:
                loc = s3.get_bucket_location(Bucket=name)
                bucket_region = loc.get("LocationConstraint") or "us-east-1"
            except ClientError:
                bucket_region = "unknown"
            if target_regions and bucket_region not in target_regions and bucket_region != "unknown":
                continue
            has_lifecycle = False
            try:
                s3.get_bucket_lifecycle_configuration(Bucket=name)
                has_lifecycle = True
            except ClientError:
                pass
            versioning = "Disabled"
            try:
                ver = s3.get_bucket_versioning(Bucket=name)
                versioning = ver.get("Status", "Disabled")
            except ClientError:
                pass
            resources.append({
                **_b("S3Bucket", name, name, bucket_region, creds),
                "creation_date": _dt(bucket.get("CreationDate")),
                "has_lifecycle_policy": has_lifecycle,
                "versioning": versioning,
            })
    except (ClientError, NoCredentialsError) as e:
        print(f"S3 scan error ({creds.account_id}): {e}")
    return resources


def scan_efs(creds: AccountCredentials, region: str) -> list:
    resources = []
    try:
        efs = creds.get_client("efs", region)
        for page in efs.get_paginator("describe_file_systems").paginate():
            for fs in page.get("FileSystems", []):
                size_bytes = fs.get("SizeInBytes", {}).get("Value", 0)
                resources.append({
                    **_b("EFSFileSystem", fs["FileSystemId"], fs.get("Name") or fs["FileSystemId"], region, creds),
                    "lifecycle_state": fs.get("LifeCycleState", ""),
                    "performance_mode": fs.get("PerformanceMode", ""),
                    "throughput_mode": fs.get("ThroughputMode", ""),
                    "size_gb": round(size_bytes / 1_073_741_824, 2),
                    "number_of_mount_targets": fs.get("NumberOfMountTargets", 0),
                    "encrypted": fs.get("Encrypted", False),
                    "tags": {t["Key"]: t["Value"] for t in fs.get("Tags", [])},
                })
    except (ClientError, NoCredentialsError) as e:
        print(f"EFS scan error in {region} ({creds.account_id}): {e}")
    return resources


def scan_fsx(creds: AccountCredentials, region: str) -> list:
    resources = []
    try:
        fsx = creds.get_client("fsx", region)
        for page in fsx.get_paginator("describe_file_systems").paginate():
            for fs in page.get("FileSystems", []):
                resources.append({
                    **_b("FSxFileSystem", fs["FileSystemId"], _tag(fs, "Name") or fs["FileSystemId"], region, creds),
                    "file_system_type": fs.get("FileSystemType", ""),
                    "storage_capacity_gb": fs.get("StorageCapacity", 0),
                    "storage_type": fs.get("StorageType", ""),
                    "lifecycle": fs.get("Lifecycle", ""),
                    "dns_name": fs.get("DNSName", ""),
                    "tags": _tags(fs),
                })
    except (ClientError, NoCredentialsError) as e:
        print(f"FSx scan error in {region} ({creds.account_id}): {e}")
    return resources


def scan_backup(creds: AccountCredentials, region: str) -> list:
    resources = []
    try:
        bkp = creds.get_client("backup", region)
        resp = bkp.list_backup_vaults()
        for vault in resp.get("BackupVaultList", []):
            recovery_count = 0
            try:
                for page in bkp.get_paginator("list_recovery_points_by_backup_vault").paginate(BackupVaultName=vault["BackupVaultName"]):
                    recovery_count += len(page.get("RecoveryPoints", []))
            except ClientError:
                pass
            resources.append({
                **_b("BackupVault", vault["BackupVaultArn"], vault["BackupVaultName"], region, creds),
                "number_of_recovery_points": vault.get("NumberOfRecoveryPoints", recovery_count),
                "creation_date": _dt(vault.get("CreationDate")),
            })
    except (ClientError, NoCredentialsError) as e:
        print(f"Backup scan error in {region} ({creds.account_id}): {e}")
    return resources


# ════════════════════════════════════════════════════════════════════════════════
#  DATABASES
# ════════════════════════════════════════════════════════════════════════════════

def scan_rds(creds: AccountCredentials, region: str) -> list:
    resources = []
    try:
        rds = creds.get_client("rds", region)
        for page in rds.get_paginator("describe_db_instances").paginate():
            for db in page.get("DBInstances", []):
                resources.append({
                    **_b("RDSInstance", db["DBInstanceIdentifier"], db["DBInstanceIdentifier"], region, creds),
                    "instance_class": db.get("DBInstanceClass", ""),
                    "engine": db.get("Engine", ""),
                    "engine_version": db.get("EngineVersion", ""),
                    "status": db.get("DBInstanceStatus", ""),
                    "multi_az": db.get("MultiAZ", False),
                    "allocated_storage": db.get("AllocatedStorage", 0),
                    "storage_type": db.get("StorageType", ""),
                    "backup_retention": db.get("BackupRetentionPeriod", 0),
                    "publicly_accessible": db.get("PubliclyAccessible", False),
                    "tags": {t["Key"]: t["Value"] for t in db.get("TagList", [])},
                })
        for page in rds.get_paginator("describe_db_snapshots").paginate(SnapshotType="manual"):
            for snap in page.get("DBSnapshots", []):
                resources.append({
                    **_b("RDSSnapshot", snap["DBSnapshotIdentifier"], snap["DBSnapshotIdentifier"], region, creds),
                    "db_instance": snap.get("DBInstanceIdentifier", ""),
                    "allocated_storage": snap.get("AllocatedStorage", 0),
                    "age_days": _age(snap.get("SnapshotCreateTime")),
                    "status": snap.get("Status", ""),
                })
        for page in rds.get_paginator("describe_db_proxies").paginate():
            for proxy in page.get("DBProxies", []):
                resources.append({
                    **_b("RDSProxy", proxy["DBProxyArn"], proxy["DBProxyName"], region, creds),
                    "endpoint": proxy.get("Endpoint", ""),
                    "engine_family": proxy.get("EngineFamily", ""),
                    "status": proxy.get("Status", ""),
                    "idle_client_timeout": proxy.get("IdleClientTimeout", 0),
                    "require_tls": proxy.get("RequireTLS", False),
                })
    except (ClientError, NoCredentialsError) as e:
        print(f"RDS scan error in {region} ({creds.account_id}): {e}")
    return resources


def scan_elasticache(creds: AccountCredentials, region: str) -> list:
    resources = []
    try:
        ec = creds.get_client("elasticache", region)
        for page in ec.get_paginator("describe_cache_clusters").paginate(ShowCacheNodeInfo=True):
            for cluster in page.get("CacheClusters", []):
                resources.append({
                    **_b("ElastiCacheCluster", cluster["CacheClusterId"], cluster["CacheClusterId"], region, creds),
                    "engine": cluster.get("Engine", ""),
                    "engine_version": cluster.get("EngineVersion", ""),
                    "cache_node_type": cluster.get("CacheNodeType", ""),
                    "num_cache_nodes": cluster.get("NumCacheNodes", 0),
                    "status": cluster.get("CacheClusterStatus", ""),
                    "replication_group_id": cluster.get("ReplicationGroupId", ""),
                    "auto_minor_version_upgrade": cluster.get("AutoMinorVersionUpgrade", False),
                })
    except (ClientError, NoCredentialsError) as e:
        print(f"ElastiCache scan error in {region} ({creds.account_id}): {e}")
    return resources


def scan_dynamodb(creds: AccountCredentials, region: str) -> list:
    resources = []
    try:
        ddb = creds.get_client("dynamodb", region)
        for page in ddb.get_paginator("list_tables").paginate():
            for name in page.get("TableNames", []):
                try:
                    tbl = ddb.describe_table(TableName=name)["Table"]
                    billing = tbl.get("BillingModeSummary", {}).get("BillingMode", "PROVISIONED")
                    tp = tbl.get("ProvisionedThroughput", {})
                    resources.append({
                        **_b("DynamoDBTable", tbl["TableArn"], tbl["TableName"], region, creds),
                        "status": tbl.get("TableStatus", ""),
                        "billing_mode": billing,
                        "read_capacity": tp.get("ReadCapacityUnits", 0),
                        "write_capacity": tp.get("WriteCapacityUnits", 0),
                        "item_count": tbl.get("ItemCount", 0),
                        "size_bytes": tbl.get("TableSizeBytes", 0),
                        "gsi_count": len(tbl.get("GlobalSecondaryIndexes", [])),
                        "ttl_enabled": False,
                    })
                except ClientError:
                    pass
    except (ClientError, NoCredentialsError) as e:
        print(f"DynamoDB scan error in {region} ({creds.account_id}): {e}")
    return resources


def scan_dax(creds: AccountCredentials, region: str) -> list:
    resources = []
    try:
        dax = creds.get_client("dax", region)
        for page in dax.get_paginator("describe_clusters").paginate():
            for cluster in page.get("Clusters", []):
                resources.append({
                    **_b("DAXCluster", cluster["ClusterArn"], cluster["ClusterName"], region, creds),
                    "node_type": cluster.get("NodeType", ""),
                    "total_nodes": cluster.get("TotalNodes", 0),
                    "active_nodes": cluster.get("ActiveNodes", 0),
                    "status": cluster.get("Status", ""),
                })
    except (ClientError, NoCredentialsError) as e:
        print(f"DAX scan error in {region} ({creds.account_id}): {e}")
    return resources


def scan_redshift(creds: AccountCredentials, region: str) -> list:
    resources = []
    try:
        rs = creds.get_client("redshift", region)
        for page in rs.get_paginator("describe_clusters").paginate():
            for cluster in page.get("Clusters", []):
                resources.append({
                    **_b("RedshiftCluster", cluster["ClusterIdentifier"], cluster["ClusterIdentifier"], region, creds),
                    "node_type": cluster.get("NodeType", ""),
                    "number_of_nodes": cluster.get("NumberOfNodes", 1),
                    "cluster_status": cluster.get("ClusterStatus", ""),
                    "cluster_availability_status": cluster.get("ClusterAvailabilityStatus", ""),
                    "db_name": cluster.get("DBName", ""),
                    "automated_snapshot_retention": cluster.get("AutomatedSnapshotRetentionPeriod", 0),
                    "encrypted": cluster.get("Encrypted", False),
                    "publicly_accessible": cluster.get("PubliclyAccessible", False),
                })
    except (ClientError, NoCredentialsError) as e:
        print(f"Redshift scan error in {region} ({creds.account_id}): {e}")
    return resources


def scan_documentdb(creds: AccountCredentials, region: str) -> list:
    resources = []
    try:
        docdb = creds.get_client("docdb", region)
        for page in docdb.get_paginator("describe_db_clusters").paginate(
            Filters=[{"Name": "engine", "Values": ["docdb"]}]
        ):
            for cluster in page.get("DBClusters", []):
                resources.append({
                    **_b("DocumentDBCluster", cluster["DBClusterArn"], cluster["DBClusterIdentifier"], region, creds),
                    "status": cluster.get("Status", ""),
                    "engine": cluster.get("Engine", ""),
                    "engine_version": cluster.get("EngineVersion", ""),
                    "instance_count": len(cluster.get("DBClusterMembers", [])),
                    "multi_az": cluster.get("MultiAZ", False),
                    "backup_retention": cluster.get("BackupRetentionPeriod", 0),
                })
    except (ClientError, NoCredentialsError) as e:
        print(f"DocumentDB scan error in {region} ({creds.account_id}): {e}")
    return resources


def scan_neptune(creds: AccountCredentials, region: str) -> list:
    resources = []
    try:
        nep = creds.get_client("neptune", region)
        for page in nep.get_paginator("describe_db_clusters").paginate(
            Filters=[{"Name": "engine", "Values": ["neptune"]}]
        ):
            for cluster in page.get("DBClusters", []):
                resources.append({
                    **_b("NeptuneCluster", cluster["DBClusterArn"], cluster["DBClusterIdentifier"], region, creds),
                    "status": cluster.get("Status", ""),
                    "engine_version": cluster.get("EngineVersion", ""),
                    "instance_count": len(cluster.get("DBClusterMembers", [])),
                    "multi_az": cluster.get("MultiAZ", False),
                    "backup_retention": cluster.get("BackupRetentionPeriod", 0),
                    "iam_auth_enabled": cluster.get("IAMDatabaseAuthenticationEnabled", False),
                })
    except (ClientError, NoCredentialsError) as e:
        print(f"Neptune scan error in {region} ({creds.account_id}): {e}")
    return resources


def scan_timestream(creds: AccountCredentials, region: str) -> list:
    resources = []
    try:
        ts = creds.get_client("timestream-write", region)
        resp = ts.list_databases()
        for db in resp.get("Databases", []):
            table_count = 0
            try:
                table_count = len(ts.list_tables(DatabaseName=db["DatabaseName"]).get("Tables", []))
            except ClientError:
                pass
            resources.append({
                **_b("TimestreamDatabase", db["Arn"], db["DatabaseName"], region, creds),
                "table_count": table_count,
                "kms_key_id": db.get("KmsKeyId", ""),
                "creation_time": _dt(db.get("CreationTime")),
            })
    except (ClientError, NoCredentialsError) as e:
        print(f"Timestream scan error in {region} ({creds.account_id}): {e}")
    return resources


def scan_qldb(creds: AccountCredentials, region: str) -> list:
    resources = []
    try:
        qldb = creds.get_client("qldb", region)
        resp = qldb.list_ledgers()
        for ledger in resp.get("Ledgers", []):
            resources.append({
                **_b("QLDBLedger", ledger["Name"], ledger["Name"], region, creds),
                "state": ledger.get("State", ""),
                "creation_date_time": _dt(ledger.get("CreationDateTime")),
            })
    except (ClientError, NoCredentialsError) as e:
        print(f"QLDB scan error in {region} ({creds.account_id}): {e}")
    return resources


def scan_keyspaces(creds: AccountCredentials, region: str) -> list:
    resources = []
    try:
        ks = creds.get_client("keyspaces", region)
        resp = ks.list_keyspaces()
        for keyspace in resp.get("keyspaces", []):
            resources.append({
                **_b("KeyspacesKeyspace", keyspace["resourceArn"], keyspace["keyspaceName"], region, creds),
                "replication_strategy": keyspace.get("replicationStrategy", ""),
            })
    except (ClientError, NoCredentialsError) as e:
        print(f"Keyspaces scan error in {region} ({creds.account_id}): {e}")
    return resources


def scan_memorydb(creds: AccountCredentials, region: str) -> list:
    resources = []
    try:
        mdb = creds.get_client("memorydb", region)
        resp = mdb.describe_clusters()
        for cluster in resp.get("Clusters", []):
            resources.append({
                **_b("MemoryDBCluster", cluster["ARN"], cluster["Name"], region, creds),
                "node_type": cluster.get("NodeType", ""),
                "num_shards": cluster.get("NumberOfShards", 0),
                "status": cluster.get("Status", ""),
                "engine_version": cluster.get("EngineVersion", ""),
                "tls_enabled": cluster.get("TLSEnabled", False),
            })
    except (ClientError, NoCredentialsError) as e:
        print(f"MemoryDB scan error in {region} ({creds.account_id}): {e}")
    return resources


def scan_dms(creds: AccountCredentials, region: str) -> list:
    resources = []
    try:
        dms = creds.get_client("dms", region)
        for page in dms.get_paginator("describe_replication_instances").paginate():
            for ri in page.get("ReplicationInstances", []):
                resources.append({
                    **_b("DMSReplicationInstance", ri["ReplicationInstanceArn"], ri["ReplicationInstanceIdentifier"], region, creds),
                    "instance_class": ri.get("ReplicationInstanceClass", ""),
                    "allocated_storage": ri.get("AllocatedStorage", 0),
                    "status": ri.get("ReplicationInstanceStatus", ""),
                    "multi_az": ri.get("MultiAZ", False),
                    "engine_version": ri.get("EngineVersion", ""),
                    "publicly_accessible": ri.get("PubliclyAccessible", False),
                })
    except (ClientError, NoCredentialsError) as e:
        print(f"DMS scan error in {region} ({creds.account_id}): {e}")
    return resources


# ════════════════════════════════════════════════════════════════════════════════
#  NETWORKING
# ════════════════════════════════════════════════════════════════════════════════

def scan_cloudfront(creds: AccountCredentials, target_regions: list) -> list:
    resources = []
    try:
        cf = creds.get_client("cloudfront", "us-east-1")
        for page in cf.get_paginator("list_distributions").paginate():
            for dist in page.get("DistributionList", {}).get("Items", []):
                resources.append({
                    **_b("CloudFrontDistribution", dist["Id"], dist.get("Comment") or dist["Id"], "global", creds),
                    "domain_name": dist.get("DomainName", ""),
                    "enabled": dist.get("Enabled", False),
                    "status": dist.get("Status", ""),
                    "price_class": dist.get("PriceClass", ""),
                    "http_version": dist.get("HttpVersion", ""),
                    "is_ipv6_enabled": dist.get("IsIPV6Enabled", False),
                })
    except (ClientError, NoCredentialsError) as e:
        print(f"CloudFront scan error ({creds.account_id}): {e}")
    return resources


def scan_apigateway(creds: AccountCredentials, region: str) -> list:
    resources = []
    try:
        # REST APIs
        apigw = creds.get_client("apigateway", region)
        resp = apigw.get_rest_apis()
        for api in resp.get("items", []):
            resources.append({
                **_b("APIGatewayREST", api["id"], api["name"], region, creds),
                "description": api.get("description", ""),
                "created_date": _dt(api.get("createdDate")),
                "endpoint_type": api.get("endpointConfiguration", {}).get("types", []),
                "disable_execute_api_endpoint": api.get("disableExecuteApiEndpoint", False),
            })
    except (ClientError, NoCredentialsError) as e:
        print(f"APIGateway REST scan error in {region} ({creds.account_id}): {e}")
    try:
        # HTTP / WebSocket APIs (v2)
        apigw2 = creds.get_client("apigatewayv2", region)
        resp = apigw2.get_apis()
        for api in resp.get("Items", []):
            resources.append({
                **_b("APIGatewayHTTP", api["ApiId"], api["Name"], region, creds),
                "protocol_type": api.get("ProtocolType", ""),
                "created_date": _dt(api.get("CreatedDate")),
                "api_endpoint": api.get("ApiEndpoint", ""),
                "disable_execute_api_endpoint": api.get("DisableExecuteApiEndpoint", False),
            })
    except (ClientError, NoCredentialsError) as e:
        print(f"APIGateway HTTP scan error in {region} ({creds.account_id}): {e}")
    return resources


def scan_transit_gateway(creds: AccountCredentials, region: str) -> list:
    resources = []
    try:
        ec2 = creds.get_client("ec2", region)
        for page in ec2.get_paginator("describe_transit_gateways").paginate():
            for tgw in page.get("TransitGateways", []):
                resources.append({
                    **_b("TransitGateway", tgw["TransitGatewayId"], _tag(tgw, "Name") or tgw["TransitGatewayId"], region, creds),
                    "state": tgw.get("State", ""),
                    "owner_id": tgw.get("OwnerId", ""),
                    "creation_time": _dt(tgw.get("CreationTime")),
                    "tags": _tags(tgw),
                })
        for page in ec2.get_paginator("describe_transit_gateway_attachments").paginate():
            for att in page.get("TransitGatewayAttachments", []):
                resources.append({
                    **_b("TransitGatewayAttachment", att["TransitGatewayAttachmentId"],
                         _tag(att, "Name") or att["TransitGatewayAttachmentId"], region, creds),
                    "transit_gateway_id": att.get("TransitGatewayId", ""),
                    "resource_type": att.get("ResourceType", ""),
                    "state": att.get("State", ""),
                    "tags": _tags(att),
                })
    except (ClientError, NoCredentialsError) as e:
        print(f"TransitGateway scan error in {region} ({creds.account_id}): {e}")
    return resources


def scan_vpc_endpoints(creds: AccountCredentials, region: str) -> list:
    resources = []
    try:
        ec2 = creds.get_client("ec2", region)
        for page in ec2.get_paginator("describe_vpc_endpoints").paginate():
            for ep in page.get("VpcEndpoints", []):
                resources.append({
                    **_b("VPCEndpoint", ep["VpcEndpointId"], _tag(ep, "Name") or ep["VpcEndpointId"], region, creds),
                    "vpc_endpoint_type": ep.get("VpcEndpointType", ""),
                    "service_name": ep.get("ServiceName", ""),
                    "state": ep.get("State", ""),
                    "vpc_id": ep.get("VpcId", ""),
                    "tags": _tags(ep),
                })
    except (ClientError, NoCredentialsError) as e:
        print(f"VPC Endpoints scan error in {region} ({creds.account_id}): {e}")
    return resources


def scan_global_accelerator(creds: AccountCredentials, target_regions: list) -> list:
    resources = []
    try:
        ga = creds.get_client("globalaccelerator", "us-west-2")
        resp = ga.list_accelerators()
        for acc in resp.get("Accelerators", []):
            resources.append({
                **_b("GlobalAccelerator", acc["AcceleratorArn"], acc["Name"], "global", creds),
                "status": acc.get("Status", ""),
                "enabled": acc.get("Enabled", False),
                "ip_address_type": acc.get("IpAddressType", ""),
                "created_time": _dt(acc.get("CreatedTime")),
            })
    except (ClientError, NoCredentialsError) as e:
        print(f"GlobalAccelerator scan error ({creds.account_id}): {e}")
    return resources


def scan_direct_connect(creds: AccountCredentials, region: str) -> list:
    resources = []
    try:
        dc = creds.get_client("directconnect", region)
        for conn in dc.describe_connections().get("connections", []):
            resources.append({
                **_b("DirectConnectConnection", conn["connectionId"], conn["connectionName"], region, creds),
                "bandwidth": conn.get("bandwidth", ""),
                "connection_state": conn.get("connectionState", ""),
                "location": conn.get("location", ""),
                "partner_name": conn.get("partnerName", ""),
            })
    except (ClientError, NoCredentialsError) as e:
        print(f"DirectConnect scan error in {region} ({creds.account_id}): {e}")
    return resources


def scan_network_firewall(creds: AccountCredentials, region: str) -> list:
    resources = []
    try:
        nfw = creds.get_client("network-firewall", region)
        resp = nfw.list_firewalls()
        for fw in resp.get("Firewalls", []):
            resources.append({
                **_b("NetworkFirewall", fw["FirewallArn"], fw["FirewallName"], region, creds),
                "vpc_id": fw.get("VpcId", ""),
            })
    except (ClientError, NoCredentialsError) as e:
        print(f"NetworkFirewall scan error in {region} ({creds.account_id}): {e}")
    return resources


def scan_route53(creds: AccountCredentials, target_regions: list) -> list:
    resources = []
    try:
        r53 = creds.get_client("route53", "us-east-1")
        resp = r53.list_hosted_zones()
        for zone in resp.get("HostedZones", []):
            resources.append({
                **_b("Route53HostedZone", zone["Id"], zone["Name"], "global", creds),
                "record_count": zone.get("ResourceRecordSetCount", 0),
                "private_zone": zone.get("Config", {}).get("PrivateZone", False),
                "comment": zone.get("Config", {}).get("Comment", ""),
            })
    except (ClientError, NoCredentialsError) as e:
        print(f"Route53 scan error ({creds.account_id}): {e}")
    return resources


def scan_transfer_family(creds: AccountCredentials, region: str) -> list:
    resources = []
    try:
        tf = creds.get_client("transfer", region)
        resp = tf.list_servers()
        for srv in resp.get("Servers", []):
            resources.append({
                **_b("TransferServer", srv["ServerId"], srv.get("IdentityProviderType", srv["ServerId"]), region, creds),
                "state": srv.get("State", ""),
                "endpoint_type": srv.get("EndpointType", ""),
                "protocols": srv.get("Protocols", []),
                "user_count": srv.get("UserCount", 0),
            })
    except (ClientError, NoCredentialsError) as e:
        print(f"TransferFamily scan error in {region} ({creds.account_id}): {e}")
    return resources


def scan_waf(creds: AccountCredentials, region: str) -> list:
    resources = []
    for scope in ("REGIONAL",):
        try:
            waf = creds.get_client("wafv2", region)
            resp = waf.list_web_acls(Scope=scope)
            for acl in resp.get("WebACLs", []):
                resources.append({
                    **_b("WAFWebACL", acl["ARN"], acl["Name"], region, creds),
                    "scope": scope,
                    "managed_by_firewall_manager": acl.get("ManagedByFirewallManager", False),
                })
        except (ClientError, NoCredentialsError) as e:
            print(f"WAF scan error in {region}/{scope} ({creds.account_id}): {e}")
    return resources


# ════════════════════════════════════════════════════════════════════════════════
#  SERVERLESS & FUNCTIONS
# ════════════════════════════════════════════════════════════════════════════════

def scan_lambda(creds: AccountCredentials, region: str) -> list:
    resources = []
    try:
        lmb = creds.get_client("lambda", region)
        for page in lmb.get_paginator("list_functions").paginate():
            for func in page.get("Functions", []):
                resources.append({
                    **_b("LambdaFunction", func["FunctionArn"], func["FunctionName"], region, creds),
                    "runtime": func.get("Runtime", ""),
                    "memory_size": func.get("MemorySize", 128),
                    "timeout": func.get("Timeout", 3),
                    "code_size": func.get("CodeSize", 0),
                    "last_modified": func.get("LastModified", ""),
                    "description": func.get("Description", ""),
                })
    except (ClientError, NoCredentialsError) as e:
        print(f"Lambda scan error in {region} ({creds.account_id}): {e}")
    return resources


# ════════════════════════════════════════════════════════════════════════════════
#  ANALYTICS & STREAMING
# ════════════════════════════════════════════════════════════════════════════════

def scan_kinesis(creds: AccountCredentials, region: str) -> list:
    resources = []
    try:
        # Kinesis Data Streams
        kin = creds.get_client("kinesis", region)
        resp = kin.list_streams(Limit=100)
        for name in resp.get("StreamNames", []):
            try:
                stream = kin.describe_stream_summary(StreamName=name)["StreamDescriptionSummary"]
                resources.append({
                    **_b("KinesisStream", stream["StreamARN"], stream["StreamName"], region, creds),
                    "shard_count": stream.get("OpenShardCount", 0),
                    "retention_period_hours": stream.get("RetentionPeriodHours", 24),
                    "status": stream.get("StreamStatus", ""),
                    "stream_mode": stream.get("StreamModeDetails", {}).get("StreamMode", "PROVISIONED"),
                })
            except ClientError:
                pass
    except (ClientError, NoCredentialsError) as e:
        print(f"Kinesis Streams scan error in {region} ({creds.account_id}): {e}")
    try:
        # Kinesis Firehose
        fh = creds.get_client("firehose", region)
        resp = fh.list_delivery_streams()
        for name in resp.get("DeliveryStreamNames", []):
            try:
                stream = fh.describe_delivery_stream(DeliveryStreamName=name)["DeliveryStreamDescription"]
                resources.append({
                    **_b("KinesisFirehose", stream["DeliveryStreamARN"], stream["DeliveryStreamName"], region, creds),
                    "status": stream.get("DeliveryStreamStatus", ""),
                    "delivery_stream_type": stream.get("DeliveryStreamType", ""),
                    "created_at": _dt(stream.get("CreateTimestamp")),
                })
            except ClientError:
                pass
    except (ClientError, NoCredentialsError) as e:
        print(f"Kinesis Firehose scan error in {region} ({creds.account_id}): {e}")
    try:
        # Kinesis Video Streams
        kvs = creds.get_client("kinesisvideo", region)
        resp = kvs.list_streams()
        for stream in resp.get("StreamInfoList", []):
            resources.append({
                **_b("KinesisVideoStream", stream["StreamARN"], stream["StreamName"], region, creds),
                "status": stream.get("Status", ""),
                "data_retention_hours": stream.get("DataRetentionInHours", 0),
                "media_type": stream.get("MediaType", ""),
                "creation_time": _dt(stream.get("CreationTime")),
            })
    except (ClientError, NoCredentialsError) as e:
        print(f"Kinesis Video scan error in {region} ({creds.account_id}): {e}")
    return resources


def scan_msk(creds: AccountCredentials, region: str) -> list:
    resources = []
    try:
        msk = creds.get_client("kafka", region)
        for page in msk.get_paginator("list_clusters").paginate():
            for cluster in page.get("ClusterInfoList", []):
                broker_info = cluster.get("BrokerNodeGroupInfo", {})
                resources.append({
                    **_b("MSKCluster", cluster["ClusterArn"], cluster["ClusterName"], region, creds),
                    "cluster_state": cluster.get("State", ""),
                    "kafka_version": cluster.get("CurrentBrokerSoftwareInfo", {}).get("KafkaVersion", ""),
                    "number_of_broker_nodes": cluster.get("NumberOfBrokerNodes", 0),
                    "broker_instance_type": broker_info.get("InstanceType", ""),
                    "broker_storage_gb": broker_info.get("StorageInfo", {}).get("EbsStorageInfo", {}).get("VolumeSize", 0),
                })
    except (ClientError, NoCredentialsError) as e:
        print(f"MSK scan error in {region} ({creds.account_id}): {e}")
    return resources


def scan_emr(creds: AccountCredentials, region: str) -> list:
    resources = []
    try:
        emr = creds.get_client("emr", region)
        for page in emr.get_paginator("list_clusters").paginate(
            ClusterStates=["STARTING", "BOOTSTRAPPING", "RUNNING", "WAITING", "TERMINATING"]
        ):
            for cluster in page.get("Clusters", []):
                resources.append({
                    **_b("EMRCluster", cluster["Id"], cluster["Name"], region, creds),
                    "status": cluster.get("Status", {}).get("State", ""),
                    "normalized_instance_hours": cluster.get("NormalizedInstanceHours", 0),
                })
    except (ClientError, NoCredentialsError) as e:
        print(f"EMR scan error in {region} ({creds.account_id}): {e}")
    return resources


def scan_athena(creds: AccountCredentials, region: str) -> list:
    resources = []
    try:
        ath = creds.get_client("athena", region)
        for page in ath.get_paginator("list_work_groups").paginate():
            for wg in page.get("WorkGroups", []):
                if wg["Name"] == "primary":
                    continue
                try:
                    detail = ath.get_work_group(WorkGroup=wg["Name"])["WorkGroup"]
                    config = detail.get("Configuration", {})
                    resources.append({
                        **_b("AthenaWorkgroup", wg["Name"], wg["Name"], region, creds),
                        "state": wg.get("State", ""),
                        "bytes_scanned_cutoff": config.get("BytesScannedCutoffPerQuery", 0),
                        "enforce_workgroup_config": config.get("EnforceWorkGroupConfiguration", True),
                        "publish_cloudwatch_metrics": config.get("PublishCloudWatchMetricsEnabled", False),
                    })
                except ClientError:
                    pass
    except (ClientError, NoCredentialsError) as e:
        print(f"Athena scan error in {region} ({creds.account_id}): {e}")
    return resources


def scan_glue(creds: AccountCredentials, region: str) -> list:
    resources = []
    try:
        glue = creds.get_client("glue", region)
        for page in glue.get_paginator("get_jobs").paginate():
            for job in page.get("Jobs", []):
                resources.append({
                    **_b("GlueJob", job["Name"], job["Name"], region, creds),
                    "worker_type": job.get("WorkerType", ""),
                    "number_of_workers": job.get("NumberOfWorkers", 0),
                    "max_dpus": job.get("MaxCapacity", 0),
                    "timeout": job.get("Timeout", 0),
                    "max_retries": job.get("MaxRetries", 0),
                    "glue_version": job.get("GlueVersion", ""),
                })
        for page in glue.get_paginator("get_crawlers").paginate():
            for crawler in page.get("Crawlers", []):
                resources.append({
                    **_b("GlueCrawler", crawler["Name"], crawler["Name"], region, creds),
                    "state": crawler.get("State", ""),
                    "database_name": crawler.get("DatabaseName", ""),
                    "schedule": crawler.get("Schedule", {}).get("ScheduleExpression", ""),
                    "last_crawl_status": crawler.get("LastCrawl", {}).get("Status", ""),
                })
    except (ClientError, NoCredentialsError) as e:
        print(f"Glue scan error in {region} ({creds.account_id}): {e}")
    return resources


def scan_opensearch(creds: AccountCredentials, region: str) -> list:
    resources = []
    try:
        oss = creds.get_client("opensearch", region)
        names = [d["DomainName"] for d in oss.list_domain_names().get("DomainNames", [])]
        if names:
            for i in range(0, len(names), 5):
                for domain in oss.describe_domains(DomainNames=names[i:i+5]).get("DomainStatusList", []):
                    cluster_config = domain.get("ClusterConfig", {})
                    resources.append({
                        **_b("OpenSearchDomain", domain["ARN"], domain["DomainName"], region, creds),
                        "engine_version": domain.get("EngineVersion", ""),
                        "instance_type": cluster_config.get("InstanceType", ""),
                        "instance_count": cluster_config.get("InstanceCount", 1),
                        "dedicated_master_enabled": cluster_config.get("DedicatedMasterEnabled", False),
                        "dedicated_master_type": cluster_config.get("DedicatedMasterType", ""),
                        "warm_enabled": cluster_config.get("WarmEnabled", False),
                        "processing": domain.get("Processing", False),
                    })
    except (ClientError, NoCredentialsError) as e:
        print(f"OpenSearch scan error in {region} ({creds.account_id}): {e}")
    return resources


def scan_quicksight(creds: AccountCredentials, target_regions: list) -> list:
    resources = []
    try:
        qs = creds.get_client("quicksight", "us-east-1")
        for page in qs.get_paginator("list_users").paginate(
            AwsAccountId=creds.account_id, Namespace="default"
        ):
            for user in page.get("UserList", []):
                resources.append({
                    **_b("QuickSightUser", user["Arn"], user["UserName"], "global", creds),
                    "email": user.get("Email", ""),
                    "role": user.get("Role", ""),
                    "active": user.get("Active", False),
                    "identity_type": user.get("IdentityType", ""),
                })
    except (ClientError, NoCredentialsError) as e:
        print(f"QuickSight scan error ({creds.account_id}): {e}")
    return resources


# ════════════════════════════════════════════════════════════════════════════════
#  AI / ML
# ════════════════════════════════════════════════════════════════════════════════

def scan_sagemaker(creds: AccountCredentials, region: str) -> list:
    resources = []
    try:
        sm = creds.get_client("sagemaker", region)
        for page in sm.get_paginator("list_notebook_instances").paginate():
            for nb in page.get("NotebookInstances", []):
                resources.append({
                    **_b("SageMakerNotebook", nb["NotebookInstanceArn"], nb["NotebookInstanceName"], region, creds),
                    "instance_type": nb.get("InstanceType", ""),
                    "status": nb.get("NotebookInstanceStatus", ""),
                    "creation_time": _dt(nb.get("CreationTime")),
                    "last_modified_time": _dt(nb.get("LastModifiedTime")),
                })
        for page in sm.get_paginator("list_endpoints").paginate():
            for ep in page.get("Endpoints", []):
                resources.append({
                    **_b("SageMakerEndpoint", ep["EndpointArn"], ep["EndpointName"], region, creds),
                    "status": ep.get("EndpointStatus", ""),
                    "creation_time": _dt(ep.get("CreationTime")),
                    "last_modified_time": _dt(ep.get("LastModifiedTime")),
                })
        for page in sm.get_paginator("list_training_jobs").paginate(StatusEquals="InProgress"):
            for job in page.get("TrainingJobSummaries", []):
                resources.append({
                    **_b("SageMakerTrainingJob", job["TrainingJobArn"], job["TrainingJobName"], region, creds),
                    "status": job.get("TrainingJobStatus", ""),
                    "creation_time": _dt(job.get("CreationTime")),
                })
    except (ClientError, NoCredentialsError) as e:
        print(f"SageMaker scan error in {region} ({creds.account_id}): {e}")
    return resources


def scan_bedrock(creds: AccountCredentials, region: str) -> list:
    resources = []
    try:
        bedrock = creds.get_client("bedrock", region)
        resp = bedrock.list_provisioned_model_throughputs()
        for model in resp.get("provisionedModelSummaries", []):
            resources.append({
                **_b("BedrockProvisionedModel", model["provisionedModelArn"], model["provisionedModelName"], region, creds),
                "model_arn": model.get("modelArn", ""),
                "status": model.get("status", ""),
                "model_units": model.get("desiredModelUnits", 0),
                "commitment_duration": model.get("commitmentDuration", ""),
                "creation_time": _dt(model.get("creationTime")),
            })
    except (ClientError, NoCredentialsError) as e:
        print(f"Bedrock scan error in {region} ({creds.account_id}): {e}")
    return resources


def scan_rekognition(creds: AccountCredentials, region: str) -> list:
    resources = []
    try:
        rek = creds.get_client("rekognition", region)
        resp = rek.describe_projects()
        for project in resp.get("ProjectDescriptions", []):
            resources.append({
                **_b("RekognitionProject", project["ProjectArn"], project["ProjectArn"].split("/")[-1], region, creds),
                "status": project.get("Status", ""),
                "creation_timestamp": _dt(project.get("CreationTimestamp")),
                "datasets": len(project.get("Datasets", [])),
            })
    except (ClientError, NoCredentialsError) as e:
        print(f"Rekognition scan error in {region} ({creds.account_id}): {e}")
    return resources


def scan_comprehend(creds: AccountCredentials, region: str) -> list:
    resources = []
    try:
        comp = creds.get_client("comprehend", region)
        resp = comp.list_endpoints()
        for ep in resp.get("EndpointPropertiesList", []):
            resources.append({
                **_b("ComprehendEndpoint", ep["EndpointArn"], ep["EndpointArn"].split("/")[-1], region, creds),
                "model_arn": ep.get("ModelArn", ""),
                "status": ep.get("Status", ""),
                "desired_inference_units": ep.get("DesiredInferenceUnits", 0),
                "current_inference_units": ep.get("CurrentInferenceUnits", 0),
                "creation_time": _dt(ep.get("CreationTime")),
            })
    except (ClientError, NoCredentialsError) as e:
        print(f"Comprehend scan error in {region} ({creds.account_id}): {e}")
    return resources


def scan_lex(creds: AccountCredentials, region: str) -> list:
    resources = []
    try:
        lex = creds.get_client("lexv2-models", region)
        resp = lex.list_bots()
        for bot in resp.get("botSummaries", []):
            resources.append({
                **_b("LexBot", bot["botId"], bot["botName"], region, creds),
                "status": bot.get("botStatus", ""),
                "idle_session_ttl_seconds": bot.get("idleSessionTTLInSeconds", 0),
                "description": bot.get("description", ""),
            })
    except (ClientError, NoCredentialsError) as e:
        print(f"Lex scan error in {region} ({creds.account_id}): {e}")
    return resources


# ════════════════════════════════════════════════════════════════════════════════
#  MESSAGING & INTEGRATION
# ════════════════════════════════════════════════════════════════════════════════

def scan_sqs(creds: AccountCredentials, region: str) -> list:
    resources = []
    try:
        sqs = creds.get_client("sqs", region)
        for page in sqs.get_paginator("list_queues").paginate():
            for url in page.get("QueueUrls", []):
                try:
                    attrs = sqs.get_queue_attributes(
                        QueueUrl=url,
                        AttributeNames=["QueueArn", "ApproximateNumberOfMessages",
                                         "ApproximateNumberOfMessagesNotVisible",
                                         "MessageRetentionPeriod", "VisibilityTimeout"]
                    )["Attributes"]
                    name = url.split("/")[-1]
                    resources.append({
                        **_b("SQSQueue", attrs.get("QueueArn", url), name, region, creds),
                        "queue_url": url,
                        "is_fifo": name.endswith(".fifo"),
                        "approximate_messages": int(attrs.get("ApproximateNumberOfMessages", 0)),
                        "messages_not_visible": int(attrs.get("ApproximateNumberOfMessagesNotVisible", 0)),
                        "retention_seconds": int(attrs.get("MessageRetentionPeriod", 345600)),
                        "visibility_timeout": int(attrs.get("VisibilityTimeout", 30)),
                    })
                except ClientError:
                    pass
    except (ClientError, NoCredentialsError) as e:
        print(f"SQS scan error in {region} ({creds.account_id}): {e}")
    return resources


def scan_sns(creds: AccountCredentials, region: str) -> list:
    resources = []
    try:
        sns = creds.get_client("sns", region)
        for page in sns.get_paginator("list_topics").paginate():
            for topic in page.get("Topics", []):
                arn = topic["TopicArn"]
                name = arn.split(":")[-1]
                try:
                    attrs = sns.get_topic_attributes(TopicArn=arn)["Attributes"]
                    resources.append({
                        **_b("SNSTopic", arn, name, region, creds),
                        "subscriptions_confirmed": int(attrs.get("SubscriptionsConfirmed", 0)),
                        "subscriptions_pending": int(attrs.get("SubscriptionsPending", 0)),
                        "subscriptions_deleted": int(attrs.get("SubscriptionsDeleted", 0)),
                        "fifo_topic": attrs.get("FifoTopic", "false") == "true",
                    })
                except ClientError:
                    pass
    except (ClientError, NoCredentialsError) as e:
        print(f"SNS scan error in {region} ({creds.account_id}): {e}")
    return resources


def scan_eventbridge(creds: AccountCredentials, region: str) -> list:
    resources = []
    try:
        eb = creds.get_client("events", region)
        for page in eb.get_paginator("list_event_buses").paginate():
            for bus in page.get("EventBuses", []):
                rule_count = 0
                try:
                    rule_resp = eb.list_rules(EventBusName=bus["Name"])
                    rule_count = len(rule_resp.get("Rules", []))
                except ClientError:
                    pass
                resources.append({
                    **_b("EventBridgeBus", bus["Arn"], bus["Name"], region, creds),
                    "rule_count": rule_count,
                })
    except (ClientError, NoCredentialsError) as e:
        print(f"EventBridge scan error in {region} ({creds.account_id}): {e}")
    return resources


def scan_step_functions(creds: AccountCredentials, region: str) -> list:
    resources = []
    try:
        sfn = creds.get_client("stepfunctions", region)
        for page in sfn.get_paginator("list_state_machines").paginate():
            for sm in page.get("stateMachines", []):
                resources.append({
                    **_b("StepFunctionsMachine", sm["stateMachineArn"], sm["name"], region, creds),
                    "type": sm.get("type", "STANDARD"),
                    "creation_date": _dt(sm.get("creationDate")),
                })
    except (ClientError, NoCredentialsError) as e:
        print(f"Step Functions scan error in {region} ({creds.account_id}): {e}")
    return resources


def scan_mq(creds: AccountCredentials, region: str) -> list:
    resources = []
    try:
        mq = creds.get_client("mq", region)
        resp = mq.list_brokers()
        for broker in resp.get("BrokerSummaries", []):
            resources.append({
                **_b("MQBroker", broker["BrokerArn"], broker["BrokerName"], region, creds),
                "broker_state": broker.get("BrokerState", ""),
                "deployment_mode": broker.get("DeploymentMode", ""),
                "host_instance_type": broker.get("HostInstanceType", ""),
                "engine_type": broker.get("EngineType", ""),
                "creation_time": _dt(broker.get("Created")),
            })
    except (ClientError, NoCredentialsError) as e:
        print(f"MQ scan error in {region} ({creds.account_id}): {e}")
    return resources


def scan_appsync(creds: AccountCredentials, region: str) -> list:
    resources = []
    try:
        appsync = creds.get_client("appsync", region)
        resp = appsync.list_graphql_apis()
        for api in resp.get("graphqlApis", []):
            resources.append({
                **_b("AppSyncAPI", api["apiId"], api["name"], region, creds),
                "authentication_type": api.get("authenticationType", ""),
                "api_type": api.get("apiType", "GRAPHQL"),
                "created_at": _dt(api.get("createdDate")),
            })
    except (ClientError, NoCredentialsError) as e:
        print(f"AppSync scan error in {region} ({creds.account_id}): {e}")
    return resources


# ════════════════════════════════════════════════════════════════════════════════
#  SECURITY
# ════════════════════════════════════════════════════════════════════════════════

def scan_kms(creds: AccountCredentials, region: str) -> list:
    resources = []
    try:
        kms = creds.get_client("kms", region)
        for page in kms.get_paginator("list_keys").paginate():
            for key in page.get("Keys", []):
                try:
                    meta = kms.describe_key(KeyId=key["KeyId"])["KeyMetadata"]
                    if meta.get("KeyManager") != "CUSTOMER":
                        continue
                    aliases = []
                    try:
                        aliases = [a["AliasName"] for a in kms.list_aliases(KeyId=key["KeyId"]).get("Aliases", [])]
                    except ClientError:
                        pass
                    resources.append({
                        **_b("KMSKey", meta["Arn"], aliases[0] if aliases else meta["KeyId"], region, creds),
                        "key_state": meta.get("KeyState", ""),
                        "key_usage": meta.get("KeyUsage", ""),
                        "key_spec": meta.get("KeySpec", ""),
                        "enabled": meta.get("Enabled", False),
                        "deletion_date": _dt(meta.get("DeletionDate")),
                        "creation_date": _dt(meta.get("CreationDate")),
                    })
                except ClientError:
                    pass
    except (ClientError, NoCredentialsError) as e:
        print(f"KMS scan error in {region} ({creds.account_id}): {e}")
    return resources


def scan_secretsmanager(creds: AccountCredentials, region: str) -> list:
    resources = []
    try:
        sm = creds.get_client("secretsmanager", region)
        for page in sm.get_paginator("list_secrets").paginate():
            for secret in page.get("SecretList", []):
                resources.append({
                    **_b("SecretsManagerSecret", secret["ARN"], secret["Name"], region, creds),
                    "description": secret.get("Description", ""),
                    "rotation_enabled": secret.get("RotationEnabled", False),
                    "last_accessed_date": _dt(secret.get("LastAccessedDate")),
                    "last_changed_date": _dt(secret.get("LastChangedDate")),
                    "age_days": _age(secret.get("CreatedDate")),
                    "tags": {t["Key"]: t["Value"] for t in secret.get("Tags", [])},
                })
    except (ClientError, NoCredentialsError) as e:
        print(f"Secrets Manager scan error in {region} ({creds.account_id}): {e}")
    return resources


def scan_ssm(creds: AccountCredentials, region: str) -> list:
    resources = []
    try:
        ssm = creds.get_client("ssm", region)
        for page in ssm.get_paginator("describe_parameters").paginate(
            ParameterFilters=[{"Key": "Tier", "Values": ["Advanced", "Intelligent-Tiering"]}]
        ):
            for param in page.get("Parameters", []):
                resources.append({
                    **_b("SSMParameter", param["Name"], param["Name"], region, creds),
                    "type": param.get("Type", ""),
                    "tier": param.get("Tier", "Standard"),
                    "last_modified_date": _dt(param.get("LastModifiedDate")),
                    "data_type": param.get("DataType", ""),
                })
    except (ClientError, NoCredentialsError) as e:
        print(f"SSM scan error in {region} ({creds.account_id}): {e}")
    return resources


def scan_acm_pca(creds: AccountCredentials, region: str) -> list:
    resources = []
    try:
        pca = creds.get_client("acm-pca", region)
        resp = pca.list_certificate_authorities()
        for ca in resp.get("CertificateAuthorities", []):
            resources.append({
                **_b("ACMPrivateCA", ca["Arn"], ca["Arn"].split("/")[-1], region, creds),
                "type": ca.get("Type", ""),
                "status": ca.get("Status", ""),
                "key_algorithm": ca.get("CertificateAuthorityConfiguration", {}).get("KeyAlgorithm", ""),
                "created_at": _dt(ca.get("CreatedAt")),
            })
    except (ClientError, NoCredentialsError) as e:
        print(f"ACM PCA scan error in {region} ({creds.account_id}): {e}")
    return resources


def scan_guardduty(creds: AccountCredentials, region: str) -> list:
    resources = []
    try:
        gd = creds.get_client("guardduty", region)
        for detector_id in gd.list_detectors().get("DetectorIds", []):
            try:
                det = gd.get_detector(DetectorId=detector_id)
                resources.append({
                    **_b("GuardDutyDetector", detector_id, detector_id, region, creds),
                    "status": det.get("Status", ""),
                    "finding_publishing_frequency": det.get("FindingPublishingFrequency", ""),
                    "created_at": _dt(det.get("CreatedAt")),
                    "service_role": det.get("ServiceRole", ""),
                })
            except ClientError:
                pass
    except (ClientError, NoCredentialsError) as e:
        print(f"GuardDuty scan error in {region} ({creds.account_id}): {e}")
    return resources


def scan_macie(creds: AccountCredentials, region: str) -> list:
    resources = []
    try:
        macie = creds.get_client("macie2", region)
        resp = macie.list_classification_jobs()
        for job in resp.get("items", []):
            resources.append({
                **_b("MacieClassificationJob", job["jobId"], job["name"], region, creds),
                "job_type": job.get("jobType", ""),
                "job_status": job.get("jobStatus", ""),
                "created_at": _dt(job.get("createdAt")),
            })
    except (ClientError, NoCredentialsError) as e:
        print(f"Macie scan error in {region} ({creds.account_id}): {e}")
    return resources


def scan_inspector(creds: AccountCredentials, region: str) -> list:
    resources = []
    try:
        insp = creds.get_client("inspector2", region)
        resp = insp.get_configuration()
        ec2_cfg = resp.get("ec2Configuration", {})
        ecr_cfg = resp.get("ecrConfiguration", {})
        lambda_cfg = resp.get("lambdaConfiguration", {})
        resources.append({
            **_b("InspectorConfiguration", creds.account_id, creds.account_id, region, creds),
            "ec2_scan_enabled": ec2_cfg.get("scanMode", "") != "DISABLED",
            "ecr_scan_enabled": ecr_cfg.get("rescanDuration", "") != "DISABLED",
            "lambda_scan_enabled": lambda_cfg.get("scanMode", "") != "DISABLED",
        })
    except (ClientError, NoCredentialsError) as e:
        print(f"Inspector scan error in {region} ({creds.account_id}): {e}")
    return resources


def scan_security_hub(creds: AccountCredentials, region: str) -> list:
    resources = []
    try:
        sh = creds.get_client("securityhub", region)
        hub = sh.describe_hub()
        resources.append({
            **_b("SecurityHub", hub["HubArn"], hub["HubArn"].split("/")[-1], region, creds),
            "auto_enable_controls": hub.get("AutoEnableControls", False),
            "subscribed_at": _dt(hub.get("SubscribedAt")),
        })
    except (ClientError, NoCredentialsError) as e:
        print(f"SecurityHub scan error in {region} ({creds.account_id}): {e}")
    return resources


def scan_firewall_manager(creds: AccountCredentials, target_regions: list) -> list:
    resources = []
    try:
        fms = creds.get_client("fms", "us-east-1")
        resp = fms.list_policies()
        for policy in resp.get("PolicyList", []):
            resources.append({
                **_b("FirewallManagerPolicy", policy["PolicyId"], policy["PolicyName"], "global", creds),
                "security_service_type": policy.get("SecurityServiceType", ""),
                "resource_type": policy.get("ResourceType", ""),
                "remediation_enabled": policy.get("RemediationEnabled", False),
            })
    except (ClientError, NoCredentialsError) as e:
        print(f"FirewallManager scan error ({creds.account_id}): {e}")
    return resources


def scan_shield(creds: AccountCredentials, target_regions: list) -> list:
    resources = []
    try:
        shield = creds.get_client("shield", "us-east-1")
        sub = shield.describe_subscription()["Subscription"]
        resources.append({
            **_b("ShieldSubscription", "shield-advanced", "Shield Advanced", "global", creds),
            "start_time": _dt(sub.get("StartTime")),
            "end_time": _dt(sub.get("EndTime")),
            "auto_renew": sub.get("AutoRenew", ""),
            "proactive_engagement_status": sub.get("ProactiveEngagementStatus", ""),
        })
    except ClientError as e:
        if "subscription does not exist" not in str(e).lower():
            print(f"Shield scan error ({creds.account_id}): {e}")
    except NoCredentialsError as e:
        print(f"Shield scan error ({creds.account_id}): {e}")
    return resources


def scan_license_manager(creds: AccountCredentials, region: str) -> list:
    resources = []
    try:
        lm = creds.get_client("license-manager", region)
        resp = lm.list_license_configurations()
        for config in resp.get("LicenseConfigurations", []):
            resources.append({
                **_b("LicenseManagerConfig", config["LicenseConfigurationArn"],
                     config["Name"], region, creds),
                "license_counting_type": config.get("LicenseCountingType", ""),
                "license_count": config.get("LicenseCount", 0),
                "consumed_licenses": config.get("ConsumedLicenses", 0),
                "status": config.get("Status", ""),
            })
    except (ClientError, NoCredentialsError) as e:
        print(f"LicenseManager scan error in {region} ({creds.account_id}): {e}")
    return resources


# ════════════════════════════════════════════════════════════════════════════════
#  DEVELOPER TOOLS
# ════════════════════════════════════════════════════════════════════════════════

def scan_codebuild(creds: AccountCredentials, region: str) -> list:
    resources = []
    try:
        cb = creds.get_client("codebuild", region)
        project_names = []
        for page in cb.get_paginator("list_projects").paginate():
            project_names.extend(page.get("projects", []))
        for i in range(0, len(project_names), 100):
            batch = project_names[i:i+100]
            for project in cb.batch_get_projects(names=batch).get("projects", []):
                env = project.get("environment", {})
                resources.append({
                    **_b("CodeBuildProject", project["arn"], project["name"], region, creds),
                    "environment_type": env.get("type", ""),
                    "compute_type": env.get("computeType", ""),
                    "build_timeout": project.get("timeoutInMinutes", 60),
                    "concurrent_build_limit": project.get("concurrentBuildLimit", 0),
                    "created": _dt(project.get("created")),
                })
    except (ClientError, NoCredentialsError) as e:
        print(f"CodeBuild scan error in {region} ({creds.account_id}): {e}")
    return resources


def scan_codepipeline(creds: AccountCredentials, region: str) -> list:
    resources = []
    try:
        cp = creds.get_client("codepipeline", region)
        resp = cp.list_pipelines()
        for pipeline in resp.get("pipelines", []):
            resources.append({
                **_b("CodePipeline", pipeline["name"], pipeline["name"], region, creds),
                "created": _dt(pipeline.get("created")),
                "updated": _dt(pipeline.get("updated")),
            })
    except (ClientError, NoCredentialsError) as e:
        print(f"CodePipeline scan error in {region} ({creds.account_id}): {e}")
    return resources


def scan_codeartifact(creds: AccountCredentials, region: str) -> list:
    resources = []
    try:
        ca = creds.get_client("codeartifact", region)
        for page in ca.get_paginator("list_repositories").paginate():
            for repo in page.get("repositories", []):
                resources.append({
                    **_b("CodeArtifactRepository", repo["arn"], repo["name"], region, creds),
                    "domain_name": repo.get("domainName", ""),
                    "domain_owner": repo.get("domainOwner", ""),
                    "description": repo.get("description", ""),
                })
    except (ClientError, NoCredentialsError) as e:
        print(f"CodeArtifact scan error in {region} ({creds.account_id}): {e}")
    return resources


# ════════════════════════════════════════════════════════════════════════════════
#  MANAGEMENT & GOVERNANCE
# ════════════════════════════════════════════════════════════════════════════════

def scan_cloudwatch_logs(creds: AccountCredentials, region: str) -> list:
    resources = []
    try:
        logs = creds.get_client("logs", region)
        for page in logs.get_paginator("describe_log_groups").paginate():
            for group in page.get("logGroups", []):
                resources.append({
                    **_b("CloudWatchLogGroup", group["logGroupName"], group["logGroupName"], region, creds),
                    "retention_days": group.get("retentionInDays"),
                    "stored_bytes": group.get("storedBytes", 0),
                })
    except (ClientError, NoCredentialsError) as e:
        print(f"CloudWatch Logs scan error in {region} ({creds.account_id}): {e}")
    return resources


def scan_cloudwatch_synthetics(creds: AccountCredentials, region: str) -> list:
    resources = []
    try:
        syn = creds.get_client("synthetics", region)
        resp = syn.describe_canaries()
        for canary in resp.get("Canaries", []):
            resources.append({
                **_b("CloudWatchCanary", canary["Id"], canary["Name"], region, creds),
                "status": canary.get("Status", {}).get("State", ""),
                "runtime_version": canary.get("RuntimeVersion", ""),
                "schedule": canary.get("Schedule", {}).get("Expression", ""),
                "success_retention_days": canary.get("SuccessRetentionPeriodInDays", 31),
                "failure_retention_days": canary.get("FailureRetentionPeriodInDays", 31),
            })
    except (ClientError, NoCredentialsError) as e:
        print(f"CloudWatch Synthetics scan error in {region} ({creds.account_id}): {e}")
    return resources


def scan_cloudtrail(creds: AccountCredentials, region: str) -> list:
    resources = []
    try:
        ct = creds.get_client("cloudtrail", region)
        for trail in ct.describe_trails(includeShadowTrails=False).get("trailList", []):
            resources.append({
                **_b("CloudTrailTrail", trail["TrailARN"], trail["Name"], region, creds),
                "is_multi_region": trail.get("IsMultiRegionTrail", False),
                "log_file_validation": trail.get("LogFileValidationEnabled", False),
                "include_global_service_events": trail.get("IncludeGlobalServiceEvents", False),
                "is_logging": False,
                "s3_bucket": trail.get("S3BucketName", ""),
            })
    except (ClientError, NoCredentialsError) as e:
        print(f"CloudTrail scan error in {region} ({creds.account_id}): {e}")
    return resources


def scan_config_service(creds: AccountCredentials, region: str) -> list:
    resources = []
    try:
        config = creds.get_client("config", region)
        recorders = config.describe_configuration_recorders().get("ConfigurationRecorders", [])
        statuses = {}
        try:
            for s in config.describe_configuration_recorder_status().get("ConfigurationRecordersStatus", []):
                statuses[s["name"]] = s.get("recording", False)
        except ClientError:
            pass
        for recorder in recorders:
            resources.append({
                **_b("ConfigRecorder", recorder["name"], recorder["name"], region, creds),
                "recording": statuses.get(recorder["name"], False),
                "all_supported": recorder.get("recordingGroup", {}).get("allSupported", False),
                "include_global_resource_types": recorder.get("recordingGroup", {}).get("includeGlobalResourceTypes", False),
            })
    except (ClientError, NoCredentialsError) as e:
        print(f"Config scan error in {region} ({creds.account_id}): {e}")
    return resources


def scan_xray(creds: AccountCredentials, region: str) -> list:
    resources = []
    try:
        xray = creds.get_client("xray", region)
        resp = xray.get_groups()
        for group in resp.get("Groups", []):
            if group["GroupName"] == "Default":
                continue
            resources.append({
                **_b("XRayGroup", group["GroupARN"], group["GroupName"], region, creds),
                "filter_expression": group.get("FilterExpression", ""),
                "insights_enabled": group.get("InsightsConfiguration", {}).get("InsightsEnabled", False),
            })
    except (ClientError, NoCredentialsError) as e:
        print(f"X-Ray scan error in {region} ({creds.account_id}): {e}")
    return resources


# ════════════════════════════════════════════════════════════════════════════════
#  BUSINESS APPLICATIONS
# ════════════════════════════════════════════════════════════════════════════════

def scan_connect(creds: AccountCredentials, region: str) -> list:
    resources = []
    try:
        conn = creds.get_client("connect", region)
        resp = conn.list_instances()
        for inst in resp.get("InstanceSummaryList", []):
            resources.append({
                **_b("ConnectInstance", inst["Arn"], inst.get("InstanceAlias", inst["Id"]), region, creds),
                "instance_status": inst.get("InstanceStatus", ""),
                "service_role": inst.get("ServiceRole", ""),
                "inbound_calls_enabled": inst.get("InboundCallsEnabled", False),
                "outbound_calls_enabled": inst.get("OutboundCallsEnabled", False),
                "created_time": _dt(inst.get("CreatedTime")),
            })
    except (ClientError, NoCredentialsError) as e:
        print(f"Connect scan error in {region} ({creds.account_id}): {e}")
    return resources


def scan_ses(creds: AccountCredentials, region: str) -> list:
    resources = []
    try:
        ses = creds.get_client("sesv2", region)
        for page in ses.get_paginator("list_dedicated_ip_pools").paginate():
            for pool_name in page.get("DedicatedIpPools", []):
                try:
                    ips = ses.get_dedicated_ips(PoolName=pool_name).get("DedicatedIps", [])
                    for ip in ips:
                        resources.append({
                            **_b("SESDedicatedIP", ip["Ip"], ip["Ip"], region, creds),
                            "pool_name": pool_name,
                            "warmup_status": ip.get("WarmupStatus", ""),
                            "warmup_percentage": ip.get("WarmupPercentage", 0),
                        })
                except ClientError:
                    pass
    except (ClientError, NoCredentialsError) as e:
        print(f"SES scan error in {region} ({creds.account_id}): {e}")
    return resources


def scan_workspaces(creds: AccountCredentials, region: str) -> list:
    resources = []
    try:
        ws = creds.get_client("workspaces", region)
        for page in ws.get_paginator("describe_workspaces").paginate():
            for workspace in page.get("Workspaces", []):
                resources.append({
                    **_b("WorkSpace", workspace["WorkspaceId"], workspace.get("ComputerName", workspace["WorkspaceId"]), region, creds),
                    "bundle_id": workspace.get("BundleId", ""),
                    "directory_id": workspace.get("DirectoryId", ""),
                    "state": workspace.get("State", ""),
                    "running_mode": workspace.get("WorkspaceProperties", {}).get("RunningMode", ""),
                    "compute_type": workspace.get("WorkspaceProperties", {}).get("ComputeTypeName", ""),
                })
    except (ClientError, NoCredentialsError) as e:
        print(f"WorkSpaces scan error in {region} ({creds.account_id}): {e}")
    return resources


def scan_pinpoint(creds: AccountCredentials, region: str) -> list:
    resources = []
    try:
        pp = creds.get_client("pinpoint", region)
        resp = pp.get_apps()
        for app in resp.get("ApplicationsResponse", {}).get("Item", []):
            resources.append({
                **_b("PinpointApp", app["Id"], app["Name"], region, creds),
                "creation_date": app.get("CreationDate", ""),
            })
    except (ClientError, NoCredentialsError) as e:
        print(f"Pinpoint scan error in {region} ({creds.account_id}): {e}")
    return resources


# ════════════════════════════════════════════════════════════════════════════════
#  MEDIA
# ════════════════════════════════════════════════════════════════════════════════

def scan_mediaconvert(creds: AccountCredentials, region: str) -> list:
    resources = []
    try:
        # MediaConvert requires the regional endpoint
        mc_base = creds.get_client("mediaconvert", region)
        endpoint = mc_base.describe_endpoints().get("Endpoints", [{}])[0].get("Url", "")
        if endpoint:
            mc = creds.get_client("mediaconvert", region)
            resp = mc.list_queues()
            for queue in resp.get("Queues", []):
                if queue["Name"] == "Default":
                    continue
                resources.append({
                    **_b("MediaConvertQueue", queue["Arn"], queue["Name"], region, creds),
                    "type": queue.get("Type", ""),
                    "status": queue.get("Status", ""),
                    "pricing_plan": queue.get("PricingPlan", ""),
                    "submitted_jobs_count": queue.get("SubmittedJobsCount", 0),
                })
    except (ClientError, NoCredentialsError) as e:
        print(f"MediaConvert scan error in {region} ({creds.account_id}): {e}")
    return resources


def scan_medialive(creds: AccountCredentials, region: str) -> list:
    resources = []
    try:
        ml = creds.get_client("medialive", region)
        resp = ml.list_channels()
        for channel in resp.get("Channels", []):
            resources.append({
                **_b("MediaLiveChannel", channel["Arn"], channel["Name"], region, creds),
                "channel_class": channel.get("ChannelClass", ""),
                "state": channel.get("State", ""),
                "input_attachments_count": len(channel.get("InputAttachments", [])),
            })
    except (ClientError, NoCredentialsError) as e:
        print(f"MediaLive scan error in {region} ({creds.account_id}): {e}")
    return resources


def scan_ivs(creds: AccountCredentials, region: str) -> list:
    resources = []
    try:
        ivs = creds.get_client("ivs", region)
        resp = ivs.list_channels()
        for channel in resp.get("channels", []):
            resources.append({
                **_b("IVSChannel", channel["arn"], channel["name"], region, creds),
                "type": channel.get("type", ""),
                "latency_mode": channel.get("latencyMode", ""),
                "authorized": channel.get("authorized", False),
                "recording_configuration_arn": channel.get("recordingConfigurationArn", ""),
            })
    except (ClientError, NoCredentialsError) as e:
        print(f"IVS scan error in {region} ({creds.account_id}): {e}")
    return resources


# ════════════════════════════════════════════════════════════════════════════════
#  ORCHESTRATOR
# ════════════════════════════════════════════════════════════════════════════════

# All resource bucket keys — one per service type stored
ALL_RESOURCE_KEYS = [
    "ec2", "elb", "autoscaling", "ecs", "eks", "ecr", "app_runner",
    "elastic_beanstalk", "batch", "lightsail",
    "rds", "elasticache", "dynamodb", "dax", "redshift", "documentdb",
    "neptune", "timestream", "qldb", "keyspaces", "memorydb", "dms",
    "s3", "efs", "fsx", "backup",
    "lambda", "cloudwatch_logs",
    "cloudfront", "apigateway", "transit_gateway", "vpc_endpoints",
    "global_accelerator", "direct_connect", "network_firewall",
    "route53", "transfer_family", "waf",
    "sqs", "sns", "kinesis", "msk", "mq", "eventbridge",
    "step_functions", "appsync",
    "emr", "glue", "athena", "opensearch", "quicksight",
    "sagemaker", "bedrock", "rekognition", "comprehend", "lex",
    "kms", "secretsmanager", "ssm", "acm_pca", "guardduty",
    "macie", "inspector", "security_hub", "firewall_manager",
    "shield", "license_manager",
    "cloudwatch_synthetics", "cloudtrail", "config_service", "xray",
    "codebuild", "codepipeline", "codeartifact",
    "connect", "ses", "workspaces", "pinpoint",
    "mediaconvert", "medialive", "ivs",
]

# Maps service_id -> [(scanner_fn, bucket_key, is_global)]
# is_global=True: scanner takes (creds, target_regions) and runs once per account
# is_global=False: scanner takes (creds, region) and runs once per region
_DISPATCH: dict = {
    "ec2":                  [(scan_ec2, "ec2", False), (scan_cloudwatch_logs, "cloudwatch_logs", False)],
    "elb":                  [(scan_elb, "elb", False)],
    "autoscaling":          [(scan_autoscaling, "autoscaling", False)],
    "ecs":                  [(scan_ecs, "ecs", False)],
    "eks":                  [(scan_eks, "eks", False)],
    "ecr":                  [(scan_ecr, "ecr", False)],
    "app_runner":           [(scan_app_runner, "app_runner", False)],
    "elastic_beanstalk":    [(scan_elastic_beanstalk, "elastic_beanstalk", False)],
    "batch":                [(scan_batch, "batch", False)],
    "lightsail":            [(scan_lightsail, "lightsail", False)],
    "rds":                  [(scan_rds, "rds", False)],
    "elasticache":          [(scan_elasticache, "elasticache", False)],
    "dynamodb":             [(scan_dynamodb, "dynamodb", False)],
    "dax":                  [(scan_dax, "dax", False)],
    "redshift":             [(scan_redshift, "redshift", False)],
    "documentdb":           [(scan_documentdb, "documentdb", False)],
    "neptune":              [(scan_neptune, "neptune", False)],
    "timestream":           [(scan_timestream, "timestream", False)],
    "qldb":                 [(scan_qldb, "qldb", False)],
    "keyspaces":            [(scan_keyspaces, "keyspaces", False)],
    "memorydb":             [(scan_memorydb, "memorydb", False)],
    "dms":                  [(scan_dms, "dms", False)],
    "s3":                   [(scan_s3, "s3", True)],
    "efs":                  [(scan_efs, "efs", False)],
    "fsx":                  [(scan_fsx, "fsx", False)],
    "backup":               [(scan_backup, "backup", False)],
    "lambda":               [(scan_lambda, "lambda", False)],
    "cloudfront":           [(scan_cloudfront, "cloudfront", True)],
    "apigateway":           [(scan_apigateway, "apigateway", False)],
    "transit_gateway":      [(scan_transit_gateway, "transit_gateway", False)],
    "vpc_endpoints":        [(scan_vpc_endpoints, "vpc_endpoints", False)],
    "global_accelerator":   [(scan_global_accelerator, "global_accelerator", True)],
    "direct_connect":       [(scan_direct_connect, "direct_connect", False)],
    "network_firewall":     [(scan_network_firewall, "network_firewall", False)],
    "route53":              [(scan_route53, "route53", True)],
    "transfer_family":      [(scan_transfer_family, "transfer_family", False)],
    "waf":                  [(scan_waf, "waf", False)],
    "sqs":                  [(scan_sqs, "sqs", False)],
    "sns":                  [(scan_sns, "sns", False)],
    "kinesis":              [(scan_kinesis, "kinesis", False)],
    "msk":                  [(scan_msk, "msk", False)],
    "mq":                   [(scan_mq, "mq", False)],
    "eventbridge":          [(scan_eventbridge, "eventbridge", False)],
    "step_functions":       [(scan_step_functions, "step_functions", False)],
    "appsync":              [(scan_appsync, "appsync", False)],
    "emr":                  [(scan_emr, "emr", False)],
    "glue":                 [(scan_glue, "glue", False)],
    "athena":               [(scan_athena, "athena", False)],
    "opensearch":           [(scan_opensearch, "opensearch", False)],
    "quicksight":           [(scan_quicksight, "quicksight", True)],
    "sagemaker":            [(scan_sagemaker, "sagemaker", False)],
    "bedrock":              [(scan_bedrock, "bedrock", False)],
    "rekognition":          [(scan_rekognition, "rekognition", False)],
    "comprehend":           [(scan_comprehend, "comprehend", False)],
    "lex":                  [(scan_lex, "lex", False)],
    "kms":                  [(scan_kms, "kms", False)],
    "secretsmanager":       [(scan_secretsmanager, "secretsmanager", False)],
    "ssm":                  [(scan_ssm, "ssm", False)],
    "acm_pca":              [(scan_acm_pca, "acm_pca", False)],
    "guardduty":            [(scan_guardduty, "guardduty", False)],
    "macie":                [(scan_macie, "macie", False)],
    "inspector":            [(scan_inspector, "inspector", False)],
    "security_hub":         [(scan_security_hub, "security_hub", False)],
    "firewall_manager":     [(scan_firewall_manager, "firewall_manager", True)],
    "shield":               [(scan_shield, "shield", True)],
    "license_manager":      [(scan_license_manager, "license_manager", False)],
    "cloudwatch_synthetics":[(scan_cloudwatch_synthetics, "cloudwatch_synthetics", False)],
    "cloudtrail":           [(scan_cloudtrail, "cloudtrail", False)],
    "config_service":       [(scan_config_service, "config_service", False)],
    "xray":                 [(scan_xray, "xray", False)],
    "codebuild":            [(scan_codebuild, "codebuild", False)],
    "codepipeline":         [(scan_codepipeline, "codepipeline", False)],
    "codeartifact":         [(scan_codeartifact, "codeartifact", False)],
    "connect":              [(scan_connect, "connect", False)],
    "ses":                  [(scan_ses, "ses", False)],
    "workspaces":           [(scan_workspaces, "workspaces", False)],
    "pinpoint":             [(scan_pinpoint, "pinpoint", False)],
    "mediaconvert":         [(scan_mediaconvert, "mediaconvert", False)],
    "medialive":            [(scan_medialive, "medialive", False)],
    "ivs":                  [(scan_ivs, "ivs", False)],
}


def scan_resources(
    creds_list: list,
    regions: list,
    services: list,
    progress_callback: Optional[Callable[[str], None]] = None,
) -> dict:
    """Scan all requested services across all accounts and regions in parallel."""

    def _cb(msg: str):
        if progress_callback:
            try:
                progress_callback(msg)
            except Exception:
                pass

    # Only allocate buckets for the services being scanned
    requested_buckets = {bucket_key for svc in services if svc in _DISPATCH for _, bucket_key, _ in _DISPATCH[svc]}
    all_resources: dict = {key: [] for key in requested_buckets}
    lock = threading.Lock()
    global_scanned: set = set()

    # Build the full list of tasks to run concurrently
    tasks = []  # (creds, scanner_fn, bucket_key, is_global, label, call_arg)
    for creds in creds_list:
        acct = f"{creds.account_name} ({creds.account_id})"
        for svc in services:
            if svc not in _DISPATCH:
                continue
            for scanner_fn, bucket_key, is_global in _DISPATCH[svc]:
                if is_global:
                    dedup_key = (creds.account_id, f"{svc}:{bucket_key}")
                    with lock:
                        if dedup_key in global_scanned:
                            continue
                        global_scanned.add(dedup_key)
                    tasks.append((creds, scanner_fn, bucket_key, f"{svc} (global) — {acct}", regions))
                else:
                    for region in regions:
                        tasks.append((creds, scanner_fn, bucket_key, f"{svc} in {region} — {acct}", region))

    # Cap workers: enough to saturate I/O-bound boto3 calls without overwhelming AWS rate limits
    max_workers = min(20, len(tasks)) if tasks else 1

    def _run(task):
        creds, scanner_fn, bucket_key, label, call_arg = task
        _cb(f"Scanning {label}...")
        try:
            return bucket_key, scanner_fn(creds, call_arg)
        except Exception as e:
            print(f"Scan error [{label}]: {e}")
            return bucket_key, []

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        for bucket_key, results in pool.map(_run, tasks):
            with lock:
                all_resources[bucket_key].extend(results)

    return all_resources
