from .file_handler import FileHandler
from services.database import Neo4jDriver
from typing import Dict, List, Set
import os


class SchemaCache:
    def __init__(self, driver):
        self.driver = driver
        self.file_handler = FileHandler()
        self.cache_file = "schema_cache.json"

    def get_schema(self) -> Dict:
        """Get current schema (prefer cached version)"""
        if not os.path.exists(self.cache_file):
            return self.refresh_schema()

        try:
            cached = self.file_handler.load_json(self.cache_file)
            if cached:
                return cached
        except:
            pass

        return self.refresh_schema()

    def refresh_schema(self) -> Dict:
        """Get complete schema information from Neo4j"""
        schema = {
            "nodes": [],
            "relationships": [],
            "properties": {},
            "relationship_properties": {}
        }

        try:
            # Get all node labels
            schema["nodes"] = [r["label"] for r in self._safe_query("CALL db.labels()")]

            # Get all relationship types
            schema["relationships"] = [r["relationshipType"] for r in
                                     self._safe_query("CALL db.relationshipTypes()")]

            # Get node properties
            for label in schema["nodes"]:
                props = self._get_all_properties(label)
                schema["properties"][label] = list(props)

            # Get relationship properties
            for rel_type in schema["relationships"]:
                props = self._get_relationship_properties(rel_type)
                schema["relationship_properties"][rel_type] = props

            self.file_handler.save_json(self.cache_file, schema)
            return schema

        except Exception as e:
            cached = self.file_handler.load_json(self.cache_file)
            if cached:
                print(f"Using cached schema (Neo4j error: {e})")
                return cached
            raise

    def _safe_query(self, query):
        """Execute query safely"""
        with self.driver.session(bookmarks=None) as session:
            return session.run(query).data()

    def _get_all_properties(self, label: str) -> Set[str]:
        """Get all properties for a node label"""
        query = f"""
        MATCH (n:`{label}`)
        WITH DISTINCT keys(n) AS keys
        UNWIND keys AS key
        RETURN collect(DISTINCT key) AS properties
        """
        try:
            result = self._safe_query(query)
            return set(result[0]["properties"]) if result else {"name"}
        except:
            return {"name"}

    def _get_relationship_properties(self, rel_type: str) -> List[str]:
        """Get properties for a relationship type"""
        query = f"""
        MATCH ()-[r:`{rel_type}`]->()
        WITH DISTINCT keys(r) AS keys
        UNWIND keys AS key
        RETURN collect(DISTINCT key) AS props
        """
        try:
            result = self._safe_query(query)
            return result[0]["props"] if result else []
        except:
            return []