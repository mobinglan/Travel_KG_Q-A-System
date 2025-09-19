# -*- coding: utf-8 -*-
import pandas as pd
from pathlib import Path
import folium
from data_manager.file_handler import FileHandler

class SightsData:
    def __init__(self):
        self.data_file = FileHandler().get_path("sights_data.json")
        self._init_data()

    def _init_data(self):
        if not self.data_file.exists():
            initial_data = {"sights": []}
            FileHandler().save_json("sights_data.json", initial_data)

    def get_all_sights(self):
        data = FileHandler().load_json("sights_data.json")
        return data["sights"]

    def get_sight_by_name(self, name):
        sights = self.get_all_sights()
        return next((s for s in sights if s["name"] == name), None)

    def add_rating(self, sight_name, username, score):
        sights = self.get_all_sights()
        for sight in sights:
            if sight["name"] == sight_name:
                sight["ratings"].append({"username": username, "score": float(score)})
                break
        self._save_sights(sights)

    def add_comment(self, sight_name, username, comment):
        """添加评论到景点数据"""
        sights = self.get_all_sights()
        sight_found = False

        # 查找景点并添加评论
        for sight in sights:
            if sight["name"] == sight_name:
                if "comments" not in sight:
                    sight["comments"] = []

                sight["comments"].append({
                    "username": username,
                    "comment": comment,
                    "timestamp": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")
                })
                sight_found = True
                break

        if not sight_found:
            # 如果景点不存在，创建新条目
            sights.append({
                "name": sight_name,
                "comments": [{
                    "username": username,
                    "comment": comment,
                    "timestamp": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")
                }],
                "ratings": []
            })

        self._save_sights(sights)

    def _save_sights(self, sights):
        FileHandler().save_json("sights_data.json", {"sights": sights})

    def create_map(self, center=[35.0, 105.0], zoom_start=5):
        """创建高德街道图"""
        return folium.Map(
            location=center,
            zoom_start=zoom_start,
            tiles='https://webrd01.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}',
            attr='高德地图',
            control_scale=True
        )

    def calculate_avg_rating(self, sight_name, initial_rating):
        """计算平均评分（包含初始评分）"""
        sight = self.get_sight_by_name(sight_name)
        if not sight or not sight.get("ratings"):
            return initial_rating
        ratings = [r["score"] for r in sight["ratings"]]
        return (sum(ratings) + initial_rating) / (len(ratings) + 1)