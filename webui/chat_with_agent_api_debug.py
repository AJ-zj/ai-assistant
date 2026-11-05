import requests
import json
import os

chat_with_agent_url = "http://127.0.0.1:6605/chat/agent_chat"


def read_file_content(file_path):
    """读取文件内容，支持txt、pdf、md、csv等格式"""
    if not file_path or not os.path.exists(file_path):
        return ""
    
    ext = os.path.splitext(file_path)[1].lower()
    
    try:
        if ext == '.txt' or ext == '.md' or ext == '.csv':
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        elif ext == '.pdf':
            try:
                import fitz
                doc = fitz.open(file_path)
                text = ""
                for page in doc:
                    text += page.get_text()
                return text
            except Exception as e:
                print(f"DEBUG: 读取PDF失败: {e}")
                return ""
        else:
            return ""
    except Exception as e:
        print(f"DEBUG: 读取文件失败: {e}")
        return ""


def chat_with_agent_debug(prompt, history, system_prompt, history_len, temperature, max_tokens, stream, session_id):
    print("=" * 80)
    print("DEBUG: 接收到的参数")
    print(f"prompt类型: {type(prompt)}, 值: {repr(prompt)}")
    print(f"history类型: {type(history)}, 值: {repr(history)}")
    print(f"system_prompt: {system_prompt}")
    print(f"history_len: {history_len}")
    print(f"temperature: {temperature}")
    print(f"max_tokens: {max_tokens}")
    print(f"stream: {stream}")
    print(f"session_id: {session_id}")
    
    files_content = []
    text_query = ""
    
    # 处理Gradio multimodal的prompt格式
    if isinstance(prompt, dict):
        print("DEBUG: prompt是字典类型")
        if 'files' in prompt:
            files = prompt['files']
            print(f"DEBUG: 发现文件: {files}")
            if isinstance(files, list):
                for file_item in files:
                    if isinstance(file_item, str):
                        file_path = file_item
                    elif isinstance(file_item, dict) and 'path' in file_item:
                        file_path = file_item['path']
                    else:
                        file_path = str(file_item)
                    
                    print(f"DEBUG: 读取文件: {file_path}")
                    content = read_file_content(file_path)
                    if content:
                        files_content.append(content)
        if 'text' in prompt:
            text_query = prompt['text'].strip()
    elif isinstance(prompt, str):
        text_query = prompt.strip()
    elif isinstance(prompt, list):
        for item in prompt:
            if isinstance(item, str) and os.path.exists(item):
                content = read_file_content(item)
                if content:
                    files_content.append(content)
            elif isinstance(item, dict):
                if 'path' in item and os.path.exists(item['path']):
                    content = read_file_content(item['path'])
                    if content:
                        files_content.append(content)
                if 'text' in item:
                    text_query = item['text'].strip()
    else:
        text_query = str(prompt).strip()
    
    print(f"DEBUG: 提取的文本查询: {repr(text_query)}")
    print(f"DEBUG: 提取的文件内容数量: {len(files_content)}")
    
    # 构建最终的query
    if files_content:
        combined_content = "\n\n---\n\n".join(files_content)
        if text_query:
            query = f"文档内容:\n{combined_content}\n\n用户问题:\n{text_query}"
        else:
            query = f"文档内容:\n{combined_content}\n\n请总结文档的主要内容。"
    else:
        query = text_query
    
    print(f"DEBUG: 最终的query: {repr(query[:500])}...")
    
    # 如果query仍然为空，返回错误信息
    if not query.strip():
        yield "请输入问题内容或上传文档"
        return
    
    # 构造 payload
    # 注意：后端 chat_routes.py 期望 history 是 List[str]，且内部是 json 字符串
    formatted_history = []
    for h in history:
        if isinstance(h, dict):
            formatted_history.append(json.dumps(h, ensure_ascii=False))
        else:
            formatted_history.append(str(h))
    
    payload = {
        "query": query,
        "sys_prompt": system_prompt,
        "history_len": int(history_len),
        "history": formatted_history,
        "temperature": float(temperature),
        "max_tokens": int(max_tokens),
        "session_id": session_id
    }
    
    print(f"DEBUG: 发送的payload: {payload}")
    
    try:
        # 使用 data 传参对应后端的 Form 接收方式
        response = requests.post(
            chat_with_agent_url,
            data={
                "request": json.dumps(payload, ensure_ascii=False)
            },
            stream=stream,
            timeout=(5, 60)  # (连接超时, 读取超时)
        )
        
        print(f"DEBUG: 响应状态码: {response.status_code}")
        
        if response.status_code == 200:
            full_answer = ""
            # 改用 iter_lines 处理流式输出，有效防止 JSON 粘连报错
            for line in response.iter_lines(decode_unicode=True):
                if line:
                    try:
                        # 移除可能的 "data: " 前缀（如果后端遵循标准 SSE 格式）
                        clean_line = line.replace("data: ", "").strip()
                        data_json = json.loads(clean_line)
                        
                        answer = data_json.get("answer", "")
                        full_answer += answer
                        yield full_answer
                    except json.JSONDecodeError:
                        # 记录解析失败的行，但不中断流程
                        continue
        else:
            try:
                error_detail = response.json().get("msg", response.text)
                yield f"请求失败 (状态码 {response.status_code}): {error_detail}"
            except:
                yield f"请求失败，状态码：{response.status_code}"
    
    except requests.exceptions.Timeout:
        yield "错误：请求服务器超时，请稍后再试。"
    except Exception as e:
        yield f"发生意外错误：{str(e)}"
