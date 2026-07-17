"""
Tesla Vision Platform - 元数据聚合任务

从 frame_annotations 聚合生成视频级统计信息，
写入 videos_meta 表供前端查询。
"""

from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    col, count, avg, min, max, collect_set, collect_list,
    size, explode, struct, array_distinct, lit
)
from pyspark.sql.types import StructType, StructField, StringType, FloatType, IntegerType

# ============================================================
# Spark 会话初始化
# ============================================================
spark = SparkSession.builder \
    .appName("TeslaMetadataAggregator") \
    .config("spark.hadoop.fs.s3a.endpoint", "http://minio:9000") \
    .config("spark.hadoop.fs.s3a.access.key", "minioadmin") \
    .config("spark.hadoop.fs.s3a.secret.key", "minioadmin") \
    .config("spark.hadoop.fs.s3a.path.style.access", "true") \
    .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem") \
    .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension") \
    .config("spark.sql.catalog.spark_catalog", "org.apache.spark.sql.delta.catalog.DeltaCatalog") \
    .getOrCreate()

# ============================================================
# 读取原始标注数据
# ============================================================
ANNOTATIONS_PATH = "s3a://tesla-lake/frame_annotations/"

print(f"读取帧标注数据: {ANNOTATIONS_PATH}")
df_annotations = spark.read.parquet(ANNOTATIONS_PATH)

print(f"帧标注总数: {df_annotations.count()}")
print(f"视频数: {df_annotations.select('video_id').distinct().count()}")

# ============================================================
# 视频级聚合
# ============================================================
video_stats = df_annotations.groupBy("video_id").agg(
    count("*").alias("total_frames"),
    avg("quality_score").alias("avg_quality_score"),
    min("quality_score").alias("min_quality_score"),
    max("quality_score").alias("max_quality_score"),
    avg("blur_score").alias("avg_blur_score"),
    # 汇总所有全局标签
    collect_set("global_tags").alias("all_global_tags"),
    # 汇总所有检测到的目标类型
    collect_set("objects.class_name").alias("all_object_classes"),
)

# 压平标签列表（去除嵌套）
video_stats = video_stats.withColumn(
    "all_global_tags", array_distinct("all_global_tags")
)

print("===== 视频级统计 =====")
video_stats.show(truncate=False)

# ============================================================
# 保存视频元数据到 Parquet
# ============================================================
VIDEO_META_PATH = "s3a://tesla-lake/videos_meta/"
video_stats.write.mode("overwrite").parquet(VIDEO_META_PATH)
print(f"视频元数据已保存: {VIDEO_META_PATH}")

# ============================================================
# 场景分布统计
# ============================================================
# 统计每种全局标签的出现频率
tag_stats = video_stats.select(
    explode("all_global_tags").alias("tag")
).groupBy("tag").agg(
    count("*").alias("video_count")
).orderBy(col("video_count").desc())

print("===== 场景标签分布 (Top 20) =====")
tag_stats.show(20, truncate=False)

# ============================================================
# 目标检测统计
# ============================================================
obj_stats = video_stats.select(
    explode("all_object_classes").alias("object_class")
).groupBy("object_class").agg(
    count("*").alias("video_count")
).orderBy(col("video_count").desc())

print("===== 目标类别分布 =====")
obj_stats.show(truncate=False)

# ============================================================
# 质量分布
# ============================================================
quality_distribution = video_stats.select("avg_quality_score") \
    .withColumn("quality_level",
        when(col("avg_quality_score") >= 80, "优秀")
        .when(col("avg_quality_score") >= 60, "良好")
        .when(col("avg_quality_score") >= 40, "一般")
        .otherwise("较差")
    ).groupBy("quality_level").agg(
        count("*").alias("count"),
        (count("*") / video_stats.count() * 100).alias("percentage")
    )

print("===== 质量分布 =====")
quality_distribution.show()

# ============================================================
# 关闭 Spark 会话
# ============================================================
spark.stop()
print("元数据聚合任务完成")
