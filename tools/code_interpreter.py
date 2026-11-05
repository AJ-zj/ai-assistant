import os
import base64
import re
from uuid import uuid4
from codeboxapi import CodeBox
from config.setting import MEDIA_DIR

# 自动创建 media 文件夹（必须加，否则报错）
os.makedirs(MEDIA_DIR, exist_ok=True)

class CodeInterpreter:
    def __init__(self):
        self.output_files = ""
        self.output_codes = ""
        # 本地运行 CodeBox
        self.codebox = CodeBox(api_key="local")
        self.codebox.start()

    # 获取结果：图片路径 + 代码
    def get_outputs(self):
        return self.output_files, self.output_codes

    # 核心：运行代码
    def run(self, code: str):
        # 1. 清理 AI 自带的 ```python ``` 标记
        clean_code = re.sub(r'(```python|```py|```)\s*', '', code, flags=re.IGNORECASE)
        clean_code = clean_code.strip()

        # 2. 去掉空行
        lines = [line for line in clean_code.split('\n') if line.strip()]
        cleaned_code = '\n'.join(lines)

        # 3. 运行代码
        output = self.codebox.run(cleaned_code)

        # 4. 如果输出是图片
        if output.type == "image/png":
            filename = f"{MEDIA_DIR}/image-{uuid4()}.png"
            decoded_image = base64.b64decode(output.content)

            # 保存图片
            with open(filename, 'wb') as f:
                f.write(decoded_image)

            # 生成前端访问地址
            image_url = f"/media/{os.path.basename(filename)}"
            self.output_files = image_url
            self.output_codes = code
            return "Image has been sent to the user."

        # 5. 文本输出
        else:
            return output.content

# 创建全局实例（供全局使用）
code_interpreter = CodeInterpreter()