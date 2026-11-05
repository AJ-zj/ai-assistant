""""它会自动识别中英双语的最终答案，只把干净的答案流式推送给前端，屏蔽思考过程，稳定且商用级可用"""
from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator, Dict, List, Literal, Union, cast

from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.outputs import LLMResult


class CustomAsyncIteratorCallbackHandler(AsyncCallbackHandler):
    """通用双语流式输出回调
    支持：
    - English: Final Answer:
    - 中文: 最终答案：
    只输出最终答案，不输出思考过程
    """

    queue: asyncio.Queue[str]
    done: asyncio.Event

    @property
    def always_verbose(self) -> bool:
        return True

    def __init__(self) -> None:
        self.queue = asyncio.Queue()
        self.done = asyncio.Event()

        # 英文匹配（原版逻辑）
        self.answer_prefix_tokens = ["Final", "Answer", ":"]
        # 中文匹配（新增）
        self.cn_answer_prefix = "最终答案："

        self.answer_reached = False
        self.last_tokens = []

    async def on_llm_start(
            self, serialized: Dict[str, Any], prompts: List[str], **kwargs: Any
    ) -> None:
        # 每次重新生成时清空状态
        self.done.clear()
        self.answer_reached = False
        self.last_tokens = []

    async def on_llm_new_token(self, token: str, **kwargs: Any) -> None:
        if not token or token.strip() == "":
            return

        # ----------------------
        # 逻辑1：兼容英文 Final Answer:
        # ----------------------
        self.last_tokens.append(token.strip())
        if len(self.last_tokens) > len(self.answer_prefix_tokens):
            self.last_tokens.pop(0)

        if not self.answer_reached:
            # 检查英文匹配
            if self.last_tokens[-len(self.answer_prefix_tokens):] == self.answer_prefix_tokens:
                self.answer_reached = True

            # 检查中文匹配
            current_buf = "".join(self.last_tokens[-10:])  # 取最后10个字符判断
            if self.cn_answer_prefix in current_buf:
                self.answer_reached = True

        # ----------------------
        # 如果已经找到答案，开始输出
        # ----------------------
        if self.answer_reached:
            self.queue.put_nowait(token)

    async def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        self.done.set()

    async def on_llm_error(self, error: BaseException, **kwargs: Any) -> None:
        self.done.set()

    async def aiter(self) -> AsyncIterator[str]:
        while not self.done.is_set() or not self.queue.empty():
            done, pending = await asyncio.wait(
                [
                    asyncio.create_task(self.queue.get()),
                    asyncio.create_task(self.done.wait()),
                ],
                return_when=asyncio.FIRST_COMPLETED,
            )

            # 取消未完成任务，防止内存泄漏
            for task in pending:
                task.cancel()

            result = done.pop().result()
            if result is True:
                continue
            yield result