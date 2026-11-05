"""
Gradio 前端入口
启动前请确保已运行：python app_server.py
"""
import uuid
import gradio as gr
from webui.chat_with_agent_api_debug import chat_with_agent_debug as chat_with_agent
from webui.knowledgebase_api import create_kb, delete_kb, upload_docs, list_kbs, update


def generate_session_id():
    return str(uuid.uuid4())


def on_app_load():
    return generate_session_id()


with gr.Blocks(fill_width=True, fill_height=True, title="AI 私人助理") as demo:
    session_state = gr.State(value=on_app_load)

    # ─────────── 聊天页 ───────────
    with gr.Tab("🤖 聊天机器人"):
        gr.Markdown("## 🤖 AI 私人助理")

        with gr.Row():
            with gr.Column(scale=1, variant="panel"):
                sys_prompt = gr.Textbox(
                    label="系统提示语",
                    value="You are a helpful assistant. Answer questions in Chinese!",
                    lines=3,
                )
                history_len = gr.Slider(minimum=-1, maximum=10, value=5, step=1,
                                        label="保留历史消息数量（-1 表示不保留）")
                temperature = gr.Slider(minimum=0.01, maximum=2.0, value=0.7, step=0.01,
                                        label="Temperature（创造性）")
                max_tokens = gr.Slider(minimum=64, maximum=4096, value=1024, step=64,
                                       label="最大输出长度（tokens）")
                stream = gr.Checkbox(label="流式输出", value=True)

            with gr.Column(scale=10):
                chatbot = gr.Chatbot(height=600, show_label=False)
                gr.ChatInterface(
                    fn=chat_with_agent,
                    multimodal=True,
                    chatbot=chatbot,
                    additional_inputs=[
                        sys_prompt,
                        history_len,
                        temperature,
                        max_tokens,
                        stream,
                        session_state,
                    ],
                )

    # ─────────── 知识库管理页 ───────────
    with gr.Tab("📚 知识库管理"):
        gr.Markdown("## 📚 知识库管理")

        with gr.Group():
            gr.Markdown("### 创建 / 删除知识库")
            with gr.Row():
                kb_name = gr.Textbox(label="知识库名称", placeholder="输入新知识库名称")
                kb_info = gr.Textbox(label="知识库描述", placeholder="描述该知识库的内容（供 Agent 选择时参考）")
            with gr.Row():
                create_button = gr.Button("✅ 创建知识库", variant="primary")
                delete_button = gr.Button("🗑️ 删除知识库", variant="stop")
            message_box = gr.Markdown(visible=False)

        with gr.Group():
            gr.Markdown("### 上传文档到知识库")
            with gr.Row():
                kb_name_upload = gr.Dropdown(label="选择目标知识库", choices=[])
                refresh_btn = gr.Button("🔄 刷新列表", scale=0)
            with gr.Row():
                chunk_size = gr.Number(label="单段文本最大长度 (chunk_size)", value=128, minimum=1, maximum=800)
                chunk_overlap = gr.Number(label="相邻文本重合长度 (chunk_overlap)", value=20, minimum=0, maximum=400)
            file_upload = gr.Files(label="选择文件（支持 .txt .pdf .md .csv）")
            file_uploaded = gr.Files(label="已累积选择的文件", visible=False)
            upload_button = gr.Button("⬆️ 上传并向量化", variant="primary")
            upload_message_box = gr.Markdown(visible=False)

        # 事件绑定
        create_button.click(
            create_kb, [kb_name, kb_info], [message_box, kb_name, kb_info]
        ).then(list_kbs, outputs=kb_name_upload)

        delete_button.click(
            delete_kb, [kb_name_upload], [message_box, kb_name]
        ).then(list_kbs, outputs=kb_name_upload)

        refresh_btn.click(list_kbs, outputs=kb_name_upload)

        file_upload.upload(update, [file_upload], [file_uploaded, file_upload])

        upload_button.click(
            upload_docs,
            [kb_name_upload, file_uploaded, chunk_size, chunk_overlap],
            [upload_message_box, file_uploaded],
        )


if __name__ == "__main__":
    try:
        demo.launch(
            server_name="127.0.0.1",  # 强制使用回环地址
            server_port=7900,  # 换一个全新的端口，避开之前的冲突
            show_error=True,
            debug=True,  # 开启调试模式，可以看到更多细节
            quiet=False
        )
    except Exception as e:
        print(f"启动失败，尝试备用方案: {e}")
        # 如果 127.0.0.1 失败，再尝试 0.0.0.0
        demo.launch(server_name="0.0.0.0", server_port=7901)
