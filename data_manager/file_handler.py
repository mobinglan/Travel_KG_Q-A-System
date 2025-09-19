import json
from typing import Dict, List, Any, Union
from pathlib import Path

class FileHandler:
    def __init__(self):
        self.data_dir = Path(__file__).parent.parent / "data"
        self.data_dir.mkdir(exist_ok=True)

    def get_path(self, filename: str) -> Path:
        return self.data_dir / filename

    def load_json(self, filename: str) -> Union[Dict, List]:
        file_path = self.get_path(filename)
        if not file_path.exists():
            return {}

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if not content:
                    return {}
                return json.loads(content)
        except json.JSONDecodeError:
            print(f" Warning: {filename} format invalid, reset ")
            return {}

    def save_json(self, filename: str, data: Any) -> None:
        file_path = self.get_path(filename)
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
