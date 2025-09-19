# -*- coding: utf-8 -*-
import streamlit as st
from core.Cyher_chat import LocalCypherGenerator
from correction_db import CorrectionDB
from typing import Dict, List
from datetime import datetime
import json
import traceback
from data_manager.file_handler import FileHandler


def format_neo4j_results(results: List[Dict]) -> str:
    """动态结果格式化函数"""
    if not results:
        return "🔍 未找到匹配结果，请尝试调整查询条件"

    # 动态识别结果类型
    first_record = results[0]

    # 通过关键字模糊匹配
    timing_keywords = ["open", "time", "hours"]
    policy_keywords = ["preferential", "policy", "discount"]

    if any(k in key.lower() for key in first_record.keys() for k in timing_keywords):
        return format_dynamic_info(results, "开放时间", ["phone", "contact"])
    elif any(k in key.lower() for key in first_record.keys() for k in policy_keywords):
        return format_dynamic_info(results, "优惠政策", ["phone", "contact"])
    else:
        return format_general_attractions(results)


def format_dynamic_info(results: List[Dict], title: str, highlight_fields: List[str]) -> str:
    """动态格式化特定类型信息"""
    formatted = f"📌 【{title}】\n------------------------------"

    for record in results[:3]:  # 最多显示3条
        items = []
        # 高亮字段优先
        for field in highlight_fields:
            if field in record:
                items.append(f"{field}: {record[field]}")

        # 其他字段
        other_fields = [f"{k}: {v}" for k, v in record.items()
                        if k not in highlight_fields and v not in [None, "无信息"]]
        items.extend(other_fields)

        formatted += f"\n• " + " | ".join(items)

    return formatted


def format_general_attractions(results: List[Dict]) -> str:
    """通用景点信息格式化（优化字段显示顺序）"""
    formatted = "🔍 为您找到以下推荐：\n\n"
    for i, record in enumerate(results, 1):
        # 动态优先级字段
        priority_fields = [
                              k for k in ["name", "title", "sight"]  # 可能的名称字段
                              if k in record
                          ] + ["star", "heat", "rating"]  # 评分类字段

        # 去重处理
        displayed = []
        seen_fields = set()

        for field in priority_fields:
            if field in record and field not in seen_fields:
                displayed.append(f"{field}: {record[field]}")
                seen_fields.add(field)

        # 添加剩余字段
        remaining = [
            f"{k}: {v}" for k, v in record.items()
            if k not in seen_fields and v not in [None, "无信息"]
        ]
        displayed.extend(remaining[:3])  # 最多显示3个额外字段

        formatted += f"{i}. " + " | ".join(displayed) + "\n"

    return formatted


def user_page(session_state=None):
    """用户页面，带隔离的聊天记录功能"""
    if session_state is None:
        session_state = st.session_state

    # 确保username存在
    username = session_state.get("username", "guest")
    if not username or username == "guest":
        st.warning("请先登录")
        return

    # 初始化文件处理器
    file_handler = FileHandler()
    chat_history_file = "user_chat_history.json"

    # 用户隔离的session key
    user_session_key = f"user_{username}_messages"
    last_query_key = f"user_{username}_last_query"

    def load_chat_history():
        """加载当前用户的聊天历史"""
        try:
            history = file_handler.load_json(chat_history_file) or {}
            return history.get(username, [])
        except Exception as e:
            print(f"加载聊天记录失败: {str(e)}")
            return []

    def save_chat_history(messages: List[Dict]):
        """保存当前用户的聊天历史"""
        try:
            history = file_handler.load_json(chat_history_file) or {}
            history[username] = messages
            file_handler.save_json(chat_history_file, history)
        except Exception as e:
            st.error(f"保存聊天记录失败: {str(e)}")
            print(f"保存聊天记录失败: {str(e)}")

    # 初始化用户专属会话状态
    if user_session_key not in session_state:
        session_state[user_session_key] = load_chat_history()
        if not session_state[user_session_key]:
            session_state[user_session_key] = [
                {"role": "assistant", "content": "您好！我是智能旅行助手，请问有什么可以帮您？"}
            ]

    if last_query_key not in session_state:
        session_state[last_query_key] = {"prompt": "", "cypher": "", "results": None}

    # 显示页面标题
    st.title(f"🧳 智能旅行助手 Pro - {username}")

    # 侧边栏控制
    with st.sidebar:
        st.subheader("会话控制")
        if st.button("🔄 清除当前会话"):
            session_state[user_session_key] = [
                {"role": "assistant", "content": "您好！我是智能旅行助手，请问有什么可以帮您？"}
            ]
            save_chat_history(session_state[user_session_key])
            st.rerun()

        if session_state.get("role") == "admin":
            st.subheader("管理员工具")
            if st.checkbox("📊 查看所有聊天记录"):
                history = file_handler.load_json(chat_history_file) or {}
                selected_user = st.selectbox("选择用户", list(history.keys()))
                st.json(history[selected_user])

    # 显示当前用户的历史消息
    for msg in session_state[user_session_key]:
        st.chat_message(msg["role"]).write(msg["content"])

    # 处理用户输入
    if prompt := st.chat_input():
        # 保存用户消息
        session_state[user_session_key].append({"role": "user", "content": prompt})
        save_chat_history(session_state[user_session_key])
        st.chat_message("user").write(prompt)

        # 初始化工具类
        cypher_chat = LocalCypherGenerator()
        correction_db = CorrectionDB()

        try:
            # 生成并执行查询
            cypher_query = cypher_chat.generate_cypher(prompt)
            raw_results = cypher_chat.execute_query(cypher_query)

            # 仅管理员可见CYPHER语句
            if session_state.get("role") == "admin":
                st.code(f"CYPHER: {cypher_query}")

            # 使用通用格式化函数
            response = format_neo4j_results(raw_results)

            # 保存最后一次查询信息
            session_state[last_query_key] = {
                "prompt": prompt,
                "cypher": cypher_query,
                "results": raw_results
            }

            # 保存并显示结果
            session_state[user_session_key].append(
                {"role": "assistant", "content": response}
            )
            save_chat_history(session_state[user_session_key])
            st.chat_message("assistant").write(response)
        except Exception as e:
            # Initialize correction_db if not already done
            correction_db = CorrectionDB()  # Add this line to ensure the variable exists

            # 错误处理
            error_detail = f"""
                  ⚠️ 查询失败,超出本助手的知识范围了

                  错误类型: {type(e).__name__}
                  错误信息: {str(e)}

                  您可以尝试:
                  1. 换种方式提问
                  2. 联系管理员修复
                  """
            session_state[user_session_key].append({
                "role": "assistant",
                "content": error_detail
            })
            save_chat_history(session_state[user_session_key])
            st.chat_message("assistant").write(error_detail)

            # 记录错误详情
            debug_info = {
                "timestamp": datetime.now().isoformat(),
                "question": prompt,
                "error": str(e),
                "traceback": traceback.format_exc()
            }
            correction_db.add_request(
                question=json.dumps(debug_info),
                generated_cypher=locals().get('cypher_query', '未生成'),
                error_msg=f"{type(e).__name__}: {str(e)}"
            )

    # 满意度评价（仅在最近有查询时显示）
    if session_state[last_query_key].get("prompt"):
        st.divider()
        col1, col2 = st.columns(2)
        with col1:
            if st.button("👍 满意", help="结果符合预期"):
                try:
                    cypher_chat.save_template(
                        question=session_state[last_query_key]["prompt"],
                        cypher=session_state[last_query_key]["cypher"],
                        validated=True
                    )
                    st.success("感谢您的反馈！已保存该查询模板")
                    session_state[last_query_key] = {"prompt": "", "cypher": "", "results": None}
                    st.rerun()
                except Exception as e:
                    st.error(f"保存模板失败: {str(e)}")

        with col2:
            if st.button("👎 不满意", help="结果不符合预期"):
                correction_db.add_request(
                    question=session_state[last_query_key]["prompt"],
                    generated_cypher=session_state[last_query_key]["cypher"],
                    error_msg="用户主动反馈不满意",
                    feedback_type="user_dissatisfied"
                )
                st.warning("感谢您的反馈，我们将改进查询结果")
                session_state[last_query_key] = {"prompt": "", "cypher": "", "results": None}
                st.rerun()


if __name__ == "__main__":
    user_page()