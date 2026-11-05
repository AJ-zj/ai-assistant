import requests
import json

chat_with_agent_url = "http://127.0.0.1:6605/chat/agent_chat"

payload = {
    "query": "你好",
    "sys_prompt": "You are a helpful assistant.",
    "history_len": -1,
    "history": [],
    "temperature": 0.5,
    "max_tokens": 1024,
    "session_id": "test_session"
}

print("测试后端API...")
print(f"请求URL: {chat_with_agent_url}")
print(f"请求数据: {payload}")

try:
    response = requests.post(
        chat_with_agent_url,
        data={
            "request": json.dumps(payload, ensure_ascii=False)
        },
        stream=False,
        timeout=(5, 60)
    )
    
    print(f"\n响应状态码: {response.status_code}")
    print(f"响应头: {dict(response.headers)}")
    
    if response.status_code != 200:
        print(f"\n错误信息: {response.text}")
    else:
        print("\n响应内容:")
        print(response.text)
                
except Exception as e:
    print(f"\n发生错误: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
