"""当前时间工具。

``text`` 为兼容早期签名的占位参数：时间由服务端本地时钟给出，
LLM 按 args_schema 传入空对象时也能正常调用。
"""

from datetime import datetime


class Get_time:
    def run(self, text: str = ""):
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


get_time = Get_time()
