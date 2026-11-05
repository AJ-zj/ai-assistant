from .base import KnowledgeBase
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


def add_kb_to_db(session: Session, kb_name: str, kb_info: str):
    try:
        # 验证参数
        if not kb_name or not kb_name.strip():
            raise ValueError("知识库名称不能为空")
        if len(kb_name) > 50:
            raise ValueError("知识库名称不能超过50个字符")

        # 精确匹配（区分大小写，更符合常规逻辑）
        kb = session.query(KnowledgeBase).filter(KnowledgeBase.kb_name == kb_name).first()

        if not kb:
            # 不存在则创建
            kb = KnowledgeBase(kb_name=kb_name, kb_info=kb_info)
            session.add(kb)

        else:
            # 存在则更新简介
            kb.kb_info = kb_info

        session.commit()
        print(f"知识库 '{kb_name}' 已保存到数据库")

    except Exception as e:
        session.rollback()
        print(f"保存知识库失败: {str(e)}")
        raise  # 抛出异常，让上层接口能捕获并返回错误


def del_kb_from_db(session: Session, kb_name: str):
    try:
        kb_to_delete = session.query(KnowledgeBase).filter_by(kb_name=kb_name).first()

        if kb_to_delete:
            session.delete(kb_to_delete)
            session.commit()
            print(f"知识库 '{kb_name}' 删除成功")
        else:
            print(f"知识库 '{kb_name}' 不存在")

    except Exception as e:
        session.rollback()
        print(f"删除知识库失败: {str(e)}")
        raise


def list_kb_from_db(session: Session):
    all_kbs = session.query(KnowledgeBase).all()
    kbs_list = [
        {"kb_name": kb.kb_name, "kb_info": kb.kb_info} for kb in all_kbs
    ]
    return kbs_list