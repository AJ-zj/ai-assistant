from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from chat.chat_routes import chat_router
from knowledgebase_server.knowledge_route import kb_router
import traceback

# 配置
from config.setting import MEDIA_DIR

# 创建 FastAPI 实例
app = FastAPI(title="AI知识库服务", version="1.0")


# ======================
# 全局异常处理（Pydantic 校验错误）
# ======================
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    # 提取可序列化的错误信息
    errors = []
    for error in exc.errors():
        error_info = {
            "loc": " -> ".join(str(loc) for loc in error.get("loc", [])),
            "msg": error.get("msg", ""),
            "type": error.get("type", "")
        }
        errors.append(error_info)

    # 安全地处理 body（可能是 bytes 或 dict）
    body_content = None
    if hasattr(exc, 'body'):
        if isinstance(exc.body, bytes):
            try:
                body_content = exc.body.decode('utf-8')
            except:
                body_content = str(exc.body)
        else:
            body_content = str(exc.body)

    return JSONResponse(
        status_code=422,
        content={
            "code": 422,
            "msg": "参数校验失败",
            "errors": errors,  # 只返回可序列化的错误信息
            "body": body_content  # 安全的 body 内容
        },
    )


# ======================
# 通用异常处理
# ======================
@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    # 打印完整错误到控制台
    print(f"❌ Unhandled exception: {type(exc).__name__}: {exc}")
    traceback.print_exc()

    return JSONResponse(
        status_code=500,
        content={
            "code": 500,
            "msg": "服务器内部错误",
            "error": str(exc),
            "error_type": type(exc).__name__
        },
    )


# ======================
# 跨域中间件
# ======================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ======================
# 挂载路由
# ======================
app.include_router(chat_router)
app.include_router(kb_router)

# ======================
# 静态文件服务（上传的图片、文件）
# ======================
app.mount("/media", StaticFiles(directory=MEDIA_DIR), name="media")


# ======================
# 健康检查接口
# ======================
@app.get("/")
async def root():
    return {"message": "AI知识库服务运行成功 ✅"}


# ======================
# 启动入口
# ======================
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app_server:app",
        host="127.0.0.1",
        port=6605,
        log_level="info"
    )