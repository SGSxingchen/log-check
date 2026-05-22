"""主程序入口 - 模块化版本"""
import os
import sys
import io

# 修复 Windows 下的编码问题
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# 确保可以导入 app 目录下的模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from parser import parse_log_file
from output import generate_csv, print_summary_stats

# 输出文件夹配置
OUTPUT_DIR = "outputs"


def get_safe_input(prompt, default_value):
    """尝试获取用户输入，失败时使用默认值"""
    try:
        return input(prompt) or default_value
    except Exception as e:
        print(f"无法获取用户输入: {e}，使用默认值: {default_value}")
        return default_value


def ensure_output_dir():
    """确保输出文件夹存在"""
    if not os.path.exists(OUTPUT_DIR):
        try:
            os.makedirs(OUTPUT_DIR)
            print(f"已创建输出文件夹: {OUTPUT_DIR}/")
        except Exception as e:
            print(f"创建输出文件夹失败: {e}")
            return False
    return True


def generate_output_filename(input_file):
    """根据输入文件名生成输出文件名

    Args:
        input_file: 输入的日志文件路径

    Returns:
        str: 输出文件名（不含扩展名）
    """
    # 获取文件名（不含路径）
    basename = os.path.basename(input_file)

    # 去掉扩展名
    name_without_ext = os.path.splitext(basename)[0]

    # 如果是默认的log.txt，使用"对话统计"
    if name_without_ext.lower() == "log":
        return "对话统计"

    return name_without_ext


def find_log_files():
    """在当前目录和logs目录查找可能的日志文件"""
    log_files = []

    # 要排除的明显不是日志文件的文件名列表
    exclude_files = ["requirements.txt", "README.md", "setup.py"]

    # 检查当前目录
    for file in os.listdir('.'):
        if file.endswith('.txt') and os.path.isfile(file) and file not in exclude_files:
            log_files.append(file)

    # 检查logs目录（如果存在）
    logs_dir = "./logs"
    if not os.path.exists(logs_dir):
        try:
            os.makedirs(logs_dir)
            print(f"已创建logs目录: {logs_dir}")
        except Exception as e:
            print(f"创建logs目录失败: {e}")

    if os.path.exists(logs_dir) and os.path.isdir(logs_dir):
        for file in os.listdir(logs_dir):
            if file.endswith('.txt') and os.path.isfile(os.path.join(logs_dir, file)):
                log_files.append(os.path.join(logs_dir, file))

    return log_files


if __name__ == "__main__":
    print("=" * 70)
    print("欢迎使用角色对话统计工具 (模块化版本)")
    print("=" * 70)
    print("\n提示: 您可以将日志文件放在当前目录或'logs'文件夹中")

    # 检查当前目录下的日志文件
    log_files = find_log_files()
    if log_files:
        print("\n发现可能的日志文件:")
        for i, file in enumerate(log_files, 1):
            print(f"{i}. {file}")
        print("请输入文件编号或直接输入完整文件路径")
    else:
        print("\n未发现日志文件，请将日志文件(.txt)放入当前目录或'logs'文件夹中")

    # 执行统计
    try:
        file_input = get_safe_input("请输入日志文件路径（默认为log.txt）：", "log.txt")

        # 如果输入的是数字，尝试从发现的文件列表中选择
        if log_files and file_input.isdigit():
            index = int(file_input) - 1
            if 0 <= index < len(log_files):
                file_path = log_files[index]
            else:
                file_path = "log.txt"
        else:
            file_path = file_input

        # 确保输出文件夹存在
        if not ensure_output_dir():
            print("无法创建输出文件夹，程序退出")
            sys.exit(1)

        # 自动生成输出文件名（保存到 outputs 文件夹）
        output_basename = generate_output_filename(file_path)
        csv_file = os.path.join(OUTPUT_DIR, f"{output_basename}.csv")
        excel_file = os.path.join(OUTPUT_DIR, f"{output_basename}.xlsx")

        print(f"\n正在处理文件：{file_path}")
        print(f"输出文件：")
        print(f"  - CSV: {csv_file}")
        print(f"  - Excel: {excel_file}")

        daily_stats, dialogue_contents = parse_log_file(file_path)
        print_summary_stats(daily_stats)
        generate_csv(daily_stats, dialogue_contents, csv_file)

        print("\n处理完成！按任意键退出...")
        try:
            input()
        except:
            pass
    except Exception as e:
        print(f"程序发生错误: {e}")
        import traceback
        traceback.print_exc()
        print("按任意键退出...")
        try:
            input()
        except:
            pass
