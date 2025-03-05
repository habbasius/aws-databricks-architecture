# AWS & Databricks Integration Configuration Guide

This guide provides step-by-step instructions for configuring AWS services to work with Databricks for a modern data engineering architecture.

## 1. Cross-Account IAM Setup

To allow Databricks to access AWS resources, set up cross-account IAM roles.

### Create the IAM Role for Databricks

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::<databricks-account-id>:root"
      },
      "Action": "sts:AssumeRole",
      "Condition": {
        "StringEquals": {
          "sts:ExternalId": "<external-id-from-databricks>"
        }
      }
    }
  ]
}
```

### Attach Required Policies

Create a policy with the following permissions:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:ListBucket",
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject",
        "s3:GetBucketLocation"
      ],
      "Resource": [
        "arn:aws:s3:::data-lake-raw-*",
        "arn:aws:s3:::data-lake-raw-*/*",
        "arn:aws:s3:::data-lake-processed-*",
        "arn:aws:s3:::data-lake-processed-*/*",
        "arn:aws:s3:::data-lake-curated-*",
        "arn:aws:s3:::data-lake-curated-*/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "kinesis:GetShardIterator",
        "kinesis:GetRecords",
        "kinesis:DescribeStream",
        "kinesis:ListShards"
      ],
      "Resource": "arn:aws:kinesis:*:*:stream/*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "glue:CreateTable",
        "glue:UpdateTable",
        "glue:DeleteTable",
        "glue:GetTable",
        "glue:GetTables",
        "glue:GetDatabase",
        "glue:GetDatabases",
        "glue:CreateDatabase"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "sns:Publish"
      ],
      "Resource": "arn:aws:sns:*:*:data-quality-alerts"
    },
    {
      "Effect": "Allow",
      "Action": [
        "redshift:GetClusterCredentials",
        "redshift-data:ExecuteStatement",
        "redshift-data:DescribeStatement",
        "redshift-data:GetStatementResult"
      ],
      "Resource": "arn:aws:redshift:*:*:cluster/*"
    }
  ]
}
```

## 2. AWS Services Configuration

### 2.1 S3 Buckets Setup for Data Lake

Create three S3 buckets for the medallion architecture:

```bash
# Raw data zone (Bronze)
aws s3 mb s3://data-lake-raw-$(uuidgen | cut -d'-' -f1) --region us-east-1

# Processed data zone (Silver)
aws s3 mb s3://data-lake-processed-$(uuidgen | cut -d'-' -f1) --region us-east-1

# Curated data zone (Gold)
aws s3 mb s3://data-lake-curated-$(uuidgen | cut -d'-' -f1) --region us-east-1

# Monitoring data zone
aws s3 mb s3://data-lake-monitoring-$(uuidgen | cut -d'-' -f1) --region us-east-1
```

Enable versioning and appropriate lifecycle policies:

```bash
aws s3api put-bucket-versioning \
    --bucket data-lake-raw-XXXX \
    --versioning-configuration Status=Enabled

aws s3api put-bucket-lifecycle-configuration \
    --bucket data-lake-raw-XXXX \
    --lifecycle-configuration file://raw-lifecycle-config.json
```

Sample lifecycle configuration for raw data:

```json
{
  "Rules": [
    {
      "ID": "Move to IA after 30 days",
      "Status": "Enabled",
      "Filter": {},
      "Transitions": [
        {
          "Days": 30,
          "StorageClass": "STANDARD_IA"
        }
      ]
    }
  ]
}
```

### 2.2 Kinesis Stream Setup

Create a Kinesis Data Stream for real-time data ingestion:

```bash
aws kinesis create-stream \
    --stream-name customer-events-stream \
    --shard-count 4 \
    --region us-east-1
```

### 2.3 AWS Glue Data Catalog

Configure AWS Glue as the metastore for Databricks Unity Catalog:

```bash
aws glue create-database \
    --database-input '{"Name":"data_engineering", "Description":"Data Engineering Catalog"}'
```

### 2.4 AWS DMS for Database Migration

Set up AWS DMS for migrating data from source databases:

```bash
# Create a replication instance
aws dms create-replication-instance \
    --replication-instance-identifier data-engineering-dms \
    --replication-instance-class dms.t3.medium \
    --allocated-storage 50 \
    --vpc-security-group-ids sg-xxxxxxxxxxxx \
    --replication-subnet-group-id default-vpc-subnet-group

# Create a source endpoint (example for MySQL)
aws dms create-endpoint \
    --endpoint-identifier source-mysql \
    --endpoint-type source \
    --engine-name mysql \
    --username admin \
    --password <password> \
    --server-name mysql-source.xxxx.us-east-1.rds.amazonaws.com \
    --port 3306 \
    --database-name source_db

# Create a target endpoint (S3)
aws dms create-endpoint \
    --endpoint-identifier target-s3 \
    --endpoint-type target \
    --engine-name s3 \
    --s3-settings '{"ServiceAccessRoleArn":"arn:aws:iam::xxxx:role/dms-s3-role", "BucketName":"data-lake-raw-xxxx", "BucketFolder":"database-migration"}'

# Create a replication task
aws dms create-replication-task \
    --replication-task-identifier mysql-to-s3 \
    --source-endpoint-arn arn:aws:dms:us-east-1:xxxx:endpoint:source-mysql \
    --target-endpoint-arn arn:aws:dms:us-east-1:xxxx:endpoint:target-s3 \
    --replication-instance-arn arn:aws:dms:us-east-1:xxxx:rep:data-engineering-dms \
    --migration-type full-load-and-cdc \
    --table-mappings file://table-mappings.json \
    --replication-task-settings file://task-settings.json
```

### 2.5 Amazon Redshift Setup for Data Warehousing

Create a Redshift cluster for analytical queries:

```bash
aws redshift create-cluster \
    --cluster-identifier data-warehouse \
    --node-type dc2.large \
    --number-of-nodes 2 \
    --master-username admin \
    --master-user-password <password> \
    --db-name analytics \
    --vpc-security-group-ids sg-xxxxxxxxxxxx \
    --cluster-subnet-group-name default
```

Set up Redshift Spectrum for querying data lake:

```sql
-- Run in Redshift
CREATE EXTERNAL SCHEMA ext_data_lake
FROM DATA CATALOG 
DATABASE 'data_engineering' 
REGION 'us-east-1'
IAM_ROLE 'arn:aws:iam::xxxx:role/redshift-spectrum-role';
```

### 2.6 AWS SNS for Alerting

Create an SNS topic for data quality alerts:

```bash
aws sns create-topic --name data-quality-alerts

# Add a subscription (e.g., email)
aws sns subscribe \
    --topic-arn arn:aws:sns:us-east-1:xxxx:data-quality-alerts \
    --protocol email \
    --notification-endpoint alerts@example.com
```

## 3. Databricks Configuration

### 3.1 Workspace Setup

1. Deploy a new Databricks workspace through the AWS Marketplace
2. Configure workspace with VPC peering to your AWS VPC
3. Set up network security groups for controlled access

### 3.2 Cluster Configurations

Create multiple cluster policies for different workloads:

#### ETL Cluster Policy:

```json
{
  "spark_version": {
    "type": "fixed",
    "value": "10.4.x-scala2.12"
  },
  "aws_attributes.instance_profile_arn": {
    "type": "fixed",
    "value": "arn:aws:iam::xxxx:instance-profile/databricks-s3-access"
  },
  "node_type_id": {
    "type": "allowlist",
    "values": ["i3.xlarge", "i3.2xlarge", "i3.4xlarge"]
  },
  "autoscale.min_workers": {
    "type": "range",
    "minValue": 2,
    "maxValue": 4
  },
  "autoscale.max_workers": {
    "type": "range",
    "minValue": 4,
    "maxValue": 20
  },
  "autotermination_minutes": {
    "type": "fixed",
    "value": 30
  }
}
```

#### Analytics Cluster Policy:

```json
{
  "spark_version": {
    "type": "fixed",
    "value": "10.4.x-scala2.12"
  },
  "aws_attributes.instance_profile_arn": {
    "type": "fixed",
    "value": "arn:aws:iam::xxxx:instance-profile/databricks-s3-access"
  },
  "node_type_id": {
    "type": "allowlist",
    "values": ["r5.xlarge", "r5.2xlarge", "r5.4xlarge"]
  },
  "spark_conf.spark.databricks.delta.preview.enabled": {
    "type": "fixed",
    "value": "true"
  },
  "autotermination_minutes": {
    "type": "fixed",
    "value": 60
  }
}
```

### 3.3 Unity Catalog Setup

Configure Unity Catalog for centralized governance:

```sql
-- Create catalog
CREATE CATALOG IF NOT EXISTS data_engineering;

-- Create schemas
CREATE SCHEMA IF NOT EXISTS data_engineering.raw;
CREATE SCHEMA IF NOT EXISTS data_engineering.processed;
CREATE SCHEMA IF NOT EXISTS data_engineering.curated;

-- Create storage credential to access S3
CREATE STORAGE CREDENTIAL aws_s3_credential
WITH AWS_ROLE = 'arn:aws:iam::xxxx:role/databricks-s3-access';

-- Create external locations
CREATE EXTERNAL LOCATION s3_raw
URL 's3://data-lake-raw-xxxx/'
WITH (CREDENTIAL = aws_s3_credential);

CREATE EXTERNAL LOCATION s3_processed
URL 's3://data-lake-processed-xxxx/'
WITH (CREDENTIAL = aws_s3_credential);

CREATE EXTERNAL LOCATION s3_curated
URL 's3://data-lake-curated-xxxx/'
WITH (CREDENTIAL = aws_s3_credential);
```

### 3.4 Delta Live Tables Pipeline Configuration

Create a DLT pipeline for continuous data processing:

```json
{
  "name": "Customer Data Pipeline",
  "clusters": [
    {
      "label": "default",
      "autoscale": {
        "min_workers": 2,
        "max_workers": 8
      }
    }
  ],
  "libraries": [
    {
      "notebook": {
        "path": "/Repos/DataEngineering/etl/bronze_to_silver"
      }
    },
    {
      "notebook": {
        "path": "/Repos/DataEngineering/etl/silver_to_gold"
      }
    }
  ],
  "continuous": true,
  "edition": "advanced",
  "configuration": {
    "pipelines.enableTrackHistory": "true",
    "pipelines.applyChangesPreviewEnabled": "true"
  },
  "target": "data_engineering.curated"
}
```

### 3.5 Databricks SQL Configuration

Set up Databricks SQL endpoint for analytics:

```json
{
  "name": "Analytics Endpoint",
  "cluster_size": "Medium",
  "min_num_clusters": 1,
  "max_num_clusters": 3,
  "auto_stop_mins": 30,
  "enable_photon": true,
  "spot_instance_policy": "COST_OPTIMIZED",
  "warehouse_type": "PRO"
}
```

### 3.6 Databricks Workflows

Create a workflow for orchestrating the pipeline:

```json
{
  "name": "Data Engineering Pipeline",
  "tags": {
    "environment": "production"
  },
  "schedule": {
    "quartz_cron_expression": "0 0/15 * ? * * *",
    "timezone_id": "America/Los_Angeles",
    "pause_status": "UNPAUSED"
  },
  "tasks": [
    {
      "task_key": "ingest_data",
      "notebook_task": {
        "notebook_path": "/Repos/DataEngineering/notebooks/01_ingest_data",
        "base_parameters": {
          "date": "{{system.onCreation.date}}"
        }
      },
      "timeout_seconds": 600,
      "email_notifications": {}
    },
    {
      "task_key": "process_data",
      "depends_on": [
        {
          "task_key": "ingest_data"
        }
      ],
      "pipeline_task": {
        "pipeline_id": "12345678-abcd-1234-abcd-1234567890ab"
      },
      "timeout_seconds": 1200
    },
    {
      "task_key": "data_quality",
      "depends_on": [
        {
          "task_key": "process_data"
        }
      ],
      "notebook_task": {
        "notebook_path": "/Repos/DataEngineering/notebooks/03_data_quality",
        "base_parameters": {}
      },
      "timeout_seconds": 600
    },
    {
      "task_key": "sync_to_redshift",
      "depends_on": [
        {
          "task_key": "data_quality"
        }
      ],
      "notebook_task": {
        "notebook_path": "/Repos/DataEngineering/notebooks/04_sync_to_redshift",
        "base_parameters": {}
      },
      "timeout_seconds": 900
    }
  ]
}
```

## 4. Redshift Integration with Databricks

### 4.1 Configure Redshift Connection from Databricks

Create a Spark connection to Redshift:

```python
# Databricks notebook

# Configure connection details
redshift_host = "data-warehouse.xxxx.us-east-1.redshift.amazonaws.com"
redshift_port = "5439"
redshift_database = "analytics"
redshift_user = "databricks_user"
redshift_password = dbutils.secrets.get(scope="redshift", key="password")
redshift_iam_role = "arn:aws:iam::xxxx:role/redshift-s3-access"

# JDBC URL
jdbc_url = f"jdbc:redshift://{redshift_host}:{redshift_port}/{redshift_database}"

# Redshift to Databricks
df = spark.read \
    .format("com.databricks.spark.redshift") \
    .option("url", jdbc_url) \
    .option("tempdir", "s3://data-lake-processed-xxxx/temp/") \
    .option("dbtable", "sales.customer_metrics") \
    .option("user", redshift_user) \
    .option("password", redshift_password) \
    .option("aws_iam_role", redshift_iam_role) \
    .load()

# Databricks to Redshift
df.write \
    .format("com.databricks.spark.redshift") \
    .option("url", jdbc_url) \
    .option("tempdir", "s3://data-lake-processed-xxxx/temp/") \
    .option("dbtable", "analytics.customer_360") \
    .option("user", redshift_user) \
    .option("password", redshift_password) \
    .option("aws_iam_role", redshift_iam_role) \
    .mode("overwrite") \
    .save()
```

### 4.2 Redshift External Schema for Delta Tables

Configure Redshift to query Delta tables directly:

```sql
-- Run in Redshift
CREATE EXTERNAL SCHEMA delta
FROM DATA CATALOG 
DATABASE 'data_engineering' 
REGION 'us-east-1'
IAM_ROLE 'arn:aws:iam::xxxx:role/redshift-spectrum-role';
```

## 5. Monitoring & Alerting

### 5.1 CloudWatch Dashboards

Create CloudWatch dashboards for monitoring AWS services:

```bash
aws cloudwatch put-dashboard \
    --dashboard-name DataEngineeringDashboard \
    --dashboard-body file://dashboard-body.json
```

Dashboard body example:

```json
{
  "widgets": [
    {
      "type": "metric",
      "x": 0,
      "y": 0,
      "width": 12,
      "height": 6,
      "properties": {
        "metrics": [
          [ "AWS/Kinesis", "IncomingRecords", "StreamName", "customer-events-stream" ],
          [ ".", "GetRecords.IteratorAgeMilliseconds", ".", "." ]
        ],
        "view": "timeSeries",
        "stacked": false,
        "region": "us-east-1",
        "title": "Kinesis Metrics",
        "period": 300
      }
    }
  ]
}
```

### 5.2 Databricks Metrics Collection

Configure Databricks Metrics Collection for observability:

```python
# In a Databricks notebook

from databricks.sdk import MetricsClient

# Initialize metrics client
metrics_client = MetricsClient()

# Create a metric
metrics_client.create_metrics(
    name="data_quality_score",
    description="Overall data quality score for the pipeline",
    namespace="data_engineering"
)

# Log a metric value
metrics_client.log_metric(
    key="data_quality_score",
    value=98.5,
    namespace="data_engineering",
    dimensions={"pipeline": "customer_data", "stage": "silver"}
)
```

## 6. CI/CD for Data Pipelines

Configure CI/CD using Databricks Repos and AWS CodePipeline:

```yaml
# buildspec.yml for AWS CodeBuild

version: 0.2

phases:
  install:
    runtime-versions:
      python: 3.9
    commands:
      - pip install databricks-cli pytest pytest-cov

  pre_build:
    commands:
      - echo "Configuring Databricks CLI..."
      - echo "[DEFAULT]" > ~/.databrickscfg
      - echo "host = $DATABRICKS_HOST" >> ~/.databrickscfg
      - echo "token = $DATABRICKS_TOKEN" >> ~/.databrickscfg

  build:
    commands:
      - echo "Running tests..."
      - pytest tests/ --cov=src/
      - echo "Deploying to Databricks..."
      - databricks workspace import_dir src/ /Repos/Production/data-engineering --overwrite

  post_build:
    commands:
      - echo "Running the deployment validation..."
      - databricks jobs run-now --job-id $VALIDATION_JOB_ID
```

## 7. Data Mesh Implementation

Configure Unity Catalog for data mesh architecture:

```sql
-- Create domain-based catalogs
CREATE CATALOG IF NOT EXISTS customer_domain;
CREATE CATALOG IF NOT EXISTS product_domain;
CREATE CATALOG IF NOT EXISTS operations_domain;

-- Set up permissions for domain teams
GRANT USAGE, CREATE ON CATALOG customer_domain TO customer_team;
GRANT USAGE, CREATE ON CATALOG product_domain TO product_team;
GRANT USAGE, CREATE ON CATALOG operations_domain TO operations_team;

-- Create shared schemas for cross-domain access
CREATE SCHEMA IF NOT EXISTS customer_domain.public;
GRANT USAGE ON SCHEMA customer_domain.public TO product_team, operations_team;
```

## 8. Operational Procedures

### 8.1 Data Pipeline Runbook

```markdown
# Data Pipeline Runbook

## Standard Operations

1. **Pipeline Monitoring**
   - Check Databricks Workflow status: https://xyz.cloud.databricks.com/?o=1234567890#/jobs
   - Verify CloudWatch metrics for Kinesis: https://console.aws.amazon.com/cloudwatch/

2. **Handling Pipeline Failures**
   - Check logs in Databricks Workflow
   - Verify data quality metrics
   - Restart failed job if applicable

3. **Data Quality Issues**
   - Investigate quality alerts from SNS
   - Run data quality notebook manually
   - Backfill data if necessary

## Disaster Recovery

1. **Databricks Workspace Failure**
   - Switch to secondary workspace
   - Update DNS records
   - Run disaster recovery workflow

2. **AWS Service Disruption**
   - Follow AWS contingency plan
   - Switch to alternate region if necessary
```

This comprehensive guide provides all the necessary configurations to implement the modern data engineering architecture on AWS using Databricks. The steps cover infrastructure setup, data ingestion, processing, storage, quality monitoring, and integration between services for a robust data platform.
