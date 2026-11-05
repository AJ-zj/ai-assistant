import requests
import json

chat_with_agent_url = "http://127.0.0.1:6605/chat/agent_chat"

import requests
import json

chat_with_agent_url = "http://127.0.0.1:6605/chat/agent_chat"


def chat_with_agent(prompt, history, system_prompt, history_len, temperature, max_tokens, stream, session_id):
    # 确保query不为空
    if isinstance(prompt, str):
        query = prompt.strip()
    elif isinstance(prompt, dict) and 'text' in prompt:
        query = prompt['text'].strip()
    else:
        query = str(prompt).strip()
    
    # 如果query仍然为空，返回错误信息
    if not query:
        yield "请输入问题内容"
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