import os
from fastapi import HTTPException
from langchain_community.document_loaders import PyPDFLoader
from langchain_community.document_loaders import TextLoader, CSVLoader
from langchain_community.document_loaders import UnstructuredMarkdownLoader


class data_loader:  # 类名规范：大驼峰
    def get_loader(self, file_path):
        # 获取文件后缀（正确写法）
        _, ext = os.path.splitext(file_path)
        ext = ext.lower()  # 统一小写，兼容 .PDF .PDF 等

        if ext == '.pdf':
            return PyPDFLoader(file_path)
        elif ext == '.txt':
            return TextLoader(file_path, encoding='utf-8')  # 加编码防止乱码
        elif ext == '.csv':
            return CSVLoader(file_path)
        elif ext == '.md':
            return UnstructuredMarkdownLoader(file_path)
        else:
            raise HTTPException(status_code=400, detail="不支持的文件类型")