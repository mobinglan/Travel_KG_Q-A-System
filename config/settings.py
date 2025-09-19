import os
from pathlib import Path


class Settings:
    # 路径配置
    OLLAMA_MODELS_DIR = r"D:/OllamaSetup/.ollama"
    LTP_MODEL_PATH = "D:/Anaconda/LTP/small"  # LTP模型路径

    # 设置环境变量（关键配置）
    os.environ["OLLAMA_MODELS"] = OLLAMA_MODELS_DIR

    # Neo4j配置
    NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
    NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "mo301329")

    # 领域实体配置
    DOMAIN_ENTITIES = ["attraction", "hotel", "restaurant"]


settings = Settings()