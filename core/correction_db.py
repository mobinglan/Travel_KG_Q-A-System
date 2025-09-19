import json
import os
from datetime import datetime
from pathlib import Path
from typing import List, Dict


class CorrectionDB:
    def __init__(self, db_file: str = "correction_requests.json"):
        # 确保使用绝对路径
        self.db_file = str(Path(__file__).parent.parent / "data" / db_file)
        os.makedirs(Path(self.db_file).parent, exist_ok=True)

        # 如果文件不存在则创建
        if not os.path.exists(self.db_file):
            with open(self.db_file, 'w') as f:
                json.dump([], f)

    def add_request(self, question: str, generated_cypher: str, error_msg: str,
                    feedback_type: str = "system_error") -> None:
        """添加修正请求（增加反馈类型）"""
        requests = self.get_all_requests()
        requests.append({
            "question": question,
            "generated_cypher": generated_cypher,
            "error_msg": error_msg,
            "status": "pending",
            "corrected_cypher": None,
            "feedback_type": feedback_type,  # system_error/user_dissatisfied
            "timestamp": datetime.now().isoformat()
        })
        self._save_requests(requests)


    def get_all_requests(self, status: str = None) -> List[Dict]:
        """获取所有修正请求，可筛选状态"""
        with open(self.db_file, 'r') as f:
            requests = json.load(f)

        if status:
            return [r for r in requests if r["status"] == status]
        return requests

    def resolve_request(self, question: str, corrected_cypher: str) -> None:
        """解决修正请求"""
        requests = self.get_all_requests()
        for req in requests:
            if req["question"] == question and req["status"] == "pending":
                req["corrected_cypher"] = corrected_cypher
                req["status"] = "resolved"
                break
        self._save_requests(requests)

    def delete_resolved(self) -> None:
        """删除已解决的请求"""
        requests = [r for r in self.get_all_requests() if r["status"] != "resolved"]
        self._save_requests(requests)

    def _save_requests(self, requests: List[Dict]) -> None:
        """保存请求到文件"""
        with open(self.db_file, 'w') as f:
            json.dump(requests, f, indent=2, ensure_ascii=False)