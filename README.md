# AWS Databricks Modern Data Engineering Architecture

This repository contains code and configuration for implementing a modern data engineering architecture on AWS using Databricks. The implementation follows AWS best practices for data engineering and incorporates Databricks for powerful data processing capabilities.

![Architecture Diagram](images/architecture-diagram.png)

## Architecture Overview

This architecture implements an end-to-end data pipeline with:

- Data ingestion from multiple sources (batch and streaming)
- Processing and transformation using Databricks and Delta Lake
- Data quality validation
- Data storage in a medallion architecture (bronze, silver, gold)
- Real-time analytics capabilities
- Integration with BI tools

### Components

- **AWS Services**: S3, Kinesis, Glue, DMS, Redshift, EventBridge, Step Functions
- **Databricks**: Workspace, Clusters, Delta Lake, Structured Streaming, MLflow, Unity Catalog

## Repository Structure

```
├── terraform/                  # Infrastructure as Code
│   ├── main.tf                 # Main Terraform configuration
│   ├── variables.tf            # Terraform variables
│   └── outputs.tf              # Terraform outputs
├── databricks/                 # Databricks notebooks and configurations
│   ├── notebooks/              # Databricks notebooks
│   │   ├── ingestion/          # Data ingestion notebooks
│   │   ├── processing/         # Data processing notebooks
│   │   ├── quality/            # Data quality notebooks
│   │   └── serving/            # Data serving notebooks
│   ├── workflows/              # Databricks workflow configurations
│   └── sql/                    # SQL queries for Databricks SQL
├── streaming/                  # Real-time streaming code
│   ├── kinesis_producer.py     # Sample Kinesis producer
│   └── kinesis_consumer.py     # Sample Kinesis consumer
├── config/                     # Configuration files
│   ├── cluster-policies/       # Databricks cluster policies
│   └── unity-catalog/          # Unity Catalog setup scripts
├── scripts/                    # Utility scripts
│   ├── setup.sh                # Setup script
│   └── deploy.sh               # Deployment script
├── docs/                       # Documentation
│   ├── architecture.md         # Architecture details
│   └── implementation.md       # Implementation guide
└── images/                     # Architecture diagrams and images
```

## Getting Started

### Prerequisites

- AWS Account with appropriate permissions
- Databricks account with AWS integration capability
- Terraform v1.0+
- AWS CLI v2+
- Python 3.8+

### Installation

1. Clone the repository

```bash
git clone https://github.com/yourusername/aws-databricks-architecture.git
cd aws-databricks-architecture
```

2. Set up environment variables

```bash
export AWS_ACCESS_KEY_ID="your-access-key"
export AWS_SECRET_ACCESS_KEY="your-secret-key"
export DATABRICKS_HOST="your-databricks-workspace-url"
export DATABRICKS_TOKEN="your-databricks-token"
```

3. Deploy the infrastructure

```bash
cd terraform
terraform init
terraform plan
terraform apply
```

4. Import Databricks notebooks

```bash
cd ../scripts
./deploy.sh
```

## Usage Examples

### Setting up Delta Live Tables Pipeline

```python
from pyspark.sql import functions as F

# Define a Delta Live Tables pipeline
@dlt.table(
  name="customers_bronze",
  comment="Raw customer data from source systems",
  table_properties={
    "quality": "bronze",
    "pipelines.autoOptimize.managed": "true"
  }
)
def customers_bronze():
  return (
    spark.readStream.format("cloudFiles")
      .option("cloudFiles.format", "csv")
      .option("cloudFiles.schemaLocation", f"{raw_zone_path}/customers/_schemas")
      .load(f"{raw_zone_path}/customers/")
  )

@dlt.table(
  name="customers_silver",
  comment="Cleaned and validated customer data",
  table_properties={
    "quality": "silver",
    "pipelines.autoOptimize.managed": "true"
  }
)
def customers_silver():
  return (
    dlt.read("customers_bronze")
      .withColumn("email", F.lower(F.col("email")))
      .withColumn("days_since_activity", F.datediff(F.current_date(), F.col("last_activity")))
      .withColumn("customer_segment", F.when(F.col("days_since_activity") <= 30, "active")
                                     .when(F.col("days_since_activity") <= 90, "recent")
                                     .otherwise("inactive"))
  )
```

### Real-time Processing with Structured Streaming

```python
# Read streaming data from Kinesis
kinesis_stream = spark.readStream \
    .format("kinesis") \
    .option("streamName", "data-engineering-stream") \
    .option("region", "us-east-1") \
    .option("initialPosition", "latest") \
    .option("awsUseInstanceProfile", "true") \
    .load()

# Process the stream
processed_stream = kinesis_stream \
    .selectExpr("cast(data as STRING) as json_data") \
    .select(F.from_json("json_data", event_schema).alias("event")) \
    .select("event.*") \
    .withColumn("processing_time", F.current_timestamp())

# Write to Delta table
query = processed_stream.writeStream \
    .format("delta") \
    .outputMode("append") \
    .option("checkpointLocation", checkpoint_path) \
    .start(output_path)
```

## Infrastructure as Code Examples

### S3 Data Lake Setup

```terraform
# S3 Buckets for Data Lake zones
resource "aws_s3_bucket" "data_lake" {
  count  = 3
  bucket = "data-lake-${var.data_zones[count.index]}-${random_string.suffix.result}"
  
  tags = {
    Name = "Data Lake - ${var.data_zones[count.index]}"
    Zone = var.data_zones[count.index]
  }
}

# S3 Bucket Lifecycle Policies
resource "aws_s3_bucket_lifecycle_configuration" "data_lake_lifecycle" {
  count  = 3
  bucket = aws_s3_bucket.data_lake[count.index].id

  rule {
    id     = "transition-to-standard-ia"
    status = "Enabled"

    transition {
      days          = var.transition_days[count.index]
      storage_class = "STANDARD_IA"
    }
  }
}
```

### Databricks Cluster Configuration

```terraform
resource "databricks_cluster" "etl_cluster" {
  cluster_name            = "ETL-Cluster"
  spark_version           = "10.4.x-scala2.12"
  node_type_id            = "i3.xlarge"
  autotermination_minutes = 20
  
  autoscale {
    min_workers = 2
    max_workers = 8
  }
  
  spark_conf = {
    "spark.databricks.delta.optimizeWrite" = "true",
    "spark.databricks.io.cache.enabled"    = "true"
  }
}
```

## Configuration Guide

1. **IAM Roles**: Configure cross-account IAM roles for Databricks to access AWS resources
2. **VPC Peering**: Set up VPC peering between Databricks and your AWS VPC
3. **S3 Access**: Configure S3 bucket policies for Databricks access
4. **Kinesis Integration**: Set up Databricks to read from Kinesis streams
5. **Redshift Connection**: Configure Redshift connection for data warehousing

See [Implementation Guide](docs/implementation.md) for detailed steps.

## Security Considerations

- IAM roles with least privilege access
- VPC network security with proper security groups
- Data encryption at rest and in transit
- Column-level security with Unity Catalog
- Access control with Databricks workspace permissions

## Monitoring and Observability

- CloudWatch dashboards for AWS services
- Databricks metrics for cluster and job performance
- Data quality monitoring with alerts
- Pipeline status monitoring

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- AWS for their modern data engineering reference architectures
- Databricks for their platform and documentation

## Contact

If you have any questions or feedback, please open an issue in this repository.
