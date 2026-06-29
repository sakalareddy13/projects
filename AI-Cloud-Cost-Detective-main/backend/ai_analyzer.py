"""
Multi-cloud cost analysis engine.

AI path  — uses the first configured AI provider (Anthropic, OpenAI, Google Gemini,
           AWS Bedrock, or any OpenAI-compatible provider such as Groq, Mistral,
           DeepSeek, xAI, Cohere, Together, Perplexity, Azure OpenAI, Ollama).
           Provider is auto-detected from environment API keys, or forced via
           AI_PROVIDER. See _PROVIDER_REGISTRY and _DETECTION_ORDER below.

Fallback — built-in rule-based engines require no API key and support all three
           cloud providers: rule_based_analyze (AWS), rule_based_analyze_azure,
           rule_based_analyze_gcp. All engines return output in the ANALYSIS_TOOL
           schema so the frontend needs no cloud-specific handling.

Entry point: analyze_resources(resources, cloud_provider, ai_provider, ai_api_key)
"""

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


# ─── rule-based analyzer (no API key required) ───────────────────────────────

def rule_based_analyze(resources: dict) -> dict:
    """
    Inspect raw resource data and flag issues using hardcoded AWS best-practice rules.
    Returns the same schema as the AI analyzer so the frontend needs no changes.
    """
    issues: list[dict] = []

    def issue(service, resource, issue_type, severity, explanation, fix, savings):
        issues.append({
            "service": service,
            "resource_name": resource.get("name", resource.get("id", "")),
            "resource_id": resource.get("id", ""),
            "region": resource.get("region", ""),
            "account_id": resource.get("account_id", ""),
            "account_name": resource.get("account_name", ""),
            "issue_type": issue_type,
            "severity": severity,
            "explanation": explanation,
            "fix_command": fix,
            "potential_monthly_savings": savings,
        })

    # ── EC2 Instances ────────────────────────────────────────────────────────
    for r in resources.get("ec2", []):
        if r.get("type") != "EC2Instance":
            continue
        itype = r.get("instance_type", "")
        state = r.get("state", "")
        region = r.get("region", "us-east-1")
        rid = r.get("id", "")

        if state == "stopped":
            issue(
                "EC2", r, "unused", "medium",
                f"Instance {rid} is stopped but still incurring EBS and EIP costs.",
                f"aws ec2 terminate-instances --instance-ids {rid} --region {region}",
                8.0,
            )

        if itype.startswith("t2."):
            new_type = itype.replace("t2.", "t3.")
            issue(
                "EC2", r, "non-optimized", "low",
                f"Instance uses older generation {itype}. Upgrade to {new_type} for ~10% cost savings and better performance.",
                f"aws ec2 modify-instance-attribute --instance-id {rid} --instance-type {{\"Value\":\"{new_type}\"}} --region {region}  # must stop instance first",
                5.0,
            )
        elif itype.startswith("m4."):
            new_type = itype.replace("m4.", "m5.")
            issue(
                "EC2", r, "non-optimized", "low",
                f"Instance uses older generation {itype}. Upgrade to {new_type} for ~10% savings.",
                f"aws ec2 modify-instance-attribute --instance-id {rid} --instance-type {{\"Value\":\"{new_type}\"}} --region {region}  # must stop instance first",
                10.0,
            )

    # ── EBS Volumes ──────────────────────────────────────────────────────────
    for r in resources.get("ec2", []):
        if r.get("type") != "EBSVolume":
            continue
        region = r.get("region", "us-east-1")
        vid = r.get("id", "")
        size = r.get("size_gb", 0)
        vtype = r.get("volume_type", "")

        if not r.get("attached"):
            savings = round(size * 0.10, 2)
            issue(
                "EBS", r, "unused", "high",
                f"Volume {vid} ({size} GB, {vtype}) is unattached — you are paying ${savings:.2f}/month for nothing.",
                f"aws ec2 delete-volume --volume-id {vid} --region {region}",
                savings,
            )
        elif vtype == "gp2":
            savings = round(size * 0.02, 2)  # gp3 is $0.02/GB cheaper
            issue(
                "EBS", r, "non-optimized", "low",
                f"Volume {vid} ({size} GB) uses gp2. Switching to gp3 saves ~20% (${savings:.2f}/month) with better baseline performance.",
                f"aws ec2 modify-volume --volume-id {vid} --volume-type gp3 --region {region}",
                savings,
            )

    # ── Elastic IPs ──────────────────────────────────────────────────────────
    for r in resources.get("ec2", []):
        if r.get("type") != "ElasticIP":
            continue
        if not r.get("associated"):
            region = r.get("region", "us-east-1")
            alloc = r.get("id", "")
            issue(
                "EC2", r, "unused", "high",
                f"Elastic IP {r.get('name')} is not associated with any instance — costs $3.60/month.",
                f"aws ec2 release-address --allocation-id {alloc} --region {region}",
                3.60,
            )

    # ── NAT Gateways ─────────────────────────────────────────────────────────
    for r in resources.get("ec2", []):
        if r.get("type") != "NatGateway":
            continue
        if r.get("state") == "available":
            region = r.get("region", "us-east-1")
            nat_id = r.get("id", "")
            issue(
                "NAT Gateway", r, "unused", "medium",
                f"NAT Gateway {nat_id} is running at ~$32/month fixed cost plus data transfer. Verify it is still needed.",
                f"aws ec2 delete-nat-gateway --nat-gateway-id {nat_id} --region {region}",
                32.0,
            )

    # ── RDS Instances ────────────────────────────────────────────────────────
    for r in resources.get("rds", []):
        if r.get("type") != "RDSInstance":
            continue
        region = r.get("region", "us-east-1")
        db_id = r.get("id", "")

        if r.get("backup_retention", 1) == 0:
            issue(
                "RDS", r, "misconfigured", "high",
                f"RDS instance {db_id} has automated backups disabled — data loss risk with no extra cost to enable.",
                f"aws rds modify-db-instance --db-instance-identifier {db_id} --backup-retention-period 7 --region {region}",
                0.0,
            )

        if r.get("publicly_accessible"):
            issue(
                "RDS", r, "misconfigured", "high",
                f"RDS instance {db_id} is publicly accessible — security risk. Disable unless strictly required.",
                f"aws rds modify-db-instance --db-instance-identifier {db_id} --no-publicly-accessible --region {region}",
                0.0,
            )

    # ── RDS Snapshots ────────────────────────────────────────────────────────
    for r in resources.get("rds", []):
        if r.get("type") != "RDSSnapshot":
            continue
        age = r.get("age_days", 0)
        size = r.get("allocated_storage", 0)
        region = r.get("region", "us-east-1")
        snap_id = r.get("id", "")

        if age > 30:
            savings = round(size * 0.095, 2)
            issue(
                "RDS", r, "unused", "medium",
                f"Manual snapshot {snap_id} is {age} days old ({size} GB). Old manual snapshots cost ${savings:.2f}/month.",
                f"aws rds delete-db-snapshot --db-snapshot-identifier {snap_id} --region {region}",
                savings,
            )

    # ── S3 Buckets ───────────────────────────────────────────────────────────
    for r in resources.get("s3", []):
        bucket = r.get("name", "")

        if not r.get("has_lifecycle_policy"):
            issue(
                "S3", r, "misconfigured", "medium",
                f"Bucket '{bucket}' has no lifecycle policy — objects accumulate indefinitely. Add a policy to transition old objects to cheaper storage classes.",
                f"aws s3api put-bucket-lifecycle-configuration --bucket {bucket} --lifecycle-configuration file://lifecycle.json",
                5.0,
            )

        if r.get("versioning") not in (None, "Disabled", "") and not r.get("has_lifecycle_policy"):
            issue(
                "S3", r, "misconfigured", "medium",
                f"Bucket '{bucket}' has versioning enabled but no lifecycle rule — old versions accumulate and incur storage costs.",
                f"aws s3api put-bucket-lifecycle-configuration --bucket {bucket} --lifecycle-configuration '{{\"Rules\":[{{\"ID\":\"expire-old-versions\",\"Status\":\"Enabled\",\"NoncurrentVersionExpiration\":{{\"NoncurrentDays\":30}}}}]}}'",
                10.0,
            )

    # ── Lambda Functions ─────────────────────────────────────────────────────
    for r in resources.get("lambda", []):
        region = r.get("region", "us-east-1")
        fn = r.get("name", "")
        mem = r.get("memory_size", 128)

        if mem >= 1024:
            issue(
                "Lambda", r, "over-provisioned", "low",
                f"Function '{fn}' is allocated {mem} MB memory. Unless CPU-intensive, reducing to 512 MB or less can cut costs significantly.",
                f"aws lambda update-function-configuration --function-name {fn} --memory-size 512 --region {region}",
                round((mem - 512) * 0.000016 * 1_000_000 / 1024, 2),
            )

    # ── CloudWatch Log Groups ────────────────────────────────────────────────
    for r in resources.get("cloudwatch_logs", []):
        region = r.get("region", "us-east-1")
        lg = r.get("name", "")
        stored_gb = round(r.get("stored_bytes", 0) / 1_073_741_824, 2)

        if r.get("retention_days") is None:
            savings = round(stored_gb * 0.03, 2)
            issue(
                "CloudWatch", r, "misconfigured", "low",
                f"Log group '{lg}' has no retention policy — logs accumulate forever at $0.03/GB/month ({stored_gb} GB stored).",
                f"aws logs put-retention-policy --log-group-name \"{lg}\" --retention-in-days 30 --region {region}",
                max(savings, 0.5),
            )

    # ── ELB / Load Balancers ─────────────────────────────────────────────────
    for r in resources.get("elb", []):
        region = r.get("region", "us-east-1")
        lb_name = r.get("name", r.get("id", ""))
        lb_type = r.get("type", "")
        if r.get("target_count", 1) == 0:
            issue(
                "ELB", r, "unused", "high",
                f"Load balancer '{lb_name}' ({lb_type}) has no registered targets. ALB/NLB cost ~$16-22/month even when idle.",
                f"aws elbv2 delete-load-balancer --load-balancer-arn {r.get('id', '')} --region {region}",
                18.0,
            )

    # ── ElastiCache ──────────────────────────────────────────────────────────
    for r in resources.get("elasticache", []):
        region = r.get("region", "us-east-1")
        cluster_id = r.get("id", "")
        node_type = r.get("cache_node_type", "")
        num_nodes = r.get("num_cache_nodes", 1)
        if r.get("status", "") in ("available",) and num_nodes == 1 and node_type.startswith("cache.r"):
            issue(
                "ElastiCache", r, "over-provisioned", "medium",
                f"ElastiCache cluster '{cluster_id}' uses memory-optimized {node_type} with a single node. "
                "Consider a smaller node type or remove if unused.",
                f"aws elasticache delete-cache-cluster --cache-cluster-id {cluster_id} --region {region}",
                50.0,
            )

    # ── DynamoDB ─────────────────────────────────────────────────────────────
    for r in resources.get("dynamodb", []):
        region = r.get("region", "us-east-1")
        table = r.get("name", r.get("id", ""))
        billing = r.get("billing_mode", "PROVISIONED")
        rcu = r.get("read_capacity", 0)
        wcu = r.get("write_capacity", 0)
        if billing == "PROVISIONED" and (rcu + wcu) > 20:
            cost = round((rcu * 0.00065 + wcu * 0.00013) * 730, 2)
            issue(
                "DynamoDB", r, "over-provisioned", "medium",
                f"Table '{table}' is PROVISIONED with {rcu} RCU / {wcu} WCU (~${cost:.2f}/month). "
                "Switch to PAY_PER_REQUEST if traffic is low or unpredictable.",
                f"aws dynamodb update-table --table-name {table} --billing-mode PAY_PER_REQUEST --region {region}",
                round(cost * 0.3, 2),
            )

    # ── Redshift ─────────────────────────────────────────────────────────────
    for r in resources.get("redshift", []):
        region = r.get("region", "us-east-1")
        cluster_id = r.get("id", "")
        node_type = r.get("node_type", "")
        num_nodes = r.get("number_of_nodes", 1)
        if num_nodes == 1 and "dc2" in node_type:
            issue(
                "Redshift", r, "over-provisioned", "medium",
                f"Redshift cluster '{cluster_id}' is a single-node {node_type} cluster. "
                "Single-node clusters are not HA and may be over-provisioned for dev/test workloads.",
                f"# Consider pausing: aws redshift pause-cluster --cluster-identifier {cluster_id} --region {region}",
                180.0,
            )

    # ── EFS ──────────────────────────────────────────────────────────────────
    for r in resources.get("efs", []):
        region = r.get("region", "us-east-1")
        fs_id = r.get("id", "")
        size_gb = r.get("size_gb", 0)
        if not r.get("has_lifecycle_policy") and size_gb > 10:
            savings = round(size_gb * 0.08, 2)  # difference between Standard and IA
            issue(
                "EFS", r, "misconfigured", "medium",
                f"EFS file system '{fs_id}' ({size_gb} GB) has no lifecycle policy. "
                "Enabling Infrequent Access tiering saves up to 92% on cold files.",
                f"aws efs put-lifecycle-configuration --file-system-id {fs_id} "
                f"--lifecycle-policies TransitionToIA=AFTER_30_DAYS --region {region}",
                savings,
            )

    # ── ECS ──────────────────────────────────────────────────────────────────
    for r in resources.get("ecs", []):
        region = r.get("region", "us-east-1")
        if r.get("type") == "ECSService":
            svc_name = r.get("name", r.get("id", ""))
            desired = r.get("desired_count", 0)
            running = r.get("running_count", 0)
            if desired > 0 and running == 0:
                issue(
                    "ECS", r, "unused", "high",
                    f"ECS service '{svc_name}' has {desired} desired tasks but 0 running. "
                    "It may be misconfigured or abandoned.",
                    f"aws ecs update-service --cluster {r.get('cluster', '')} --service {svc_name} "
                    f"--desired-count 0 --region {region}  # scale to 0 to stop billing",
                    20.0,
                )

    # ── SageMaker ────────────────────────────────────────────────────────────
    for r in resources.get("sagemaker", []):
        region = r.get("region", "us-east-1")
        if r.get("type") == "SageMakerNotebook":
            nb = r.get("name", r.get("id", ""))
            instance = r.get("instance_type", "")
            if r.get("status") == "Stopped":
                issue(
                    "SageMaker", r, "unused", "medium",
                    f"SageMaker notebook '{nb}' is stopped but its EBS volume still incurs storage costs.",
                    f"aws sagemaker delete-notebook-instance --notebook-instance-name {nb} --region {region}  "
                    "# backup data first",
                    5.0,
                )
            elif r.get("status") == "InService" and instance.startswith("ml.p"):
                issue(
                    "SageMaker", r, "over-provisioned", "high",
                    f"SageMaker notebook '{nb}' uses GPU instance {instance}. "
                    "GPU notebooks can cost $1-10+/hour — stop when not actively training.",
                    f"aws sagemaker stop-notebook-instance --notebook-instance-name {nb} --region {region}",
                    300.0,
                )
        elif r.get("type") == "SageMakerEndpoint":
            ep = r.get("name", r.get("id", ""))
            if r.get("status") == "InService":
                issue(
                    "SageMaker", r, "unused", "medium",
                    f"SageMaker endpoint '{ep}' is running. Endpoints incur costs even with zero invocations.",
                    f"aws sagemaker delete-endpoint --endpoint-name {ep} --region {region}  "
                    "# verify it's no longer needed",
                    50.0,
                )

    # ── OpenSearch ───────────────────────────────────────────────────────────
    for r in resources.get("opensearch", []):
        region = r.get("region", "us-east-1")
        domain = r.get("name", r.get("id", ""))
        instance_type = r.get("instance_type", "")
        instance_count = r.get("instance_count", 1)
        if instance_count >= 3 and "t3" not in instance_type and "t2" not in instance_type:
            issue(
                "OpenSearch", r, "over-provisioned", "medium",
                f"OpenSearch domain '{domain}' has {instance_count} x {instance_type} nodes. "
                "Verify data node count matches actual ingestion and query load.",
                f"# Resize via console or aws opensearch update-domain-config",
                100.0,
            )

    # ── EMR ──────────────────────────────────────────────────────────────────
    for r in resources.get("emr", []):
        region = r.get("region", "us-east-1")
        cluster_id = r.get("id", "")
        state = r.get("state", "")
        if state == "WAITING":
            issue(
                "EMR", r, "unused", "high",
                f"EMR cluster '{cluster_id}' is in WAITING state — it has finished all steps but is still running and billing.",
                f"aws emr terminate-clusters --cluster-ids {cluster_id} --region {region}",
                150.0,
            )

    # ── KMS ──────────────────────────────────────────────────────────────────
    for r in resources.get("kms", []):
        region = r.get("region", "us-east-1")
        key_id = r.get("id", "")
        if r.get("key_state") == "Enabled" and r.get("days_since_last_used", 0) > 90:
            issue(
                "KMS", r, "unused", "low",
                f"KMS key '{key_id}' has not been used in {r.get('days_since_last_used', 0)} days. "
                "Each customer-managed key costs $1/month.",
                f"aws kms schedule-key-deletion --key-id {key_id} --pending-window-in-days 30 --region {region}",
                1.0,
            )

    # ── Secrets Manager ──────────────────────────────────────────────────────
    for r in resources.get("secretsmanager", []):
        region = r.get("region", "us-east-1")
        secret = r.get("name", r.get("id", ""))
        age = r.get("age_days", 0)
        if age > 90 and r.get("last_accessed_days", age) > 90:
            issue(
                "Secrets Manager", r, "unused", "low",
                f"Secret '{secret}' was created {age} days ago and hasn't been accessed recently. "
                "Each secret costs $0.40/month.",
                f"aws secretsmanager delete-secret --secret-id \"{secret}\" --region {region}",
                0.40,
            )

    # ── SSM Parameters ───────────────────────────────────────────────────────
    for r in resources.get("ssm", []):
        region = r.get("region", "us-east-1")
        if r.get("type") == "SSMParameter" and r.get("tier") == "Advanced":
            param = r.get("name", r.get("id", ""))
            issue(
                "SSM", r, "non-optimized", "low",
                f"SSM parameter '{param}' uses the Advanced tier at $0.05/month. "
                "Downgrade to Standard if the value is ≤4 KB.",
                f"aws ssm put-parameter --name \"{param}\" --tier Standard --overwrite --region {region}",
                0.05,
            )

    # ── Glue ─────────────────────────────────────────────────────────────────
    for r in resources.get("glue", []):
        region = r.get("region", "us-east-1")
        if r.get("type") == "GlueJob":
            job = r.get("name", r.get("id", ""))
            if r.get("worker_type", "") in ("G.2X", "G.4X", "G.8X"):
                issue(
                    "Glue", r, "over-provisioned", "medium",
                    f"Glue job '{job}' uses {r.get('worker_type')} workers. "
                    "Evaluate if G.1X workers would complete the job within acceptable time at lower cost.",
                    f"# Update via aws glue update-job --job-name {job}",
                    30.0,
                )

    # ── MSK ──────────────────────────────────────────────────────────────────
    for r in resources.get("msk", []):
        region = r.get("region", "us-east-1")
        cluster_name = r.get("name", r.get("id", ""))
        num_brokers = r.get("number_of_broker_nodes", 0)
        broker_type = r.get("broker_instance_type", "")
        if num_brokers >= 6:
            issue(
                "MSK", r, "over-provisioned", "medium",
                f"MSK cluster '{cluster_name}' has {num_brokers} brokers ({broker_type}). "
                "Verify broker count matches actual partition and throughput requirements.",
                f"# Review broker count in AWS console for cluster {cluster_name}",
                200.0,
            )

    # ── WorkSpaces ───────────────────────────────────────────────────────────
    for r in resources.get("workspaces", []):
        region = r.get("region", "us-east-1")
        ws_id = r.get("id", "")
        state = r.get("state", "")
        running_mode = r.get("running_mode", "")
        if state == "AVAILABLE" and running_mode == "ALWAYS_ON":
            issue(
                "WorkSpaces", r, "non-optimized", "medium",
                f"WorkSpace '{ws_id}' uses ALWAYS_ON billing. Switching to AUTO_STOP can save 60-80% "
                "for users who work fewer than 80 hours/month.",
                f"aws workspaces modify-workspace-properties --workspace-id {ws_id} "
                f"--workspace-properties RunningMode=AUTO_STOP,RunningModeAutoStopTimeoutInMinutes=60 "
                f"--region {region}",
                30.0,
            )

    # ── NAT Gateways (already in ec2 bucket) — covered above ────────────────

    # ── Transit Gateway ──────────────────────────────────────────────────────
    for r in resources.get("transit_gateway", []):
        region = r.get("region", "us-east-1")
        tgw_id = r.get("id", "")
        attachment_count = r.get("attachment_count", 0)
        if attachment_count == 0:
            issue(
                "Transit Gateway", r, "unused", "medium",
                f"Transit Gateway '{tgw_id}' has no attachments but costs ~$36/month.",
                f"aws ec2 delete-transit-gateway --transit-gateway-id {tgw_id} --region {region}",
                36.0,
            )

    # ── ACM Private CA ───────────────────────────────────────────────────────
    for r in resources.get("acm_pca", []):
        region = r.get("region", "us-east-1")
        ca_arn = r.get("id", "")
        if r.get("status") == "ACTIVE":
            issue(
                "ACM PCA", r, "unused", "high",
                f"ACM Private CA '{ca_arn}' is ACTIVE and costs $400/month regardless of certificates issued. "
                "Delete if no longer issuing private certificates.",
                f"aws acm-pca delete-certificate-authority --certificate-authority-arn {ca_arn} "
                f"--permanent-deletion-time-in-days 30 --region {region}",
                400.0,
            )

    # ── Shield Advanced ──────────────────────────────────────────────────────
    for r in resources.get("shield", []):
        if r.get("type") == "ShieldSubscription":
            issue(
                "Shield", r, "unused", "high",
                "Shield Advanced subscription is active at $3,000/month. "
                "Verify this level of DDoS protection is still required.",
                "# Cancel via AWS console > Shield > Subscription",
                3000.0,
            )

    # ── CloudWatch Synthetics (Canaries) ─────────────────────────────────────
    for r in resources.get("cloudwatch_synthetics", []):
        region = r.get("region", "us-east-1")
        canary = r.get("name", r.get("id", ""))
        if r.get("status") == "RUNNING":
            issue(
                "CloudWatch Synthetics", r, "unused", "low",
                f"Canary '{canary}' is running. Each canary costs ~$0.0012/run — review if still needed.",
                f"aws synthetics stop-canary --name {canary} --region {region}",
                1.0,
            )

    # ── Direct Connect ───────────────────────────────────────────────────────
    for r in resources.get("direct_connect", []):
        region = r.get("region", "us-east-1")
        cx_id = r.get("id", "")
        bandwidth = r.get("bandwidth", "")
        if r.get("connection_state") == "available" and bandwidth in ("10Gbps", "100Gbps"):
            issue(
                "Direct Connect", r, "over-provisioned", "medium",
                f"Direct Connect connection '{cx_id}' uses {bandwidth} bandwidth. "
                "Verify actual throughput utilization justifies this capacity.",
                f"# Review utilization in CloudWatch before resizing connection {cx_id}",
                500.0,
            )

    # ── Connect (Contact Center) ─────────────────────────────────────────────
    for r in resources.get("connect", []):
        region = r.get("region", "us-east-1")
        instance_id = r.get("id", "")
        if r.get("type") == "ConnectInstance" and r.get("inbound_calls_enabled") and r.get("outbound_calls_enabled"):
            issue(
                "Connect", r, "unused", "low",
                f"Amazon Connect instance '{instance_id}' has both inbound and outbound calling enabled. "
                "Verify it's actively used — idle instances still incur service fees.",
                f"# Review usage in Amazon Connect console for instance {instance_id}",
                20.0,
            )

    # ── MediaLive ────────────────────────────────────────────────────────────
    for r in resources.get("medialive", []):
        region = r.get("region", "us-east-1")
        channel_id = r.get("id", "")
        if r.get("state") == "RUNNING":
            issue(
                "MediaLive", r, "unused", "high",
                f"MediaLive channel '{channel_id}' is RUNNING. Live channels cost $50-500+/hour depending on codec/resolution.",
                f"aws medialive stop-channel --channel-id {channel_id} --region {region}",
                500.0,
            )

    # ── CodeBuild ────────────────────────────────────────────────────────────
    for r in resources.get("codebuild", []):
        region = r.get("region", "us-east-1")
        project = r.get("name", r.get("id", ""))
        if r.get("environment_compute_type", "") in ("BUILD_GENERAL1_2XLARGE", "BUILD_GENERAL1_LARGE"):
            issue(
                "CodeBuild", r, "over-provisioned", "low",
                f"CodeBuild project '{project}' uses a large compute type. "
                "Evaluate if BUILD_GENERAL1_SMALL or MEDIUM would complete builds in acceptable time.",
                f"# Update via aws codebuild update-project --name {project}",
                5.0,
            )

    total = sum(len(v) for v in resources.values())
    monthly = round(sum(i["potential_monthly_savings"] for i in issues), 2)

    high = sum(1 for i in issues if i["severity"] == "high")
    medium = sum(1 for i in issues if i["severity"] == "medium")

    summary = (
        f"Scanned {total} resources and found {len(issues)} cost issues "
        f"({high} high, {medium} medium severity). "
        f"Estimated savings: ${monthly:.2f}/month (${monthly * 12:.2f}/year). "
        "(Analysis performed by built-in rule engine — add ANTHROPIC_API_KEY for AI-powered deeper analysis.)"
    ) if issues else (
        f"Scanned {total} resources — no obvious cost issues detected by the rule engine. "
        "Add ANTHROPIC_API_KEY for AI-powered deeper analysis."
    )

    return {
        "summary": summary,
        "total_resources": total,
        "issues_found": len(issues),
        "estimated_monthly_savings": monthly,
        "estimated_annual_savings": round(monthly * 12, 2),
        "issues": issues,
    }


# ─── shared tool schema & prompt ─────────────────────────────────────────────
#
# ANALYSIS_TOOL is the core data contract between the AI layer and the frontend.
# It is passed verbatim to every AI provider as a "tool" / "function" definition,
# forcing structured JSON output instead of free-form text.
#
# Field reference (mirrors the frontend AnalysisResult / AnalysisIssue TypeScript types):
#
#   summary                   Human-readable paragraph summarising the scan findings.
#   total_resources           Count of all resources examined (not just those with issues).
#   issues_found              len(issues) — must equal the number of entries in the issues array.
#   estimated_monthly_savings Sum of potential_monthly_savings across all issues (USD).
#   estimated_annual_savings  estimated_monthly_savings × 12 (USD).
#
#   issues[].service          Cloud service name, e.g. "EC2", "S3", "Azure VM", "GCS".
#   issues[].resource_name    Display name (tag Name / resource display name).
#   issues[].resource_id      Cloud resource identifier (instance-id, ARN, resource URI…).
#   issues[].region           Region/location string, e.g. "us-east-1", "eastus", "us-central1".
#   issues[].account_id       Cloud account / subscription / project ID (may be empty string).
#   issues[].account_name     Human-readable account name (may be empty string).
#   issues[].issue_type       One of: "over-provisioned" | "unused" | "misconfigured" | "non-optimized"
#   issues[].severity         One of: "high" | "medium" | "low"
#   issues[].explanation      Plain-English description of why this is a cost issue.
#   issues[].fix_command      CLI command or console step the user can run to resolve the issue.
#                             For AWS: aws CLI command. For Azure: az CLI. For GCP: gcloud CLI.
#   issues[].potential_monthly_savings  Estimated USD savings per month if the fix is applied.
#
# IMPORTANT: This same schema is used for AWS, Azure, and GCP scans. The rule-based
# fallback engines (rule_based_analyze / _azure / _gcp) also produce output in this
# exact shape so the frontend and downstream code need no cloud-specific handling.
# ─────────────────────────────────────────────────────────────────────────────

ANALYSIS_TOOL = {
    "name": "report_cost_analysis",
    "description": "Report cloud infrastructure cost analysis findings with actionable remediation steps",
    "input_schema": {
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
            "total_resources": {"type": "integer"},
            "issues_found": {"type": "integer"},
            "estimated_monthly_savings": {"type": "number"},
            "estimated_annual_savings": {"type": "number"},
            "issues": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "service": {"type": "string"},
                        "resource_name": {"type": "string"},
                        "resource_id": {"type": "string"},
                        "region": {"type": "string"},
                        "account_id": {"type": "string"},
                        "account_name": {"type": "string"},
                        "issue_type": {"type": "string", "enum": ["over-provisioned", "unused", "misconfigured", "non-optimized"]},
                        "severity": {"type": "string", "enum": ["high", "medium", "low"]},
                        "explanation": {"type": "string"},
                        "fix_command": {"type": "string"},
                        "potential_monthly_savings": {"type": "number"},
                    },
                    "required": ["service", "resource_name", "resource_id", "region",
                                 "issue_type", "severity", "explanation", "fix_command",
                                 "potential_monthly_savings"],
                },
            },
        },
        "required": ["summary", "total_resources", "issues_found",
                     "estimated_monthly_savings", "estimated_annual_savings", "issues"],
    },
}


_SERVICE_HINTS = {
    "ec2":                  "stopped instances, unattached EBS volumes, gp2→gp3 upgrades, old generation types (t2→t3, m4→m5), unassociated Elastic IPs, unnecessary NAT gateways",
    "rds":                  "public accessibility, missing backups, manual snapshots >30 days old, idle instances",
    "s3":                   "missing lifecycle policies, versioning without expiry rules",
    "lambda":               "over-provisioned memory (≥1024 MB), missing concurrency limits",
    "cloudwatch_logs":      "log groups without retention policies",
    "elb":                  "load balancers with no registered targets",
    "elasticache":          "oversized single-node clusters",
    "dynamodb":             "PROVISIONED tables that should be PAY_PER_REQUEST, unused tables",
    "redshift":             "single-node or paused clusters, idle warehouses",
    "efs":                  "file systems without lifecycle/IA tiering policies",
    "ecs":                  "services with 0 running tasks, oversized task definitions",
    "sagemaker":            "stopped notebook instances (EBS cost), running GPU notebooks, idle endpoints",
    "opensearch":           "over-provisioned domain node counts",
    "emr":                  "clusters in WAITING state (job done but still running)",
    "kms":                  "customer-managed keys unused >90 days ($1/month each)",
    "secretsmanager":       "secrets unused >90 days ($0.40/month each)",
    "ssm":                  "Advanced-tier parameters that could be Standard",
    "glue":                 "jobs using oversized worker types (G.2X/G.4X when G.1X would suffice)",
    "msk":                  "clusters with excessive broker counts",
    "workspaces":           "ALWAYS_ON desktops used <80 hrs/month (switch to AUTO_STOP)",
    "transit_gateway":      "gateways with no attachments ($36/month)",
    "acm_pca":              "active private CAs ($400/month)",
    "shield":               "subscription if not required ($3000/month)",
    "medialive":            "running live channels (very expensive per hour)",
    "direct_connect":       "over-provisioned bandwidth connections",
}


def _build_prompt(resources: dict) -> str:
    lines = []
    total = 0
    present_services = []
    for service, items in resources.items():
        if not items:
            continue
        present_services.append(service)
        lines.append(f"\n### {service.upper()} — {len(items)} resources")
        for r in items[:30]:
            lines.append(f"  - {json.dumps(r, default=str)}")
        total += len(items)

    hint_lines = [
        f"- {svc.upper()}: {hint}"
        for svc, hint in _SERVICE_HINTS.items()
        if svc in present_services
    ]
    hints_block = "\n".join(hint_lines) if hint_lines else "- Analyze the resources above for any cost inefficiencies."

    return f"""You are an expert AWS cost optimization engineer. Analyze ONLY the resources listed below and identify cost optimization opportunities.

## AWS Resources ({total} total)
{''.join(lines)}

IMPORTANT: Only analyze the resource types listed above. Do not infer or report on services that are not shown.

For the scanned services, check for:
{hints_block}

For each issue provide the exact AWS CLI fix command and a realistic monthly savings estimate.
Use the report_cost_analysis tool to return your findings."""


# ─── Azure rule-based analyzer ────────────────────────────────────────────────

def rule_based_analyze_azure(resources: dict) -> dict:
    issues: list[dict] = []

    def issue(service, resource, issue_type, severity, explanation, fix, savings):
        issues.append({
            "service": service,
            "resource_name": resource.get("name", resource.get("id", "")),
            "resource_id": resource.get("id", ""),
            "region": resource.get("region", ""),
            "account_id": resource.get("account_id", ""),
            "account_name": resource.get("account_name", ""),
            "issue_type": issue_type,
            "severity": severity,
            "explanation": explanation,
            "fix_command": fix,
            "potential_monthly_savings": savings,
        })

    for r in resources.get("virtual_machines", []):
        state = r.get("power_state", "")
        name = r.get("name", "")
        rg = r.get("resource_group", "")
        if state == "stopped":
            issue("Azure VM", r, "unused", "high",
                  f"VM '{name}' is stopped (not deallocated) — compute charges still apply.",
                  f"az vm deallocate --name {name} --resource-group {rg}",
                  50.0)
        elif state == "deallocated":
            issue("Azure VM", r, "unused", "medium",
                  f"VM '{name}' is deallocated but incurs managed disk and static IP costs.",
                  f"az vm delete --name {name} --resource-group {rg} --yes  # only if no longer needed",
                  15.0)

    for r in resources.get("managed_disks", []):
        if not r.get("attached"):
            size = r.get("disk_size_gb", 0)
            savings = round(max(size * 0.10, 1.0), 2)
            issue("Azure Disk", r, "unused", "high",
                  f"Managed disk '{r.get('name')}' ({size} GB, {r.get('sku', '')}) is unattached.",
                  f"az disk delete --name {r.get('name')} --resource-group {r.get('resource_group', '')} --yes",
                  savings)

    for r in resources.get("public_ips", []):
        if not r.get("associated"):
            sku = r.get("sku", "")
            savings = 3.65 if sku == "Standard" else 1.46
            issue("Azure Public IP", r, "unused", "medium",
                  f"Public IP '{r.get('name')}' ({r.get('ip_address', 'N/A')}) is not associated with any resource.",
                  f"az network public-ip delete --name {r.get('name')} --resource-group {r.get('resource_group', '')}",
                  savings)

    for r in resources.get("snapshots", []):
        if r.get("age_days", 0) > 90:
            size = r.get("disk_size_gb", 0)
            savings = round(size * 0.05, 2)
            issue("Azure Snapshot", r, "unused", "low",
                  f"Disk snapshot '{r.get('name')}' is {r.get('age_days')} days old ({size} GB).",
                  f"az snapshot delete --name {r.get('name')} --resource-group {r.get('resource_group', '')}",
                  savings)

    for r in resources.get("app_services", []):
        if r.get("state", "").lower() == "stopped":
            issue("Azure App Service", r, "unused", "medium",
                  f"App Service '{r.get('name')}' is stopped but its plan still incurs charges.",
                  f"az webapp delete --name {r.get('name')} --resource-group {r.get('resource_group', '')}  # or scale down plan",
                  20.0)

    for r in resources.get("sql_databases", []):
        if r.get("edition", "") == "Premium":
            issue("Azure SQL", r, "non-optimized", "low",
                  f"SQL Database '{r.get('name')}' uses Premium tier. Evaluate migrating to General Purpose (vCore) for better cost efficiency.",
                  "# Use Azure Portal to switch purchasing model",
                  30.0)

    total = sum(len(v) for v in resources.values())
    total_savings = round(sum(i["potential_monthly_savings"] for i in issues), 2)
    return {
        "summary": (
            f"Azure scan found {total} resources. {len(issues)} optimization opportunities "
            f"with ~${total_savings:.0f}/month potential savings."
            if issues else
            f"Azure scan found {total} resources. No major cost issues detected by the rule engine."
        ),
        "total_resources": total,
        "issues_found": len(issues),
        "estimated_monthly_savings": total_savings,
        "estimated_annual_savings": round(total_savings * 12, 2),
        "issues": issues,
    }


# ─── GCP rule-based analyzer ──────────────────────────────────────────────────

def rule_based_analyze_gcp(resources: dict) -> dict:
    issues: list[dict] = []

    def issue(service, resource, issue_type, severity, explanation, fix, savings):
        issues.append({
            "service": service,
            "resource_name": resource.get("name", resource.get("id", "")),
            "resource_id": resource.get("id", ""),
            "region": resource.get("region", ""),
            "account_id": resource.get("account_id", ""),
            "account_name": resource.get("account_name", ""),
            "issue_type": issue_type,
            "severity": severity,
            "explanation": explanation,
            "fix_command": fix,
            "potential_monthly_savings": savings,
        })

    for r in resources.get("compute_instances", []):
        status = r.get("status", "")
        name = r.get("name", "")
        zone = r.get("zone", r.get("region", ""))
        project = r.get("account_id", "")
        if status == "TERMINATED":
            issue("GCE", r, "unused", "medium",
                  f"VM '{name}' is TERMINATED but incurs persistent disk and static IP costs.",
                  f"gcloud compute instances delete {name} --zone={zone} --project={project}",
                  10.0)
        elif status == "RUNNING":
            mtype = r.get("machine_type", "")
            if mtype.startswith("n1-"):
                new_type = mtype.replace("n1-", "n2-")
                issue("GCE", r, "non-optimized", "low",
                      f"VM '{name}' uses older N1 machine type '{mtype}'. N2 offers ~20% better perf/cost.",
                      f"gcloud compute instances stop {name} --zone={zone} && "
                      f"gcloud compute instances set-machine-type {name} --zone={zone} --machine-type={new_type}",
                      8.0)

    for r in resources.get("persistent_disks", []):
        if not r.get("attached"):
            size = r.get("size_gb", 0)
            savings = round(max(size * 0.04, 1.0), 2)
            zone = r.get("zone", r.get("region", ""))
            issue("GCE Disk", r, "unused", "high",
                  f"Persistent disk '{r.get('name')}' ({size} GB) is not attached to any VM.",
                  f"gcloud compute disks delete {r.get('name')} --zone={zone} --project={r.get('account_id', '')}",
                  savings)

    for r in resources.get("static_ips", []):
        if not r.get("in_use"):
            issue("GCP Static IP", r, "unused", "medium",
                  f"Static IP '{r.get('name')}' ({r.get('address', 'N/A')}) is reserved but unused (~$7.30/month).",
                  f"gcloud compute addresses delete {r.get('name')} --project={r.get('account_id', '')}",
                  7.30)

    for r in resources.get("snapshots", []):
        if r.get("age_days", 0) > 90:
            size = r.get("disk_size_gb", 0)
            savings = round(size * 0.026, 2)
            issue("GCP Snapshot", r, "unused", "low",
                  f"Snapshot '{r.get('name')}' is {r.get('age_days')} days old ({size} GB).",
                  f"gcloud compute snapshots delete {r.get('name')} --project={r.get('account_id', '')}",
                  savings)

    for r in resources.get("cloud_sql", []):
        if r.get("tier", "").startswith("db-n1-"):
            issue("Cloud SQL", r, "non-optimized", "low",
                  f"Cloud SQL '{r.get('name')}' uses N1 machine type. N2 offers better performance per dollar.",
                  "# Edit instance in Cloud Console or gcloud to upgrade machine type",
                  15.0)

    total = sum(len(v) for v in resources.values())
    total_savings = round(sum(i["potential_monthly_savings"] for i in issues), 2)
    return {
        "summary": (
            f"GCP scan found {total} resources. {len(issues)} optimization opportunities "
            f"with ~${total_savings:.0f}/month potential savings."
            if issues else
            f"GCP scan found {total} resources. No major cost issues detected by the rule engine."
        ),
        "total_resources": total,
        "issues_found": len(issues),
        "estimated_monthly_savings": total_savings,
        "estimated_annual_savings": round(total_savings * 12, 2),
        "issues": issues,
    }


# ─── shared helpers ───────────────────────────────────────────────────────────

def _normalize(result: dict) -> dict:
    result.setdefault("estimated_annual_savings",
                      round(result.get("estimated_monthly_savings", 0) * 12, 2))
    for issue in result.get("issues", []):
        issue.setdefault("account_id", "")
        issue.setdefault("account_name", "")
    return result


def _fallback(resources: dict, reason: str, cloud_provider: str = "aws") -> dict:
    result = _rule_based_for_provider(resources, cloud_provider)
    result["summary"] = f"[{reason} — results below are from the built-in rule engine.] " + result.get("summary", "")
    return result


def _rule_based_for_provider(resources: dict, cloud_provider: str = "aws") -> dict:
    if cloud_provider == "azure":
        return rule_based_analyze_azure(resources)
    if cloud_provider == "gcp":
        return rule_based_analyze_gcp(resources)
    return rule_based_analyze(resources)


# OpenAI-compatible function-call tool definition (works for all OpenAI-compat providers)
_OPENAI_TOOL = {
    "type": "function",
    "function": {
        "name": ANALYSIS_TOOL["name"],
        "description": ANALYSIS_TOOL["description"],
        "parameters": ANALYSIS_TOOL["input_schema"],
    },
}

# JSON schema string used when a provider doesn't support tool calling (prompt-based JSON)
_JSON_SCHEMA_STR = json.dumps(ANALYSIS_TOOL["input_schema"], indent=2)


# ─── OpenAI-compatible providers ──────────────────────────────────────────────
# (env_key, default_model, base_url)  base_url=None → use provider's default
_OPENAI_COMPAT: dict[str, tuple[str | None, str, str | None]] = {
    "openai":      ("OPENAI_API_KEY",      "gpt-4o",                          None),
    "groq":        ("GROQ_API_KEY",        "llama-3.3-70b-versatile",         "https://api.groq.com/openai/v1"),
    "deepseek":    ("DEEPSEEK_API_KEY",    "deepseek-chat",                   "https://api.deepseek.com/v1"),
    "xai":         ("XAI_API_KEY",         "grok-3",                          "https://api.x.ai/v1"),
    "mistral":     ("MISTRAL_API_KEY",     "mistral-large-latest",            "https://api.mistral.ai/v1"),
    "cohere":      ("COHERE_API_KEY",      "command-r-plus",                  "https://api.cohere.ai/compatibility/v1"),
    "together":    ("TOGETHER_API_KEY",    "meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo", "https://api.together.xyz/v1"),
    "perplexity":  ("PERPLEXITY_API_KEY",  "sonar-pro",                       "https://api.perplexity.ai"),
    "ollama":      (None,                  "llama3.2",                        None),  # key-less, base_url from env
}


def _openai_compat_analyze(resources: dict, provider: str, api_key: str) -> dict:
    try:
        import openai as _openai
    except ImportError:
        return _fallback(resources, f"openai package not installed — run: pip install openai")

    env_key_name, default_model, default_base = _OPENAI_COMPAT[provider]
    model = os.getenv("AI_MODEL", default_model)

    if provider == "ollama":
        base_url = os.getenv("OLLAMA_BASE_URL", os.getenv("OLLAMA_HOST", "http://localhost:11434")) + "/v1"
        client = _openai.OpenAI(api_key="ollama", base_url=base_url)
    elif provider == "azure":
        endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "").rstrip("/")
        client = _openai.AzureOpenAI(
            api_key=api_key,
            azure_endpoint=endpoint,
            api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-01"),
        )
    else:
        client = _openai.OpenAI(api_key=api_key, base_url=default_base)

    try:
        response = client.chat.completions.create(
            model=model,
            tools=[_OPENAI_TOOL],
            tool_choice={"type": "function", "function": {"name": ANALYSIS_TOOL["name"]}},
            messages=[{"role": "user", "content": _build_prompt(resources)}],
        )
        tool_call = response.choices[0].message.tool_calls[0]
        return _normalize(json.loads(tool_call.function.arguments))
    except Exception as e:
        err_str = str(e).lower()
        if "authentication" in err_str or "api_key" in err_str or "401" in err_str:
            raise RuntimeError(f"{provider} authentication failed: {e}")
        logger.warning("ai.provider_failed", extra={"provider": provider, "error": str(e)})
        return _fallback(resources, f"{provider} error ({type(e).__name__})")


# ─── Anthropic (Claude) ───────────────────────────────────────────────────────

def _anthropic_analyze(resources: dict, api_key: str) -> dict:
    try:
        import anthropic as _anthropic
    except ImportError:
        return _fallback(resources, "anthropic package not installed — run: pip install anthropic")

    model = os.getenv("AI_MODEL", "claude-sonnet-4-6")
    client = _anthropic.Anthropic(api_key=api_key)

    try:
        message = client.messages.create(
            model=model,
            max_tokens=8192,
            tools=[ANALYSIS_TOOL],
            tool_choice={"type": "auto"},
            messages=[{"role": "user", "content": _build_prompt(resources)}],
        )
        for block in message.content:
            if block.type == "tool_use" and block.name == "report_cost_analysis":
                return _normalize(block.input)
    except Exception as e:
        err_str = str(e).lower()
        if "authentication" in err_str or "api_key" in err_str or "401" in err_str:
            raise RuntimeError(f"Anthropic authentication failed: {e}")
        logger.warning("ai.provider_failed", extra={"provider": "anthropic", "error": str(e)})
        return _fallback(resources, f"Anthropic error ({type(e).__name__})")

    return rule_based_analyze(resources)


# ─── Google Gemini ────────────────────────────────────────────────────────────

def _google_analyze(resources: dict, api_key: str) -> dict:
    try:
        from google import genai
        from google.genai import types as genai_types
    except ImportError:
        return _fallback(resources, "google-genai package not installed — run: pip install google-genai")

    model_name = os.getenv("AI_MODEL", "gemini-2.0-flash")
    client = genai.Client(api_key=api_key)

    prompt = (
        _build_prompt(resources)
        + f"\n\nReturn ONLY a valid JSON object matching this exact schema (no markdown, no extra text):\n{_JSON_SCHEMA_STR}"
    )

    try:
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                response_mime_type="application/json",
            ),
        )
        return _normalize(json.loads(response.text))
    except Exception as e:
        err_str = str(e).lower()
        if "api_key" in err_str or "401" in err_str or "permission" in err_str:
            raise RuntimeError(f"Google AI authentication failed: {e}")
        logger.warning("ai.provider_failed", extra={"provider": "google", "error": str(e)})
        return _fallback(resources, f"Google AI error ({type(e).__name__})")


# ─── AWS Bedrock ──────────────────────────────────────────────────────────────
# Uses existing boto3 — no extra package needed.

def _bedrock_analyze(resources: dict, api_key: str) -> dict:
    import boto3
    model_id = os.getenv("AI_MODEL", os.getenv("BEDROCK_MODEL_ID", "amazon.nova-pro-v1:0"))
    region = os.getenv("BEDROCK_REGION", os.getenv("AWS_REGION", "us-east-1"))

    tool_spec = {
        "toolSpec": {
            "name": ANALYSIS_TOOL["name"],
            "description": ANALYSIS_TOOL["description"],
            "inputSchema": {"json": ANALYSIS_TOOL["input_schema"]},
        }
    }

    try:
        client = boto3.client("bedrock-runtime", region_name=region)
        response = client.converse(
            modelId=model_id,
            messages=[{"role": "user", "content": [{"text": _build_prompt(resources)}]}],
            toolConfig={"tools": [tool_spec], "toolChoice": {"tool": {"name": ANALYSIS_TOOL["name"]}}},
        )
        for block in response.get("output", {}).get("message", {}).get("content", []):
            if block.get("toolUse", {}).get("name") == ANALYSIS_TOOL["name"]:
                return _normalize(block["toolUse"]["input"])
    except Exception as e:
        err_str = str(e).lower()
        if "credentials" in err_str or "access" in err_str or "authfailure" in err_str:
            raise RuntimeError(f"Bedrock authentication failed: {e}")
        logger.warning("ai.provider_failed", extra={"provider": "bedrock", "error": str(e)})
        return _fallback(resources, f"Bedrock error ({type(e).__name__})")

    return rule_based_analyze(resources)


# ─── provider detection ───────────────────────────────────────────────────────

# Full provider registry: name → (env_key, handler)
# OpenAI-compat providers share _openai_compat_analyze via a lambda.
_PROVIDER_REGISTRY: dict[str, tuple[str | None, callable]] = {
    # Native SDKs
    "anthropic":  ("ANTHROPIC_API_KEY",    _anthropic_analyze),
    "google":     ("GOOGLE_API_KEY",       _google_analyze),
    "gemini":     ("GEMINI_API_KEY",       _google_analyze),
    # AWS Bedrock — no API key (uses existing AWS credentials)
    "bedrock":    (None,                   _bedrock_analyze),
    # Azure OpenAI
    "azure":      ("AZURE_OPENAI_API_KEY", lambda r, k: _openai_compat_analyze(r, "azure", k)),
    # OpenAI-compatible (all use openai package)
    **{name: (cfg[0], lambda r, k, n=name: _openai_compat_analyze(r, n, k))
       for name, cfg in _OPENAI_COMPAT.items()},
}

# Priority order when AI_PROVIDER is not set
_DETECTION_ORDER = [
    "anthropic", "openai", "google", "gemini",
    "groq", "deepseek", "xai", "mistral", "cohere",
    "together", "perplexity", "azure", "bedrock", "ollama",
]


def _get_provider() -> tuple[str, str | None]:
    """Return (provider_name, api_key_or_None). Returns ('none', None) when nothing is configured."""
    explicit = os.getenv("AI_PROVIDER", "").strip().lower()

    if explicit:
        if explicit not in _PROVIDER_REGISTRY:
            logger.warning("ai.unknown_provider", extra={"provider": explicit})
            return "none", None
        env_key, _ = _PROVIDER_REGISTRY[explicit]
        api_key = os.getenv(env_key, "").strip() if env_key else None
        if env_key and not api_key:
            logger.warning("ai.missing_key", extra={"provider": explicit, "env_key": env_key})
            return "none", None
        return explicit, api_key

    # Auto-detect
    for name in _DETECTION_ORDER:
        env_key, _ = _PROVIDER_REGISTRY[name]
        if env_key is None:
            # Key-less provider (bedrock, ollama) — only used when explicitly set
            continue
        api_key = os.getenv(env_key, "").strip()
        if api_key:
            return name, api_key

    return "none", None


# ─── public entry point ───────────────────────────────────────────────────────

def analyze_resources(resources: dict, cloud_provider: str = "aws", ai_provider: str = None, ai_api_key: str = None) -> dict:
    """
    Route to the configured AI provider, or fall back to the built-in rule engine.
    cloud_provider: "aws" | "azure" | "gcp" — selects the correct rule engine fallback.

    Set ONE of these env vars (first found is used, or set AI_PROVIDER to force one):

      ANTHROPIC_API_KEY   → Claude        pip install anthropic          (already installed)
      OPENAI_API_KEY      → GPT-4o        pip install openai
      GOOGLE_API_KEY      → Gemini        pip install google-generativeai
      GEMINI_API_KEY      → Gemini        (alternative to GOOGLE_API_KEY)
      GROQ_API_KEY        → Llama/Groq    pip install openai
      DEEPSEEK_API_KEY    → DeepSeek      pip install openai
      XAI_API_KEY         → Grok          pip install openai
      MISTRAL_API_KEY     → Mistral       pip install openai
      COHERE_API_KEY      → Command R+    pip install openai
      TOGETHER_API_KEY    → Llama/Together pip install openai
      PERPLEXITY_API_KEY  → Sonar         pip install openai
      AZURE_OPENAI_API_KEY → Azure GPT    pip install openai  (+AZURE_OPENAI_ENDPOINT)
      AI_PROVIDER=bedrock → AWS Bedrock   no extra package (uses existing boto3)
      AI_PROVIDER=ollama  → Ollama local  pip install openai  (+OLLAMA_BASE_URL optional)

    Optional overrides:
      AI_PROVIDER=groq        force a specific provider
      AI_MODEL=llama3.2       override the default model for the chosen provider
    """
    # If a provider + key were supplied explicitly (from the UI), use them directly
    if ai_provider and ai_provider in _PROVIDER_REGISTRY:
        _, handler = _PROVIDER_REGISTRY[ai_provider]
        # Key-less providers (bedrock, ollama) don't need an api_key
        needs_key = _PROVIDER_REGISTRY[ai_provider][0] is not None
        if needs_key and not ai_api_key:
            logger.warning("ai.no_key_supplied", extra={"provider": ai_provider})
            return _rule_based_for_provider(resources, cloud_provider)
        logger.info("ai.using_provider", extra={"provider": ai_provider, "source": "ui"})
        try:
            return handler(resources, ai_api_key)
        except Exception as e:
            logger.warning("ai.provider_failed", extra={"provider": ai_provider, "error": str(e)})
            return _rule_based_for_provider(resources, cloud_provider)

    provider, api_key = _get_provider()

    if provider != "none":
        _, handler = _PROVIDER_REGISTRY[provider]
        logger.info("ai.using_provider", extra={"provider": provider, "model": os.getenv("AI_MODEL", "default"), "source": "env"})
        try:
            return handler(resources, api_key)
        except Exception as e:
            logger.warning("ai.provider_failed", extra={"provider": provider, "error": str(e)})
            return _rule_based_for_provider(resources, cloud_provider)

    logger.info("ai.rule_engine", extra={"cloud_provider": cloud_provider})
    return _rule_based_for_provider(resources, cloud_provider)
