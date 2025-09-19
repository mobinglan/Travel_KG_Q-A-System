# -*- coding: utf-8 -*-
import time  # 正确的 time 模块导入
import streamlit as st
import pandas as pd
from pathlib import Path
import folium
from streamlit_folium import st_folium
from data_manager.sights_data import SightsData

# 在 sights_map.py 开头添加页面配置
st.set_page_config(page_title="中国景点地图", layout="wide")

def sights_map(session_state=None):
    if session_state is None:
        session_state = st.session_state

    # 初始化数据管理器
    sights_data = SightsData()

    # 状态初始化
    if 'selected_sight' not in session_state:
        session_state.selected_sight = None

    # 加载数据（带缓存）
    @st.cache_data
    def load_data():
        try:
            data_file = Path(__file__).parent.parent / "data" / "sights_coordinates.xlsx"
            df = pd.read_excel(data_file)

            required_cols = ["name", "address", "price", "description", "initial_rating", "latitude", "longitude"]
            if not all(col in df.columns for col in required_cols):
                st.error("Excel文件缺少必要列！")
                return None

            df = df[df['latitude'].notna() & df['longitude'].notna()]
            df['avg_rating'] = df.apply(
                lambda row: sights_data.calculate_avg_rating(row['name'], row['initial_rating']),
                axis=1
            )
            return df
        except Exception as e:
            st.error(f"数据加载失败: {str(e)}")
            return None

    df = load_data()
    if df is None:
        st.stop()

    col_map, col_detail = st.columns([3, 2])  # 3:2比例相当于5/3 : 5/2

    with col_map:
        st.title("🗺️ 中国景点地图")
        search_query= st.text_input("搜索景点名称或地址", "", key="search")
        # 数据筛选
        def filter_data():
            if search_query:
                mask = (df["name"].str.contains(search_query, case=False)) | \
                       (df["address"].str.contains(search_query, case=False))
                return df[mask]
            return df

        filtered_df = filter_data()

        # 主地图区域
        if not filtered_df.empty:
            m = folium.Map(
                location=[filtered_df['latitude'].mean(), filtered_df['longitude'].mean()],
                zoom_start=6 if len(filtered_df) > 50 else 8,
                tiles='https://webrd01.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}',
                attr='高德地图',
                control_scale=True
            )

            # 添加标记点
            for _, row in filtered_df.iterrows():
                folium.Marker(
                    location=[row['latitude'], row['longitude']],
                    popup=folium.Popup(f"<b>{row['name']}</b>", max_width=120),
                    tooltip=f"{row['name']} ¥{row['price']}",
                    icon=folium.Icon(color='blue'),
                ).add_to(m)

            # 渲染地图
            st_folium(
                m,
                width=None,
                height=650,
                key="main_map",
                returned_objects=["last_object_clicked"]
            )

    with col_detail:
        # 景点详情板块（与页面标题齐平）
        # st.subheader("景点详情", divider=False)

        # 景点选择下拉框
        sight_options = filtered_df['name'].tolist() if not filtered_df.empty else []
        selected_sight_name = st.selectbox(
            "选择查看景点",
            options=sight_options,
            index=0,
            key="sight_selector"
        )

        if selected_sight_name and not filtered_df.empty:
            selected_sight = filtered_df[filtered_df['name'] == selected_sight_name].iloc[0]
            sight_extra = sights_data.get_sight_by_name(selected_sight_name)

            # 地址信息
            st.text(f"地址：{selected_sight['address']}")

            # 价格和评分并排显示（各占一半）
            col_price, col_rating = st.columns(2)
            with col_price:
                st.text(f"门票价格：¥{selected_sight['price']}")
            with col_rating:
                st.text(f"平均评分：{selected_sight['avg_rating']:.1f}/5.0")

            # 景点介绍（可滚动区域）
            st.text("景点介绍")
            with st.container(height=200):
                st.write(selected_sight['description'])

            # 评论部分（占详情部分的2/5）
            col_comments, col_rating_form = st.columns(2)  # 左右各占一半

            with col_comments:
                st.subheader("景点评论", divider=False)
                if sight_extra and sight_extra.get("comments"):
                    with st.container(height=200):
                        for comment in reversed(sight_extra["comments"]):
                            st.text(f"{comment['username']} ({comment['timestamp']})")
                            st.text(comment['comment'])
                            st.divider()
                else:
                    st.info("暂无游客评价")

            with col_rating_form:
                st.subheader("游客评价", divider=False)
                with st.form(f"rate_{selected_sight_name}"):
                    rating = st.slider("评分", 1.0, 5.0, 3.0, 0.5,
                                       key=f"rating_{selected_sight_name}")
                    comment = st.text_area("评论内容",
                                           key=f"comment_{selected_sight_name}",
                                           height=100)
                    # 在评论提交部分：
                    if st.form_submit_button("提交评价"):
                        if "username" in session_state and session_state.logged_in:
                            try:
                                sights_data.add_rating(selected_sight_name,
                                                       session_state["username"],
                                                       rating)
                                if comment.strip():
                                    sights_data.add_comment(selected_sight_name,
                                                            session_state["username"],
                                                            comment)
                                st.success("评价已提交！")
                                time.sleep(0.5)
                                st.rerun()
                            except Exception as e:
                                st.error(f"提交评价失败: {str(e)}")
                        else:
                            st.warning("请先登录后再提交评价")
                            session_state.show_login = True
                            st.rerun()


if __name__ == "__main__":
    sights_map()