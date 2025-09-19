# -*- coding: utf-8 -*-
import sys
import time
import streamlit as st
from pathlib import Path
from data_manager.file_handler import FileHandler

# 路径设置
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.append(str(PROJECT_ROOT))

try:
    from core.User_page import user_page
    from core.admin_correction_page import admin_correction_page
    from core.sights_map import sights_map
except ImportError as e:
    st.error(f"导入模块失败: {e}")
    st.stop()

# 初始化登录状态
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "show_login" not in st.session_state:
    st.session_state.show_login = True

# 用户数据库
USER_DB = FileHandler().get_path("users.json")
if not USER_DB.exists():
    FileHandler().save_json("users.json", [
        {"username": "user", "password": "1234", "role": "user"},
        {"username": "admin", "password": "admin123", "role": "admin"}
    ])


def register():
    """用户注册功能"""
    st.header("用户注册")
    with st.form("register_form"):
        username = st.text_input("用户名")
        password = st.text_input("密码", type="password")
        confirm_password = st.text_input("确认密码", type="password")

        if st.form_submit_button("注册"):
            if not username or not password:
                st.error("用户名和密码不能为空")
                return
            if password != confirm_password:
                st.error("两次输入的密码不一致")
                return

            users = FileHandler().load_json("users.json")
            if any(u["username"] == username for u in users):
                st.error("用户名已存在")
                return

            users.append({
                "username": username,
                "password": password,
                "role": "user"
            })
            FileHandler().save_json("users.json", users)
            st.success("注册成功！请登录")
            st.session_state.show_login = True
            time.sleep(1)
            st.rerun()


def login():
    """用户登录功能"""
    st.header("登录")
    if not st.session_state.show_login:
        register()
        if st.button("已有账号？去登录"):
            st.session_state.show_login = True
            st.rerun()
        return

    with st.form("login_form"):
        username = st.text_input("用户名")
        password = st.text_input("密码", type="password")

        if st.form_submit_button("登录"):
            users = FileHandler().load_json("users.json")
            user = next((u for u in users if u["username"] == username and u["password"] == password), None)

            if user:
                st.session_state.update({
                    "logged_in": True,
                    "username": username,
                    "role": user["role"]
                })
                st.success("登录成功！")
                time.sleep(0.5)
                st.rerun()
            else:
                st.error("用户名或密码错误")

    if st.button("没有账号？去注册"):
        st.session_state.show_login = False
        st.rerun()

def logout():
    """退出登录功能"""
    if st.sidebar.button("退出登录"):
        # 保留聊天记录文件，只清除会话状态
        st.session_state.logged_in = False
        st.session_state.username = None
        st.rerun()
def main_navigation():
    """主导航菜单"""
    st.sidebar.title("导航菜单")

    if st.session_state.role == "admin":
        pages = {
            "用户服务": user_page,
            "系统管理": admin_correction_page,
            "景点地图与评论": sights_map
        }
    else:
        pages = {
            "用户服务": user_page,
            "景点地图与评论": sights_map
        }

    selection = st.sidebar.radio("选择页面", list(pages.keys()))
    logout()

    if 'session_state' in pages[selection].__code__.co_varnames:
        pages[selection](st.session_state)
    else:
        pages[selection]()


# 主程序入口
if not st.session_state.logged_in:
    login()
else:
    main_navigation()