from datetime import datetime

class Get_time:
    def run(self,text:str):
        time=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        return time
get_time=Get_time()


