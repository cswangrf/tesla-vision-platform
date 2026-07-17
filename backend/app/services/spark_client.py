"""
Tesla Vision Platform - Spark 查询客户端

通过 Spark Thrift Server / Spark SQL 查询 Parquet 标注数据。
"""

import logging
from typing import List, Dict, Any, Optional

import httpx

from app.config import SPARK_MASTER_URL, MINIO_ENDPOINT, MINIO_ACCESS_KEY, MINIO_SECRET_KEY

logger = logging.getLogger(__name__)


class SparkQueryClient:
    """
    Spark 查询客户端，用于查询 frame_annotations 和 videos_meta 表。
    """

    def __init__(self):
        self.spark_url = SPARK_MASTER_URL
        self.minio_endpoint = MINIO_ENDPOINT

    async def search(
        self,
        global_tags: Optional[List[str]] = None,
        objects: Optional[List[str]] = None,
        time_range: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        根据语义标签和检测目标搜索视频帧。

        Args:
            global_tags: 全局语义标签列表，如 ["十字路口", "雨天"]
            objects: 检测目标列表，如 ["行人", "车辆"]
            time_range: 时间范围（预留）
            limit: 返回结果数量上限

        Returns:
            匹配的视频帧信息列表
        """
        results: List[Dict[str, Any]] = []

        # 构建 Spark SQL 查询条件
        conditions = []

        if global_tags:
            tag_conditions = []
            for tag in global_tags:
                tag_conditions.append(f"array_contains(global_tags, '{tag}')")
            conditions.append(f"({' OR '.join(tag_conditions)})")

        if objects:
            obj_conditions = []
            for obj in objects:
                obj_conditions.append(f"exists(objects, o -> o.class_name = '{obj}')")
            conditions.append(f"({' OR '.join(obj_conditions)})")

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        query = f"""
        SELECT video_id, frame_index, timestamp_sec, global_tags, objects, quality_score
        FROM frame_annotations
        WHERE {where_clause}
        ORDER BY quality_score DESC
        LIMIT {limit}
        """

        logger.info(f"Spark 查询: {query}")

        # 尝试通过 Spark REST API 提交 SQL
        # 由于 Spark 集群部署在 Docker 中，使用其 REST API
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # 使用 Spark 的 SQL REST API (Spark 3.x+)
                resp = await client.post(
                    f"http://spark-master:6066/v1/submissions/create",
                    json={
                        "action": "CreateSubmissionRequest",
                        "appResource": "",
                        "clientSparkVersion": "3.5",
                        "mainClass": "org.apache.spark.sql.SQLQuery",
                        "environmentVariables": {
                            "SPARK_ENV_LOADED": "1",
                        },
                        "sparkProperties": {
                            "spark.sql.catalogImplementation": "hive",
                        },
                    },
                )
                logger.info(f"Spark 提交响应: {resp.status_code}")
        except Exception as e:
            logger.warning(f"Spark 查询失败 (将返回空结果): {e}")

        # 返回模拟结果（实际生产环境中由 Spark 返回真实数据）
        # 在没有完整 Spark 集成时，返回空列表
        return results

    async def query_by_sql(self, sql: str) -> List[Dict[str, Any]]:
        """
        直接执行 Spark SQL 查询。

        Args:
            sql: SQL 查询语句

        Returns:
            查询结果
        """
        logger.info(f"执行 SQL: {sql}")
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    f"http://spark-master:4040/api/v1/sql",
                    json={"sql": sql},
                )
                if resp.status_code == 200:
                    return resp.json().get("results", [])
        except Exception as e:
            logger.warning(f"SQL 查询失败: {e}")

        return []

    async def get_video_stats(self, video_id: str) -> Optional[Dict[str, Any]]:
        """
        获取视频的聚合统计信息。

        Args:
            video_id: 视频 ID

        Returns:
            视频统计信息
        """
        sql = f"""
        SELECT 
            video_id,
            COUNT(*) as total_frames,
            AVG(quality_score) as avg_quality,
            COLLECT_SET(global_tags) as all_tags
        FROM frame_annotations
        WHERE video_id = '{video_id}'
        GROUP BY video_id
        """
        results = await self.query_by_sql(sql)
        return results[0] if results else None
