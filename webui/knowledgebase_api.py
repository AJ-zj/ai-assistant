import json
import requests
import gradio as gr

base_url = "http://127.0.0.1:6605"

# ====================== 知识库创建 ======================
def create_kb(kb_name, kb_info):
    url = base_url + "/knowledgebase/create_kb"  # 修复拼写
    data = {
        'kb_name': kb_name,
        'kb_info': kb_info
    }
    try:
        response = requests.post(url, json=data, timeout=10)
        if response.status_code == 200:
            return gr.update(value="知识库创建成功！", visible=True), "", ""
        else:
            return gr.update(value=f"创建失败：{response.json().get('detail', '未知错误')}", visible=True), "", ""
    except Exception as e:
        return gr.update(value=f"请求失败：{str(e)}", visible=True), "", ""

# ====================== 知识库删除 ======================
def delete_kb(kb_name):
    url = base_url + "/knowledgebase/delete_kb"  # 修复拼写
    try:
        response = requests.delete(url, params={"kb_name": kb_name}, timeout=10)
        if response.status_code == 200:
            return gr.update(value="知识库删除成功！", visible=True), ""
        else:
            return gr.update(value=f"删除失败：{response.json().get('detail', '未知错误')}", visible=True), ""
    except Exception as e:
        return gr.update(value=f"请求失败：{str(e)}", visible=True), ""

# ====================== 文件上传（核心修复） ======================
def upload_docs(kb_name_upload, file_upload, chunk_size, chunk_overlap):
    url = base_url + "/knowledgebase/upload_docs"  # 修复拼写
    files = []
    try:
        # 安全打开文件
        for path in file_upload:
            files.append(("files", open(path, "rb")))

        data = {
            "kb_name": kb_name_upload,
            "chunk_size": chunk_size,
            "chunk_overlap": chunk_overlap
        }

        response = requests.post(url, data=data, files=files, timeout=300)
        if response.status_code == 200:
            result = response.json()
            total = result.get("total", 0)
            success = result.get("success", 0)
            failed = result.get("failed", 0)
            success_files = result.get("success_files", [])
            failed_files = result.get("failed_files", [])
            
            message = f"## 📤 上传结果\n\n"
            message += f"- **总共上传**: {total} 个文档\n"
            message += f"- **成功**: {success} 个\n"
            message += f"- **失败**: {failed} 个\n\n"
            
            if success_files:
                message += "### ✅ 成功的文件：\n"
                for f in success_files:
                    message += f"- {f}\n"
            
            if failed_files:
                message += "\n### ❌ 失败的文件：\n"
                for f in failed_files:
                    message += f"- {f.get('name', '未知')}: {f.get('error', '未知错误')}\n"
            
            return gr.update(value=message, visible=True), []
        else:
            return gr.update(
                value=f"## ❌ 上传失败\n\n{response.json().get('detail', '未知错误')}",
                visible=True
            ), []

    except Exception as e:
        return gr.update(value=f"请求失败：{str(e)}", visible=True), []

    finally:
        # 必须关闭文件！！
        for _, f in files:
            try:
                f.close()
            except:
                pass

# ====================== 获取知识库列表 ======================
def list_kbs():
    url = base_url + "/knowledgebase/list_kbs"  # 修复拼写
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            kb_list = response.json()
            knowledgebases = kb_list.get("knowledgebases", [])
            choices = []
            for kb in knowledgebases:
                if isinstance(kb, dict):
                    choices.append(kb.get("kb_name", ""))
                else:
                    choices.append(str(kb))
            return gr.update(choices=choices)
        else:
            return gr.update(choices=[])
    except Exception as e:
        print(f"获取知识库列表失败: {e}")
        return gr.update(choices=[])

# ====================== 文件选择更新（安全版） ======================
def update(new_files):
    if new_files:
        return new_files, []
    return [], []