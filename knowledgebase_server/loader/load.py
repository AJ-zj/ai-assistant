import os
import fitz
from fastapi import HTTPException
from langchain_core.documents import Document


# ==============================================
#  【正确】Loader 类（类名大写，不与实例冲突）
# ==============================================
class DataLoader:
    def load_file(self, file_path: str) -> list[Document]:
        _, ext = os.path.splitext(file_path)
        ext = ext.lower()

        # PDF - 直接提取文本
        if ext == ".pdf":
            doc = fitz.open(file_path)
            text = ""
            for page in doc:
                text += page.get_text()
            return [Document(page_content=text, metadata={"source": file_path})]

        # TXT
        elif ext == ".txt":
            from langchain_community.document_loaders import TextLoader
            loader = TextLoader(file_path, encoding='utf-8')
            return loader.load()

        # MD
        elif ext == ".md":
            from langchain_community.document_loaders import UnstructuredMarkdownLoader
            loader = UnstructuredMarkdownLoader(file_path)
            return loader.load()

        # CSV
        elif ext == ".csv":
            from langchain_community.document_loaders import CSVLoader
            loader = CSVLoader(file_path)
            return loader.load()

        else:
            raise HTTPException(status_code=400, detail="不支持的文件格式")


# ==============================================
#  【全局单例】正确导出
# ==============================================
data_loader = DataLoader()