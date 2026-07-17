from pyspark.sql import SparkSession
from pyspark.sql.functions import col, size, when, array_contains

spark = SparkSession.builder \
    .appName("TeslaDataCleaner") \
    .config("spark.hadoop.fs.s3a.endpoint", "http://minio:9000") \
    .config("spark.hadoop.fs.s3a.access.key", "minioadmin") \
    .config("spark.hadoop.fs.s3a.secret.key", "minioadmin") \
    .config("spark.hadoop.fs.s3a.path.style.access", "true") \
    .getOrCreate()

# 读取帧标注
df = spark.read.parquet("s3a://tesla-lake/frame_annotations/")

# 质量过滤规则
clean_df = df.filter(
    (col("blur_score") > 100) &                         # 清晰度
    (size(col("objects")) > 2) &                        # 至少检测到 2 个目标
    (~array_contains(col("global_tags"), "低质量"))     # 无低质标签
)

# 保存清洗后的数据
clean_df.write.mode("overwrite").parquet("s3a://tesla-lake/filtered_annotations/")

# 生成视频级统计
video_stats = clean_df.groupBy("video_id").agg(
    {"*": "count", "objects": "avg"}
)
video_stats.write.mode("overwrite").parquet("s3a://tesla-lake/video_stats/")

spark.stop()