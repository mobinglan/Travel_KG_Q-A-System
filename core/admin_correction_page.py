import streamlit as st
from correction_db import CorrectionDB
from core.Cyher_chat import LocalCypherGenerator

def admin_correction_page(session_state=None):
    if session_state is None:
        session_state = st.session_state

    st.title("🔧 Cypher查询修正管理")

    # 初始化组件
    db = CorrectionDB()
    cypher_gen = LocalCypherGenerator()

    # 选项卡布局
    tab1, tab2 = st.tabs(["待处理修正", "已解决修正"])

    with tab1:
        st.subheader("待处理修正请求")
        pending_requests = db.get_all_requests(status="pending")

        if not pending_requests:
            st.info("当前没有待处理的修正请求")
        else:
            for i, req in enumerate(pending_requests):
                with st.expander(f"请求 #{i + 1}: {req['question']}"):
                    st.write(f"**反馈类型:** {req.get('feedback_type', '系统错误')}")  # 新增显示
                    st.write(f"**用户问题:** {req['question']}")
                    st.code(f"生成的Cypher:\n{req['generated_cypher']}", language="cypher")
                    st.error(f"错误信息: {req['error_msg']}")

                    corrected_cypher = st.text_area(
                        "修正后的Cypher语句",
                        value=req['generated_cypher'],
                        key=f"correct_{i}",
                        height=200
                    )

                    if st.button("提交修正", key=f"submit_{i}"):
                        # 验证Cypher语法
                        try:
                            db.resolve_request(req['question'], corrected_cypher)
                            cypher_gen.save_template(req['question'], corrected_cypher, True)
                            st.success("修正已保存并添加到模板库！")
                            st.rerun()
                        except Exception as e:
                            st.error(f"保存修正时出错: {str(e)}")

    with tab2:
        st.subheader("已解决修正记录")
        resolved_requests = db.get_all_requests(status="resolved")

        if not resolved_requests:
            st.info("没有已解决的修正记录")
        else:
            for req in resolved_requests:
                st.write(f"**问题:** {req['question']}")
                st.code(f"修正后的Cypher:\n{req['corrected_cypher']}", language="cypher")
                st.write("---")

            if st.button("清除已解决记录"):
                db.delete_resolved()
                st.success("已清除所有已解决记录！")
                st.rerun()


if __name__ == "__main__":
    admin_correction_page()