from neo4j import GraphDatabase
from config.settings import settings
from typing import  Any

class Neo4jDriver:
    def __init__(self):
        self.driver = GraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
        )

    def execute_query(self, cypher: str) -> Any:
        """Execute Cypher query and return results"""
        try:
            with self.neo4j_driver.session() as session:
                result = session.run(cypher)
                return [dict(record) for record in result]
        except Exception as e:
            print(f"Error executing Cypher: {e}")
            raise

    def close(self):
        self.driver.close()