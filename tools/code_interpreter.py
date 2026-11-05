"""代码解释器工具：在独立工作线程中按需启动本地 CodeBox。

FastAPI 的请求处理运行在 asyncio 事件循环里，而 codeboxapi 的同步方法
（start / run）内部通过 syncify 调用 asyncio.run；如果在模块导入阶段就
创建 CodeBox().start()，会抛 "Already running asyncio in this thread"，
并连带导致整个工具列表加载失败（其余 4 个工具也不可用）。

因此这里：
1. 模块导入时只启动一个空闲 worker 线程，不创建 CodeBox；
2. 首次真正调用本工具时，由 worker 线程创建 CodeBox 并执行代码；
3. 任何异常降级为可读文本返回，不阻断 Agent 的其他工具。
"""

import base64
import os
import queue
import re
import threading
from uuid import uuid4

from codeboxapi import CodeBox

from config.setting import MEDIA_DIR

os.makedirs(MEDIA_DIR, exist_ok=True)


class CodeInterpreter:
    """把 CodeBox 的全部操作收敛到单一 worker 线程，避开主事件循环。"""

    def __init__(self, timeout: int = 120):
        self.output_files = ""
        self.output_codes = ""
        self._timeout = timeout
        self._tasks: "queue.Queue" = queue.Queue()
        self._worker = threading.Thread(
            target=self._serve, daemon=True, name="code-interpreter"
        )
        self._worker.start()

    def _serve(self):
        box = None
        while True:
            code, reply = self._tasks.get()
            try:
                if box is None:
                    box = CodeBox(api_key="local")
                    box.start()
                reply.put(("ok", box.run(code)))
            except Exception as exc:  # noqa: BLE001 - 降级为工具返回文本
                reply.put(("error", f"{type(exc).__name__}: {exc}"))
            finally:
                self._tasks.task_done()

    def _execute(self, code: str):
        reply: "queue.Queue" = queue.Queue()
        self._tasks.put((code, reply))
        try:
            return reply.get(timeout=self._timeout)
        except queue.Empty:
            return ("error", f"代码执行超时（{self._timeout}s）")

    def get_outputs(self):
        return self.output_files, self.output_codes

    def run(self, code: str):
        clean_code = re.sub(
            r"(```python|```py|```)\s*", "", code, flags=re.IGNORECASE
        ).strip()
        cleaned_code = "\n".join(
            line for line in clean_code.split("\n") if line.strip()
        )

        status, payload = self._execute(cleaned_code)
        if status == "error":
            return f"[代码解释器不可用] {payload}"
        output = payload

        if output.type == "image/png":
            filename = os.path.join(MEDIA_DIR, f"image-{uuid4()}.png")
            with open(filename, "wb") as f:
                f.write(base64.b64decode(output.content))
            self.output_files = f"/media/{os.path.basename(filename)}"
            self.output_codes = code
            return "Image has been sent to the user."

        return output.content or ""


code_interpreter = CodeInterpreter()
