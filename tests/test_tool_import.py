"""回归测试：工具列表必须能在运行中的事件循环里安全导入。

历史 bug：code_interpreter 模块级直接 CodeBox().start()，在 FastAPI
请求（asyncio 事件循环已运行）中导入 tools_select 会抛
"Already running asyncio in this thread"，导致 5 个工具全部不可用。
"""

import asyncio
import unittest


class TestToolImportInEventLoop(unittest.TestCase):
    def test_import_and_call_time_tool_inside_running_loop(self):
        async def scenario():
            try:
                from tools.tools_select import tools
            except ImportError as exc:  # 未装可选依赖时跳过
                raise unittest.SkipTest(f"缺少运行依赖: {exc}") from exc

            names = [tool.name for tool in tools]
            time_tool = next(t for t in tools if t.name == "get_time")
            output = time_tool.invoke({"text": ""})
            return names, output

        names, output = asyncio.run(scenario())
        self.assertEqual(len(names), 5)
        self.assertIn("get_time", names)
        self.assertRegex(output, r"\d{4}-\d{2}-\d{2}")


if __name__ == "__main__":
    unittest.main()
