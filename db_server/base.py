import os
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from config.setting import SQLALCHEMY_DATABASE_URI, SQLALCHEMY_DATABASE

# 确保数据库目录存在（只创建目录，不创建文件）
db_dir = os.path.dirname(SQLALCHEMY_DATABASE)
if db_dir and not os.path.exists(db_dir):
    os.makedirs(db_dir)

# 创建数据库引擎
engine = create_engine(SQLALCHEMY_DATABASE_URI, echo=True)

# 创建基类
Base = declarative_base()

# 定义 KnowledgeBase 模型
class KnowledgeBase(Base):
    __tablename__ = 'knowledge_base'  # 表名
    id = Column(Integer, primary_key=True, autoincrement=True, comment='知识库ID')
    kb_name = Column(String(50), comment='知识库名称')
    kb_info = Column(String(200), comment='知识库简介')

    def __repr__(self):
        return f"KnowledgeBase(id={self.id}, kb_name={self.kb_name}, kb_info={self.kb_info})"

# ✅ 关键：创建所有表（必须加）
Base.metadata.create_all(bind=engine)

# 创建会话（推荐不直接全局实例化）
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 正确获取 session 方式
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
session = SessionLocal()