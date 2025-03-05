# Databricks notebook source
# MAGIC %md
# MAGIC # Delta Live Tables Pipeline for Modern Data Engineering
# MAGIC 
# MAGIC This notebook defines a complete Delta Live Tables pipeline for the modern data engineering architecture:
# MAGIC 
# MAGIC 1. Bronze Layer: Raw data ingestion
# MAGIC 2. Silver Layer: Cleansed and validated data
# MAGIC 3. Gold Layer: Business-level aggregates
# MAGIC 4. Data Quality: Expectations and metrics
# MAGIC 
# MAGIC Architecture components:
# MAGIC - Data Source: Kinesis streaming data, S3 files from AWS DMS
# MAGIC - Processing: Delta Live Tables with data quality validation
# MAGIC - Storage: Delta Lake in medallion architecture

# COMMAND ----------

import dlt
from pyspark.sql import functions as F
from pyspark.sql.types import *

# Configuration for data zones
raw_zone_path = "s3://data-lake-raw-abcd1234/"
processed_zone_path = "s3://data-lake-processed-abcd1234/"
curated_zone_path = "s3://data-lake-curated-abcd1234/"

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Bronze Layer Tables
# MAGIC 
# MAGIC The bronze layer contains raw data ingested from source systems.

# COMMAND ----------

# MAGIC %md
# MAGIC ### 1.1 Customer Raw Data

# COMMAND ----------

# Define schema for customer data
customer_schema = StructType([
    StructField("customer_id", StringType(), False),
    StructField("name", StringType(), True),
    StructField("email", StringType(), True),
    StructField("phone", StringType(), True),
    StructField("address", StringType(), True),
    StructField("city", StringType(), True),
    StructField("state", StringType(), True),
    StructField("zip", StringType(), True),
    StructField("signup_date", TimestampType(), True),
    StructField("last_activity", TimestampType(), True)
])

# Bronze table for customer data from S3/DMS
@dlt.table(
    name="customers_bronze",
    comment="Raw customer data ingested from source systems",
    schema=customer_schema,
    table_properties={
        "quality": "bronze",
        "pipelines.autoOptimize.managed": "true"
    }
)
def customers_bronze():
    return (
        spark.readStream.format("cloudFiles")
            .option("cloudFiles.format", "csv")
            .option("cloudFiles.schemaLocation", f"{raw_zone_path}/_schemas/customers")
            .option("header", "true")
            .load(f"{raw_zone_path}/customers/")
    )

# COMMAND ----------

# MAGIC %md
# MAGIC ### 1.2 Order Raw Data from Kinesis

# COMMAND ----------

# Define schema for order events from Kinesis
order_schema = StructType([
    StructField("order_id", StringType(), False),
    StructField("customer_id", StringType(), True),
    StructField("order_date", TimestampType(), True),
    StructField("status", StringType(), True),
    StructField("items", ArrayType(
        StructType([
            StructField("product_id", StringType(), True),
            StructField("quantity", IntegerType(), True),
            StructField("price", DoubleType(), True)
        ])
    ), True),
    StructField("total_amount", DoubleType(), True),
    StructField("payment_method", StringType(), True),
    StructField("shipping_address", StringType(), True),
    StructField("shipping_city", StringType(), True),
    StructField("shipping_state", StringType(), True),
    StructField("shipping_zip", StringType(), True)
])

# Bronze table for order data from Kinesis
@dlt.table(
    name="orders_bronze",
    comment="Raw order data from Kinesis stream",
    table_properties={
        "quality": "bronze",
        "pipelines.autoOptimize.managed": "true"
    }
)
def orders_bronze():
    return (
        # In production, use the Kinesis reader
        # spark.readStream.format("kinesis")
        #     .option("streamName", "customer-events-stream")
        #     .option("region", "us-east-1")
        #     .option("initialPosition", "latest")
        #     .option("awsUseInstanceProfile", "true")
        #     .load()
        #     .selectExpr("cast(data as STRING) as json_data")
        #     .select(F.from_json("json_data", order_schema).alias("order"))
        #     .select("order.*")
        
        # For testing with local source
        spark.readStream.format("cloudFiles")
            .option("cloudFiles.format", "json")
            .option("cloudFiles.schemaLocation", f"{raw_zone_path}/_schemas/orders")
            .load(f"{raw_zone_path}/orders/")
    )

# COMMAND ----------

# MAGIC %md
# MAGIC ### 1.3 Product Catalog Raw Data

# COMMAND ----------

# Define schema for product catalog
product_schema = StructType([
    StructField("product_id", StringType(), False),
    StructField("name", StringType(), True),
    StructField("description", StringType(), True),
    StructField("category", StringType(), True),
    StructField("subcategory", StringType(), True),
    StructField("price", DoubleType(), True),
    StructField("cost", DoubleType(), True),
    StructField("stock_quantity", IntegerType(), True),
    StructField("supplier_id", StringType(), True),
    StructField("created_date", TimestampType(), True),
    StructField("modified_date", TimestampType(), True)
])

# Bronze table for product catalog
@dlt.table(
    name="products_bronze",
    comment="Raw product catalog data",
    schema=product_schema,
    table_properties={
        "quality": "bronze",
        "pipelines.autoOptimize.managed": "true"
    }
)
def products_bronze():
    return (
        spark.readStream.format("cloudFiles")
            .option("cloudFiles.format", "json")
            .option("cloudFiles.schemaLocation", f"{raw_zone_path}/_schemas/products")
            .load(f"{raw_zone_path}/products/")
    )

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Silver Layer Tables
# MAGIC 
# MAGIC The silver layer contains cleansed, validated, and standardized data.

# COMMAND ----------

# MAGIC %md
# MAGIC ### 2.1 Customer Silver Data

# COMMAND ----------

# Define expectations for customer data
@dlt.table(
    name="customers_silver",
    comment="Cleansed and validated customer data",
    table_properties={
        "quality": "silver",
        "pipelines.autoOptimize.managed": "true",
        "delta.columnMapping.mode": "name"
    }
)
@dlt.expect_all({
    "valid_email": "email IS NULL OR email RLIKE '^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,6}$'",
    "valid_phone": "phone IS NULL OR phone RLIKE '^[0-9]{10}$'",
    "valid_zip": "zip IS NULL OR zip RLIKE '^[0-9]{5}([-][0-9]{4})?$'"
})
def customers_silver():
    return (
        dlt.read("customers_bronze")
            .withColumn("email", F.lower(F.col("email")))
            .withColumn("customer_id", F.trim(F.col("customer_id")))
            .withColumn("name", F.initcap(F.col("name")))
            .withColumn("days_since_activity", F.datediff(F.current_date(), F.col("last_activity")))
            .withColumn("customer_segment", 
                         F.when(F.col("days_since_activity") <= 30, "active")
                          .when(F.col("days_since_activity") <= 90, "recent")
                          .otherwise("inactive"))
            .withColumn("full_address", 
                         F.concat_ws(", ", 
                                     F.col("address"), 
                                     F.col("city"), 
                                     F.col("state"), 
                                     F.col("zip")))
            .withColumn("processing_time", F.current_timestamp())
    )

# COMMAND ----------

# MAGIC %md
# MAGIC ### 2.2 Order Silver Data

# COMMAND ----------

# Define expectations for order data
@dlt.table(
    name="orders_silver",
    comment="Cleansed and validated order data",
    table_properties={
        "quality": "silver",
        "pipelines.autoOptimize.managed": "true",
        "delta.columnMapping.mode": "name"
    }
)
@dlt.expect_all({
    "valid_order_id": "order_id IS NOT NULL",
    "valid_amount": "total_amount > 0",
    "valid_date": "order_date IS NOT NULL"
})
def orders_silver():
    # Explode the items array to get order details
    orders_with_items = (
        dlt.read("orders_bronze")
            .withColumn("order_month", F.date_format(F.col("order_date"), "yyyy-MM"))
            .withColumn("order_date_only", F.to_date(F.col("order_date")))
            .withColumn("processing_time", F.current_timestamp())
            .filter(F.col("order_id").isNotNull())
            .withColumn("shipping_address_full", 
                        F.concat_ws(", ", 
                                    F.col("shipping_address"), 
                                    F.col("shipping_city"), 
                                    F.col("shipping_state"), 
                                    F.col("shipping_zip")))
    )
    
    return orders_with_items

# COMMAND ----------

# Extract order items into a separate table
@dlt.table(
    name="order_items_silver",
    comment="Order items detail data",
    table_properties={
        "quality": "silver",
        "pipelines.autoOptimize.managed": "true"
    }
)
def order_items_silver():
    return (
        dlt.read("orders_bronze")
            .filter(F.col("order_id").isNotNull())
            .filter(F.size(F.col("items")) > 0)
            .select(
                F.col("order_id"),
                F.col("order_date"),
                F.explode("items").alias("item")
            )
            .select(
                "order_id",
                "order_date",
                F.col("item.product_id").alias("product_id"),
                F.col("item.quantity").alias("quantity"),
                F.col("item.price").alias("unit_price"),
                (F.col("item.quantity") * F.col("item.price")).alias("item_total")
            )
            .withColumn("processing_time", F.current_timestamp())
    )

# COMMAND ----------

# MAGIC %md
# MAGIC ### 2.3 Product Silver Data

# COMMAND ----------

@dlt.table(
    name="products_silver",
    comment="Cleansed and validated product data",
    table_properties={
        "quality": "silver",
        "pipelines.autoOptimize.managed": "true"
    }
)
@dlt.expect_all({
    "valid_product_id": "product_id IS NOT NULL",
    "valid_price": "price > 0",
    "valid_category": "category IS NOT NULL"
})
def products_silver():
    return (
        dlt.read("products_bronze")
            .withColumn("margin", F.round(F.col("price") - F.col("cost"), 2))
            .withColumn("margin_percent", F.round((F.col("price") - F.col("cost")) / F.col("price") * 100, 2))
            .withColumn("is_low_stock", F.col("stock_quantity") < 10)
            .withColumn("processing_time", F.current_timestamp())
    )

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Gold Layer Tables
# MAGIC 
# MAGIC The gold layer contains business-level aggregates and analytics-ready data.

# COMMAND ----------

# MAGIC %md
# MAGIC ### 3.1 Customer 360 View

# COMMAND ----------

@dlt.table(
    name="customer_360",
    comment="Customer 360 view with order history",
    table_properties={
        "quality": "gold",
        "pipelines.autoOptimize.managed": "true"
    }
)
def customer_360():
    # Get customer data
    customers = dlt.read("customers_silver")
    
    # Get order summary per customer
    orders_summary = (
        dlt.read("orders_silver")
            .groupBy("customer_id")
            .agg(
                F.count("order_id").alias("total_orders"),
                F.sum("total_amount").alias("total_spend"),
                F.max("order_date").alias("last_order_date"),
                F.min("order_date").alias("first_order_date"),
                F.avg("total_amount").alias("avg_order_value")
            )
    )
    
    # Join customer data with order summary
    return (
        customers.join(
            orders_summary,
            "customer_id",
            "left"
        )
        .withColumn("total_orders", F.coalesce(F.col("total_orders"), F.lit(0)))
        .withColumn("total_spend", F.coalesce(F.col("total_spend"), F.lit(0.0)))
        .withColumn("days_since_last_order", 
                    F.when(F.col("last_order_date").isNotNull(), 
                           F.datediff(F.current_date(), F.col("last_order_date")))
                    .otherwise(None))
        .withColumn("customer_lifetime_days",
                    F.when(F.col("first_order_date").isNotNull(),
                           F.datediff(F.current_date(), F.col("first_order_date")))
                    .otherwise(F.datediff(F.current_date(), F.col("signup_date"))))
        .withColumn("is_repeat_customer", F.col("total_orders") > 1)
        .withColumn("compute_date", F.current_date())
    )

# COMMAND ----------

# MAGIC %md
# MAGIC ### 3.2 Product Analytics

# COMMAND ----------

@dlt.table(
    name="product_analytics",
    comment="Product performance analytics",
    table_properties={
        "quality": "gold",
        "pipelines.autoOptimize.managed": "true"
    }
)
def product_