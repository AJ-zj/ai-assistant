import os
# 心之天气 API 工具类
import requests
from config.setting import TIME_OUT


class WeatherCheck:
    def __init__(self, api_key: str):
        self.api_key = api_key

    def run(self, city: str):
        try:
            # 只取第一行，避免传入多余内容
            city = city.split("\n")[0].strip()

            # 心知天气 API
            url = f"https://api.seniverse.com/v3/weather/now.json?key={self.api_key}&location={city}&language=zh-Hans&unit=c"

            # 发送请求
            response = requests.get(url, timeout=TIME_OUT)

            if response.status_code == 200:
                data = response.json()
                weather = data['results'][0]['now']['text']
                temperature = data['results'][0]['now']['temperature']
                return f"当前{city}天气为：{weather}，温度为：{temperature}℃"
            else:
                return f"获取{city}天气失败，错误码：{response.status_code}"

        except Exception as e:
            return f"获取天气时出现异常：{str(e)}"


# 全局使用示例（你在别的文件可以导入这个）
weather_check = WeatherCheck(api_key=os.getenv("SENIVERSE_API_KEY", ""))