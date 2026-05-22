"""日志格式检测模块"""
import re


def detect_format(file_path):
    """检测日志文件的格式类型

    支持的格式:
    - format1: 用户名(ID) 年-月-日 时间
    - format2: 用户名(ID) 年/月/日 时间
    - format3: 时间 <用户名>消息内容 (无冒号)
    - format4: 时间<用户名>:消息内容
    - format5: 用户名(ID) 时间 (仅时间，无日期)

    Args:
        file_path: 日志文件路径

    Returns:
        str: 格式类型标识 (format1/format2/format3/format4/format5)
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                # 跳过 [mirai: 开头的系统消息
                if line.startswith('[mirai:'):
                    continue

                # 格式1: 用户名(ID) 年-月-日 时间
                if re.match(r'.+?\(\d+\) \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}', line):
                    return "format1"

                # 格式2: 用户名(ID) 年/月/日 时间
                if re.match(r'.+?\(\d+\) \d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}', line):
                    return "format2"

                # 格式5: 用户名(ID) 时间 (仅时间，无日期)
                if re.match(r'.+?\(\d+\) \d{2}:\d{2}:\d{2}', line):
                    return "format5"

                # 格式3: 时间 <用户名>消息内容 (无冒号)
                if re.match(r'\d{2}:\d{2}:\d{2} <([^>]+)>(.*)', line):
                    return "format3"

                # 格式4: 时间<用户名>:消息内容
                if re.match(r'(?:\d{2}:\d{2}:\d{2})?<([^>]+)>:(.*)', line):
                    return "format4"
    except FileNotFoundError:
        print(f"警告: 文件 {file_path} 未找到")

    # 默认返回格式1
    return "format1"
