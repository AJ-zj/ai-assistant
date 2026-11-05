from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

# 导入工具
from tools.weather_check import weather_check
from tools.web_search import web_search
from tools.code_interpreter import code_interpreter
from tools.knowledge_search import knowledge_search
from tools.get_time import get_time


# =========================
# 1. 天气工具
# =========================
class WeatherInput(BaseModel):
    city: str = Field(description="城市名", example="北京")

def weather_func(city: str):
    return weather_check.run(city)

weather_tool = StructuredTool.from_function(
    func=weather_func,
    name="weather_check",
    description="查询国内城市实时天气",
    args_schema=WeatherInput
)


# =========================
# 2. 联网搜索
# =========================
class WebSearchInput(BaseModel):
    query: str = Field(description="搜索关键词")

def web_search_func(query: str):
    return web_search.run(query)

web_search_tool = StructuredTool.from_function(
    func=web_search_func,
    name="web_search",
    description="联网搜索实时信息",
    args_schema=WebSearchInput
)


# =========================
# 3. 代码解释器
# =========================
class CodeInterpreterInput(BaseModel):
    code: str = Field(description="Python代码")

def code_func(code: str):
    return code_interpreter.run(code)

code_interpreter_tool = StructuredTool.from_function(
    func=code_func,
    name="code_interpreter",
    description="执行Python代码",
    args_schema=CodeInterpreterInput
)


# =========================
# 4. 知识库搜索
# =========================
class KnowledgeSearchInput(BaseModel):
    inputs: str = Field(description="知识库名,查询内容")

def knowledge_func(inputs: str):
    return knowledge_search.run(inputs)

knowledge_search_tool = StructuredTool.from_function(
    func=knowledge_func,
    name="knowledge_search",
    description="私有知识库搜索",
    args_schema=KnowledgeSearchInput
)


# =========================
# 5. 时间工具（无参数）
# =========================
class GetTimeInput(BaseModel):
    pass

def get_time_func():
    return get_time.run()

get_time_tool = StructuredTool.from_function(
    func=get_time_func,
    name="get_time",
    description="获取当前时间",
    args_schema=GetTimeInput
)


# =========================
# 最终工具列表
# =========================
tools = [
    weather_tool,
    web_search_tool,
    code_interpreter_tool,
    knowledge_search_tool,
    get_time_tool,
]