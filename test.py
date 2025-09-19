# -*- coding: utf-8 -*-
import streamlit as st
import folium
from streamlit_folium import st_folium


# 基础地图测试
def test_basic_map():
    st.title("🗺️ 地图基础功能测试")

    # 测试坐标（天安门）
    default_location = [39.9042, 116.4074]

    tab1, tab2 = st.tabs(["高德地图", "OpenStreetMap"])

    with tab1:
        st.subheader("高德地图测试")
        try:
            m = folium.Map(
                location=default_location,
                zoom_start=15,
                tiles='https://webrd01.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}',
                attr='高德地图'
            )
            folium.Marker(
                location=default_location,
                popup="<b>天安门</b>",
                tooltip="点击查看详情"
            ).add_to(m)
            st_folium(m, width=700, height=500)
            st.success("✅ 高德地图加载成功")
        except Exception as e:
            st.error(f"高德地图加载失败: {str(e)}")

    with tab2:
        st.subheader("OpenStreetMap测试")
        try:
            m = folium.Map(
                location=default_location,
                zoom_start=15,
                tiles='OpenStreetMap'
            )
            folium.Marker(default_location).add_to(m)
            st_folium(m, width=700, height=500)
            st.success("✅ OpenStreetMap加载成功")
        except Exception as e:
            st.error(f"OpenStreetMap加载失败: {str(e)}")


# 数据加载测试
def test_data_load():
    st.title("📊 数据加载测试")
    sample_data = {
        "name": ["故宫", "颐和园", "长城"],
        "latitude": [39.9163, 39.9997, 40.3595],
        "longitude": [116.3972, 116.2764, 116.0204]
    }
    df = st.data_editor(pd.DataFrame(sample_data))

    if st.button("测试地图渲染"):
        try:
            m = folium.Map(
                location=[df['latitude'].mean(), df['longitude'].mean()],
                zoom_start=10
            )
            for _, row in df.iterrows():
                folium.Marker(
                    [row['latitude'], row['longitude']],
                    popup=row['name']
                ).add_to(m)
            st_folium(m, width=700, height=500)
            st.success("✅ 测试数据渲染成功")
        except Exception as e:
            st.error(f"渲染失败: {str(e)}")


# 主程序
if __name__ == "__main__":
    import pandas as pd

    st.set_page_config(layout="wide")
    test_basic_map()
    st.divider()
    test_data_load()

    st.sidebar.markdown("""
    ### 测试说明
    1. 高德地图需要网络连接
    2. 如果高德地图失败，OpenStreetMap应作为备用方案
    3. 检查浏览器控制台错误(F12)
    """)