import json
from datetime import datetime
import traceback
import ollama
from data_manager.file_handler import FileHandler
from data_manager.schema_cache import SchemaCache
from typing import Dict, List, Optional, Any
from services.database import Neo4jDriver


class LocalCypherGenerator:
    def __init__(self):
        self.neo4j_driver = Neo4jDriver()
        self.schema_cache = SchemaCache(self.neo4j_driver.driver)
        self.schema = self.schema_cache.refresh_schema()
        self._setup_prompt_template()
        self.file_handler = FileHandler()
        self.template_file = "cypher_templates.json"
        self.templates = self._load_templates()

    def _load_templates(self) -> Dict:
        """安全加载模板数据，确保返回字典"""
        data = self.file_handler.load_json(self.template_file)

        # 处理可能的格式问题
        if data is None:
            return {}
        if isinstance(data, list):
            # 将列表格式转换为字典格式
            return {f"query_{i}": {"cypher": item} for i, item in enumerate(data)}
        return data

    def save_template(self, question: str, cypher: str, validated: bool = False) -> None:
        """保存模板（增加验证状态）"""
        if not isinstance(self.templates, dict):
            self.templates = {}

        self.templates[question] = {
            "cypher": cypher,
            "validated": validated,
            "usage_count": 1,
            "last_used": datetime.now().isoformat()
        }
        self._save_templates()


    # 在 LocalCypherGenerator 中添加
    def refresh_schema(self):
        self.schema = self.schema_cache.refresh_schema()
        self._setup_prompt_template()

    def _setup_prompt_template(self):
        """Define prompt template"""
        # 确保使用最新schema
        self.schema = self.schema_cache.refresh_schema()

        self.prompt = f"""
        You are a professional Neo4j query generator. Convert questions to Cypher queries following these rules:

        Knowledge Graph Structure:
        - Node Types: {', '.join(self.schema['nodes'])}
        - Relationship Types: {', '.join(self.schema['relationships'])}

        Node Properties:
        {json.dumps(self.schema['properties'], indent=2, ensure_ascii=False)}

        Relationship Properties:
        {json.dumps(self.schema['relationship_properties'], indent=2, ensure_ascii=False)}

        Conversion Rules:
        1. City names must match exactly
        2. Use >=/< for numerical comparisons
        3. Sort results by rating descending
        4. Include LIMIT 5
        5. Return ONLY the Cypher query, no additional explanation
        Example:

        # 优惠政策查询模式
        Question: [景点名称]有什么优惠政策？
        Cypher: MATCH (s:Sight) 
                WHERE s.name CONTAINS '[景点名称]'
                RETURN s.name AS name, 
                       COALESCE(s.preferential, '暂无优惠政策信息') AS preferential
                LIMIT 1
    
        # 开放时间查询模式
        Question: [景点名称]的开放时间是？
        Cypher: MATCH (s:Sight)
                WHERE s.name CONTAINS '[景点名称]'
                RETURN s.name AS name,
                       COALESCE(s.open_hours, '开放时间未收录') AS open_hours
                LIMIT 1
                
        Question: 故宫有什么优惠政策？
        Cypher: MATCH (s:Sight) 
                WHERE s.name CONTAINS '故宫'
                RETURN s.name, s.preferential
                LIMIT 1
                
        Question: 颐和园几点开门？
        Cypher: MATCH (s:Sight)
                WHERE s.name CONTAINS '颐和园'
                RETURN s.name, s.open_hours
                LIMIT 1
        Question: 我想去南宁玩，有什么推荐的景点吗？
        Cypher: MATCH (s:Sight)-[:LOCATED_IN]->(c:City {{name: '南宁'}})
                RETURN s.name AS name, s.heat AS heat
                ORDER BY heat DESC
                LIMIT 5
        Question: 推荐一下北京的比较火的4A和5A景点？
        Cypher: MATCH (s:Sight)-[:LOCATED_IN]->(c:City)
                WHERE c.name = '北京' AND s.star IN ['4A', '5A']
                RETURN s.name AS name, s.heat AS heat, s.star AS star
                ORDER BY heat DESC
                LIMIT 5
        Question: 广西的5A景点有哪些？
        Cypher: MATCH (s:Sight {{star: '5A'}})-[:LOCATED_IN]->(c:City)-[:BELONGS_TO]->(p:Province {{name: '广西'}})
                RETURN s.name AS SightName,s.star AS Star
        """

    def _validate_cypher(self, cypher: str) -> bool:
        """Basic validation of Cypher syntax"""
        required_keywords = ["MATCH", "RETURN"]
        return all(keyword in cypher for keyword in required_keywords)
    def _get_template_match(self, question: str) -> Optional[str]:
        """Check if a similar question's template exists"""
        if not isinstance(self.templates, dict):
            print(f"警告: 模板格式无效，类型为 {type(self.templates)}")
            return None

        for saved_question, template_data in self.templates.items():
            if not isinstance(template_data, dict):
                continue
            if any(keyword in question for keyword in saved_question.split()[:3]):
                return template_data.get("cypher")
        return None

    def generate_cypher(self, question: str) -> str:
        """通用查询生成方法"""
        try:
            # 1. 模板匹配
            if not isinstance(self.templates, dict):
                self.templates = self._load_templates()
            if template := self._get_template_match(question):
                return template

            # 2. 调用大模型生成查询
            response = ollama.chat(
                model='qwen2.5-coder:3b',
                messages=[{
                    'role': 'user',
                    'content': f"{self.prompt}\n问题: {question}"
                }],
                options={'temperature': 0.1}
            )
            cypher = response['message']['content'].strip()

            # 3. 基本语法验证
            if not cypher.startswith(("MATCH", "CREATE", "MERGE")):
                raise ValueError("生成的Cypher格式无效")
            return cypher

        except Exception as e:
            print(f"[ERROR] 生成查询失败: {str(e)}\n{traceback.format_exc()}")
            raise RuntimeError(f"无法生成查询: {str(e)}")
    # def generate_cypher(self, question: str) -> str:
    #     """通用查询生成方法"""
    #     try:
    #         # 1. 模板匹配（保持不变）
    #         if not isinstance(self.templates, dict):
    #             self.templates = self._load_templates()
    #         if template := self._get_template_match(question):
    #             return template
    #             # # 3. 其他情况调用大模型生成
    #             # response = ollama.chat(
    #             #     model='qwen2.5-coder:3b',
    #             #     messages=[{
    #             #         'role': 'user',
    #             #         'content': f"{self.prompt}\n问题: {question}"
    #             #     }],
    #             #     options={'temperature': 0.1}
    #             # )
    #             # cypher = response['message']['content'].strip()
    #             #
    #             # if not cypher.startswith(("MATCH", "CREATE", "MERGE")):
    #             #     raise ValueError("生成的Cypher格式无效")
    #             # return cypher
    #
    #         # 2. 自动识别查询意图
    #         if any(keyword in question for keyword in ["开放时间", "几点开门", "营业时间"]):
    #             sight_name = self._clean_question(question, ["的开放时间是", "几点开门"])
    #             return f"""
    #             MATCH (s:Sight)
    #             WHERE toLower(s.name) CONTAINS toLower('{sight_name}')
    #             RETURN s.name AS name,
    #                    s.open_hours AS open_hours,
    #                    s.phone_number AS phone_number
    #             LIMIT 1
    #             """
    #
    #         elif any(keyword in question for keyword in ["优惠", "政策", "门票"]):
    #             sight_name = self._clean_question(question, ["有什么优惠", "优惠政策"])
    #             return f"""
    #             MATCH (s:Sight)
    #             WHERE toLower(s.name) CONTAINS toLower('{sight_name}')
    #             RETURN s.name AS name,
    #                    COALESCE(s.preferential, '暂无信息') AS preferential,
    #                    s.phone_number AS phone_number
    #             LIMIT 1
    #             """
    #
    #         # 3. 城市景点推荐
    #         elif "推荐" in question and ("景点" in question or "地方" in question):
    #             # 提取城市名称
    #             city_keywords = ["北京", "上海", "广州", "深圳", "成都", "杭州", "重庆", "西安", "苏州", "武汉",
    #                              "南京", "天津", "郑州", "长沙", "东莞", "沈阳", "青岛", "合肥", "佛山"]
    #             city = next((c for c in city_keywords if c in question), None)
    #
    #             if city:
    #                 return f"""
    #                 MATCH (s:Sight)-[:LOCATED_IN]->(c:City)
    #                 WHERE c.name = '{city}'
    #                 RETURN s.name AS name,
    #                        s.heat AS heat,
    #                        s.star AS star,
    #                        s.address AS address
    #                 ORDER BY heat DESC
    #                 LIMIT 5
    #                 """
    #
    #         # 4. 默认景点推荐（全国范围）
    #         return """
    #         MATCH (s:Sight)
    #         RETURN s.name AS name,
    #                s.heat AS heat,
    #                s.star AS star,
    #                s.address AS address
    #         ORDER BY heat DESC
    #         LIMIT 5
    #         """
    #
    #     except Exception as e:
    #         print(f"[ERROR] 生成查询失败: {str(e)}")
    #         raise RuntimeError("查询生成失败")


    def _clean_question(self, question: str, remove_words: List[str]) -> str:
        """清理问题中的干扰词"""
        for word in remove_words:
            question = question.replace(word, "")
        return question.strip()

    def execute_query(self, cypher: str) -> Any:
        """执行Cypher查询并安全返回结果"""
        try:
            with self.neo4j_driver.driver.session() as session:
                result = session.run(cypher)

                # 安全处理结果（兼容节点/关系/普通值）
                records = []
                for record in result:
                    rec = {}
                    for key in record.keys():
                        value = record[key]
                        if hasattr(value, 'items'):
                            if 'start' in value and 'end' in value:  # 是关系对象
                                value = {k: v for k, v in value.items()
                                         if k not in ['start', 'end']}
                            rec[key] = value
                        if hasattr(value, '__iter__') and not isinstance(value, (str, bytes)):
                            # 处理节点和关系对象
                            rec[key] = dict(value.items()) if hasattr(value, 'items') else str(value)
                        else:
                            # 处理普通值
                            rec[key] = value
                    records.append(rec)
                return records

        except Exception as e:
            error_msg = f"查询执行失败: {str(e)}\n查询语句: {cypher}"
            raise ValueError(error_msg)

    def _save_templates(self):
        """保存模板时确保为字典格式"""
        if not isinstance(self.templates, dict):
            self.temsplates = {"converted": self.templates}
        self.file_handler.save_json(self.template_file, self.templates)

    def get_template_stats(self) -> Dict[str, int]:
        """Get template usage statistics"""
        return {
            "total_templates": len(self.templates),
            "validated_templates": sum(1 for t in self.templates.values() if t["validated"]),
            "most_used": max((t["usage_count"] for t in self.templates.values()), default=0)
        }
