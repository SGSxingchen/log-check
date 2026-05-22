"""日志解析模块 - 从日志文件中提取对话数据并进行统计"""
import re
from collections import defaultdict
from datetime import datetime, timedelta
from .format_detector import detect_format
try:
    from ..utils import count_char_weight, normalize_speaker_name
except ImportError:
    from utils import count_char_weight, normalize_speaker_name

# 分天配置
TIME_GAP_THRESHOLD_HOURS = 6  # 超过6小时无发言视为分天

# 参与时长配置
IDLE_THRESHOLD_MINUTES = 15  # 超过15分钟无发言视为休息/摸鱼,不计入参与时长

# CQ 码 / OneBot 占位符过滤
# 形如 [CQ:image,file=...] [CQ:reply,id=...] [CQ:at,qq=...] [CQ:face,id=...] 等
CQ_CODE_PATTERN = re.compile(r'\[CQ:[^\]]*\]')


def strip_cq_codes(text):
    """移除文本中的 [CQ:xxx,...] OneBot 协议占位符"""
    if not text:
        return text
    return CQ_CODE_PATTERN.sub('', text)


def finalize_message_content(message_lines):
    """把累计的消息行拼接、剥离 CQ 码、去首尾空白。

    Returns:
        str: 最终内容（可能为空字符串）
    """
    if not message_lines:
        return ''
    return strip_cq_codes('\n'.join(message_lines)).strip()


def is_separator_line(line):
    """检测是否为日志分隔符"""
    separators = [
        '.log off', '.logoff', '。log off', '。logoff',
        '/log off', '/logoff', '===日志开始===', '===日志结束==='
    ]
    return any(sep in line for sep in separators) or bool(re.match(r'={3,}.*={3,}', line))


def parse_datetime_format1_2(line, format_type):
    """从format1/2格式的行中解析日期时间"""
    try:
        if format_type == "format1":
            match = re.search(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
            if match:
                return datetime.strptime(match.group(1), '%Y-%m-%d %H:%M:%S')
        else:  # format2
            match = re.search(r'(\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2})', line)
            if match:
                return datetime.strptime(match.group(1), '%Y/%m/%d %H:%M:%S')
    except ValueError:
        # 跳过无效的日期时间（如 1970-00-00 00:00:00）
        return None
    return None


def should_split_day_by_time_gap(prev_dt, current_dt, threshold_hours=TIME_GAP_THRESHOLD_HOURS):
    """判断两个时间戳之间的间隔是否超过阈值，需要分天"""
    if prev_dt is None or current_dt is None:
        return False
    time_gap = current_dt - prev_dt
    return time_gap > timedelta(hours=threshold_hours)


def parse_time_format3_4(time_str):
    """从format3/4格式的时间字符串(HH:MM:SS)解析为datetime对象
    由于没有日期信息，使用固定日期（如1970-01-01），并处理跨天情况"""
    if not time_str:
        return None
    try:
        # 使用固定日期1970-01-01，只关注时间部分
        return datetime.strptime(f"1970-01-01 {time_str}", "%Y-%m-%d %H:%M:%S")
    except:
        return None


def should_split_day_by_time_gap_format34(prev_time_str, current_time_str, threshold_hours=TIME_GAP_THRESHOLD_HOURS):
    """针对format3/4的时间间隔判断，处理跨天情况"""
    if not prev_time_str or not current_time_str:
        return False

    prev_dt = parse_time_format3_4(prev_time_str)
    current_dt = parse_time_format3_4(current_time_str)

    if prev_dt is None or current_dt is None:
        return False

    # 如果当前时间小于前一个时间，说明跨天了（例如23:00 -> 01:00）
    if current_dt < prev_dt:
        # 将当前时间加一天
        current_dt += timedelta(days=1)

    time_gap = current_dt - prev_dt
    return time_gap > timedelta(hours=threshold_hours)


def parse_datetime_format5(line):
    """从format5格式的行中解析时间（只有时间，无日期）
    格式: 用户名(ID) HH:MM:SS
    """
    try:
        match = re.search(r'(\d{2}:\d{2}:\d{2})', line)
        if match:
            # 使用固定日期1970-01-01，只关注时间部分
            return datetime.strptime(f"1970-01-01 {match.group(1)}", "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
    return None


def should_split_day_by_time_gap_format5(prev_dt, current_dt, threshold_hours=TIME_GAP_THRESHOLD_HOURS):
    """针对format5的时间间隔判断，处理跨天情况"""
    if prev_dt is None or current_dt is None:
        return False

    # 如果当前时间小于前一个时间，说明跨天了（例如23:00 -> 01:00）
    if current_dt < prev_dt:
        # 将当前时间加一天
        current_dt += timedelta(days=1)

    time_gap = current_dt - prev_dt
    return time_gap > timedelta(hours=threshold_hours)


def calculate_participation_time(timestamps, idle_threshold_minutes=IDLE_THRESHOLD_MINUTES):
    """计算参与时长(分钟),只累加活跃时间段

    计算逻辑:
    只累加间隔 ≤ 阈值的时间段,超过阈值的间隔跳过

    Args:
        timestamps: datetime对象列表,按时间排序
        idle_threshold_minutes: 休息阈值(分钟),超过此时间视为休息,不计入

    Returns:
        int: 参与时长(分钟)
    """
    if not timestamps:
        return 0

    # 过滤掉None值并排序
    valid_timestamps = [ts for ts in timestamps if ts is not None]
    if len(valid_timestamps) < 1:
        return 0

    # 只有一条消息,给予5分钟活跃时间
    if len(valid_timestamps) == 1:
        return 5

    valid_timestamps.sort()

    # 只累加不超过阈值的间隔
    participation_minutes = 0
    for i in range(len(valid_timestamps) - 1):
        gap = (valid_timestamps[i + 1] - valid_timestamps[i]).total_seconds() / 60

        # 如果间隔不超过阈值,计入参与时长
        if gap <= idle_threshold_minutes:
            participation_minutes += gap

    # 最后一条消息也给予1分钟活跃时间
    participation_minutes += 1

    return int(participation_minutes)


def _record_message(daily_stats, dialogue_contents, current_day, current_speaker,
                    current_message, current_date, current_timestamp):
    """统一收尾：拼接 + 过滤 CQ 码 + 计入统计 + 保存对话内容。

    内容过滤后为空时，整条消息被忽略（既不计数也不保存）。
    """
    if not current_speaker or not current_message:
        return
    content = strip_cq_codes('\n'.join(current_message)).strip()
    if not content:
        return
    is_ooc = bool(re.search(r'[（(]', content))
    if is_ooc:
        daily_stats[current_day][current_speaker]['ooc_messages'] += 1
        daily_stats[current_day][current_speaker]['ooc_chars'] += count_char_weight(content)
    else:
        daily_stats[current_day][current_speaker]['messages'] += 1
        daily_stats[current_day][current_speaker]['chars'] += count_char_weight(content)

    dialogue_contents[current_speaker].append({
        'day': current_day,
        'date': current_date,
        'content': content,
        'is_ooc': is_ooc,
        'timestamp': current_timestamp,
    })


def parse_log_file(file_path="log.txt"):
    """从文件中统计对话信息，支持五种格式，并返回每个角色的具体对话内容

    Args:
        file_path: 日志文件路径

    Returns:
        tuple: (daily_stats, dialogue_contents)
            - daily_stats: 每日统计数据字典
            - dialogue_contents: 每个角色的具体对话内容列表
    """
    daily_stats = defaultdict(lambda: defaultdict(lambda: {
        'messages': 0,
        'chars': 0,
        'ooc_messages': 0,
        'ooc_chars': 0,
        'participation_minutes': 0  # 参与时长(分钟),仅format1/2有效
    }))

    # 存储每个角色的具体对话内容
    dialogue_contents = defaultdict(list)

    current_day = 1
    current_speaker = None
    current_message = []
    current_date = None
    current_timestamp = None
    prev_datetime = None  # 用于计算时间间隔

    # 检测文件格式
    format_type = detect_format(file_path)
    print(f"检测到{format_type}格式日志文件")

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                if format_type in ["format1", "format2"]:  # 处理格式1和格式2（带日期时间戳）
                    # 首先检查是否为分隔符
                    if is_separator_line(line):
                        # 处理当前未处理的消息
                        if current_speaker and current_message:
                            content = strip_cq_codes('\n'.join(current_message)).strip()
                            if content:
                                is_ooc = bool(re.search(r'[（(]', content))
                                if is_ooc:
                                    daily_stats[current_day][current_speaker]['ooc_messages'] += 1
                                    daily_stats[current_day][current_speaker]['ooc_chars'] += count_char_weight(content)
                                else:
                                    daily_stats[current_day][current_speaker]['messages'] += 1
                                    daily_stats[current_day][current_speaker]['chars'] += count_char_weight(content)

                                # 保存对话内容
                                dialogue_contents[current_speaker].append({
                                    'day': current_day,
                                    'date': current_date,
                                    'content': content,
                                    'is_ooc': is_ooc,
                                    'timestamp': current_timestamp
                                })
                        current_speaker = None
                        current_message = []
                        current_day += 1
                        prev_datetime = None  # 重置时间戳
                        continue

                    # 尝试解析当前行的时间戳
                    current_dt = parse_datetime_format1_2(line, format_type)

                    # 检查长时间间隔分天
                    if current_dt and should_split_day_by_time_gap(prev_datetime, current_dt):
                        # 处理前一条消息
                        if current_speaker and current_message:
                            content = strip_cq_codes('\n'.join(current_message)).strip()
                            if content:
                                is_ooc = bool(re.search(r'[（(]', content))
                                if is_ooc:
                                    daily_stats[current_day][current_speaker]['ooc_messages'] += 1
                                    daily_stats[current_day][current_speaker]['ooc_chars'] += count_char_weight(content)
                                else:
                                    daily_stats[current_day][current_speaker]['messages'] += 1
                                    daily_stats[current_day][current_speaker]['chars'] += count_char_weight(content)

                                # 保存对话内容
                                dialogue_contents[current_speaker].append({
                                    'day': current_day,
                                    'date': current_date,
                                    'content': content,
                                    'is_ooc': is_ooc,
                                    'timestamp': current_timestamp
                                })
                        # 切换到新的一天
                        current_day += 1
                        current_speaker = None
                        current_message = []

                    # 更新日期和时间戳
                    if current_dt:
                        prev_datetime = current_dt
                        date_pattern = r'\d{4}-\d{2}-\d{2}' if format_type == "format1" else r'\d{4}/\d{2}/\d{2}'
                        date_match = re.search(date_pattern, line)
                        if date_match:
                            current_date = date_match.group(0)

                    # 匹配格式1或格式2的发言行，根据格式类型使用不同的正则
                    speaker_pattern = r'(.+?)\((\d+)\) \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}' if format_type == "format1" else r'(.+?)\((\d+)\) \d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}'
                    speaker_match = re.match(speaker_pattern, line)
                    if speaker_match:
                        # 处理前一条消息
                        if current_speaker and current_message:
                            content = strip_cq_codes('\n'.join(current_message)).strip()
                            if content:
                                is_ooc = bool(re.search(r'[（(]', content))
                                if is_ooc:
                                    daily_stats[current_day][current_speaker]['ooc_messages'] += 1
                                    daily_stats[current_day][current_speaker]['ooc_chars'] += count_char_weight(content)
                                else:
                                    daily_stats[current_day][current_speaker]['messages'] += 1
                                    daily_stats[current_day][current_speaker]['chars'] += count_char_weight(content)

                                # 保存对话内容
                                dialogue_contents[current_speaker].append({
                                    'day': current_day,
                                    'date': current_date,
                                    'content': content,
                                    'is_ooc': is_ooc,
                                    'timestamp': current_timestamp
                                })

                        current_speaker = normalize_speaker_name(speaker_match.group(1))
                        current_timestamp = line
                        current_message = []
                    else:
                        # 如果已有当前发言者，则这行是消息内容
                        if current_speaker:
                            current_message.append(line)

                elif format_type in ["format3", "format4"]:  # 处理格式3和格式4（基于时间戳的格式）
                    # 首先检查是否是日志分隔符，表示新的一天
                    if is_separator_line(line):
                        # 处理当前未处理的消息
                        if current_speaker and current_message:
                            content = strip_cq_codes('\n'.join(current_message)).strip()
                            if content:
                                is_ooc = bool(re.search(r'[（(]', content))
                            if is_ooc:
                                daily_stats[current_day][current_speaker]['ooc_messages'] += 1
                                daily_stats[current_day][current_speaker]['ooc_chars'] += count_char_weight(content)
                            else:
                                daily_stats[current_day][current_speaker]['messages'] += 1
                                daily_stats[current_day][current_speaker]['chars'] += count_char_weight(content)

                            # 保存对话内容
                            dialogue_contents[current_speaker].append({
                                'day': current_day,
                                'date': None,  # 格式3和格式4没有日期字段
                                'content': content,
                                'is_ooc': is_ooc,
                                'timestamp': f"第{current_day}天"  # 使用天数作为时间戳
                            })
                        current_speaker = None
                        current_message = []
                        current_day += 1
                        prev_datetime = None  # 重置时间戳
                        continue

                    if format_type == "format3":
                        # 处理格式3：时间 <用户名>消息内容
                        match = re.match(r'(\d{2}:\d{2}:\d{2}) <([^>]+)>(.*)', line)
                        if match:
                            current_time = match.group(1)

                            # 检查长时间间隔分天
                            if 'prev_timestamp' in locals() and prev_timestamp:
                                if should_split_day_by_time_gap_format34(prev_timestamp, current_time):
                                    # 处理前一条消息
                                    if current_speaker and current_message:
                                        content = strip_cq_codes('\n'.join(current_message)).strip()
                                        is_ooc = bool(re.search(r'[（(]', content))
                                        if is_ooc:
                                            daily_stats[current_day][current_speaker]['ooc_messages'] += 1
                                            daily_stats[current_day][current_speaker]['ooc_chars'] += count_char_weight(content)
                                        else:
                                            daily_stats[current_day][current_speaker]['messages'] += 1
                                            daily_stats[current_day][current_speaker]['chars'] += count_char_weight(content)

                                        # 保存对话内容
                                        dialogue_contents[current_speaker].append({
                                            'day': current_day,
                                            'date': None,  # 格式3和格式4没有日期字段
                                            'content': content,
                                            'is_ooc': is_ooc,
                                            'timestamp': f"第{current_day}天 {prev_timestamp}"
                                        })
                                    # 分天，增加天数
                                    current_day += 1
                                    current_speaker = None
                                    current_message = []

                            # 处理前一条消息（如果不是跨天情况）
                            if current_speaker and current_message:
                                content = strip_cq_codes('\n'.join(current_message)).strip()
                                is_ooc = bool(re.search(r'[（(]', content))
                                if is_ooc:
                                    daily_stats[current_day][current_speaker]['ooc_messages'] += 1
                                    daily_stats[current_day][current_speaker]['ooc_chars'] += count_char_weight(content)
                                else:
                                    daily_stats[current_day][current_speaker]['messages'] += 1
                                    daily_stats[current_day][current_speaker]['chars'] += count_char_weight(content)

                                # 保存对话内容
                                dialogue_contents[current_speaker].append({
                                    'day': current_day,
                                    'date': None,  # 格式3和格式4没有日期字段
                                    'content': content,
                                    'is_ooc': is_ooc,
                                    'timestamp': f"第{current_day}天 {prev_timestamp if 'prev_timestamp' in locals() else ''}"
                                })

                            prev_timestamp = match.group(1)
                            current_speaker = normalize_speaker_name(match.group(2))
                            current_message = [match.group(3).strip()]
                        else:
                            if current_speaker and line:
                                current_message.append(line)
                    else:
                        # 匹配格式4发言行：时间<用户名>:消息内容
                        match = re.match(r'(?:(\d{2}:\d{2}:\d{2}))?<([^>]+)>:(.*)', line)
                        if match:
                            current_time = match.group(1) if match.group(1) else ""

                            # 检查长时间间隔分天
                            if current_time and 'prev_timestamp' in locals() and prev_timestamp:
                                if should_split_day_by_time_gap_format34(prev_timestamp, current_time):
                                    # 处理前一条消息
                                    if current_speaker and current_message:
                                        content = strip_cq_codes('\n'.join(current_message)).strip()
                                        is_ooc = bool(re.search(r'[（(]', content))
                                        if is_ooc:
                                            daily_stats[current_day][current_speaker]['ooc_messages'] += 1
                                            daily_stats[current_day][current_speaker]['ooc_chars'] += count_char_weight(content)
                                        else:
                                            daily_stats[current_day][current_speaker]['messages'] += 1
                                            daily_stats[current_day][current_speaker]['chars'] += count_char_weight(content)

                                        # 保存对话内容
                                        dialogue_contents[current_speaker].append({
                                            'day': current_day,
                                            'date': None,  # 格式3和格式4没有日期字段
                                            'content': content,
                                            'is_ooc': is_ooc,
                                            'timestamp': f"第{current_day}天 {prev_timestamp}"
                                        })
                                    # 分天，增加天数
                                    current_day += 1
                                    current_speaker = None
                                    current_message = []

                            # 处理前一条消息（如果不是跨天情况）
                            if current_speaker and current_message:
                                content = strip_cq_codes('\n'.join(current_message)).strip()
                                is_ooc = bool(re.search(r'[（(]', content))
                                if is_ooc:
                                    daily_stats[current_day][current_speaker]['ooc_messages'] += 1
                                    daily_stats[current_day][current_speaker]['ooc_chars'] += count_char_weight(content)
                                else:
                                    daily_stats[current_day][current_speaker]['messages'] += 1
                                    daily_stats[current_day][current_speaker]['chars'] += count_char_weight(content)

                                # 保存对话内容
                                dialogue_contents[current_speaker].append({
                                    'day': current_day,
                                    'date': None,  # 格式3和格式4没有日期字段
                                    'content': content,
                                    'is_ooc': is_ooc,
                                    'timestamp': f"第{current_day}天 {prev_timestamp if 'prev_timestamp' in locals() else ''}"
                                })

                            prev_timestamp = match.group(1) if match.group(1) else ""
                            current_speaker = normalize_speaker_name(match.group(2))
                            current_message = [match.group(3).strip()]
                        else:
                            if current_speaker and line:
                                current_message.append(line)

                elif format_type == "format5":  # 处理格式5: 用户名(ID) HH:MM:SS
                    # 跳过 [mirai: 开头的系统消息
                    if line.startswith('[mirai:'):
                        continue

                    # 首先检查是否为分隔符
                    if is_separator_line(line):
                        # 处理当前未处理的消息
                        if current_speaker and current_message:
                            content = strip_cq_codes('\n'.join(current_message)).strip()
                            if content:
                                is_ooc = bool(re.search(r'[（(]', content))
                            if is_ooc:
                                daily_stats[current_day][current_speaker]['ooc_messages'] += 1
                                daily_stats[current_day][current_speaker]['ooc_chars'] += count_char_weight(content)
                            else:
                                daily_stats[current_day][current_speaker]['messages'] += 1
                                daily_stats[current_day][current_speaker]['chars'] += count_char_weight(content)

                            # 保存对话内容
                            dialogue_contents[current_speaker].append({
                                'day': current_day,
                                'date': None,  # format5 没有日期字段
                                'content': content,
                                'is_ooc': is_ooc,
                                'timestamp': current_timestamp
                            })
                        current_speaker = None
                        current_message = []
                        current_day += 1
                        prev_datetime = None  # 重置时间戳
                        continue

                    # 尝试解析当前行的时间戳
                    current_dt = parse_datetime_format5(line)

                    # 检查长时间间隔分天
                    if current_dt and should_split_day_by_time_gap_format5(prev_datetime, current_dt):
                        # 处理前一条消息
                        if current_speaker and current_message:
                            content = strip_cq_codes('\n'.join(current_message)).strip()
                            if content:
                                is_ooc = bool(re.search(r'[（(]', content))
                            if is_ooc:
                                daily_stats[current_day][current_speaker]['ooc_messages'] += 1
                                daily_stats[current_day][current_speaker]['ooc_chars'] += count_char_weight(content)
                            else:
                                daily_stats[current_day][current_speaker]['messages'] += 1
                                daily_stats[current_day][current_speaker]['chars'] += count_char_weight(content)

                            # 保存对话内容
                            dialogue_contents[current_speaker].append({
                                'day': current_day,
                                'date': None,
                                'content': content,
                                'is_ooc': is_ooc,
                                'timestamp': current_timestamp
                            })
                        # 切换到新的一天
                        current_day += 1
                        current_speaker = None
                        current_message = []

                    # 更新时间戳
                    if current_dt:
                        prev_datetime = current_dt

                    # 匹配格式5的发言行: 用户名(ID) HH:MM:SS
                    speaker_match = re.match(r'(.+?)\((\d+)\) \d{2}:\d{2}:\d{2}', line)
                    if speaker_match:
                        # 处理前一条消息
                        if current_speaker and current_message:
                            content = strip_cq_codes('\n'.join(current_message)).strip()
                            if content:
                                is_ooc = bool(re.search(r'[（(]', content))
                            if is_ooc:
                                daily_stats[current_day][current_speaker]['ooc_messages'] += 1
                                daily_stats[current_day][current_speaker]['ooc_chars'] += count_char_weight(content)
                            else:
                                daily_stats[current_day][current_speaker]['messages'] += 1
                                daily_stats[current_day][current_speaker]['chars'] += count_char_weight(content)

                            # 保存对话内容
                            dialogue_contents[current_speaker].append({
                                'day': current_day,
                                'date': None,
                                'content': content,
                                'is_ooc': is_ooc,
                                'timestamp': current_timestamp
                            })

                        current_speaker = normalize_speaker_name(speaker_match.group(1))
                        current_timestamp = line
                        current_message = []
                    else:
                        # 如果已有当前发言者，则这行是消息内容
                        if current_speaker:
                            current_message.append(line)

    except FileNotFoundError:
        print(f"警告: 文件 {file_path} 未找到")

    # 处理最后一条消息
    if current_speaker and current_message:
        content = strip_cq_codes('\n'.join(current_message)).strip()
        is_ooc = bool(re.search(r'[（(]', content))

        if is_ooc:
            daily_stats[current_day][current_speaker]['ooc_messages'] += 1
            daily_stats[current_day][current_speaker]['ooc_chars'] += count_char_weight(content)
        else:
            daily_stats[current_day][current_speaker]['messages'] += 1
            daily_stats[current_day][current_speaker]['chars'] += count_char_weight(content)

        # 保存最后一条消息
        dialogue_contents[current_speaker].append({
            'day': current_day,
            'date': current_date,
            'content': content,
            'is_ooc': is_ooc,
            'timestamp': f"第{current_day}天" if format_type in ["format3", "format4"] else f"第{current_day}天 {current_date}"
        })

    # 计算每个角色每天的参与时长 (format1/2/5有精确时间戳)
    if format_type in ["format1", "format2", "format5"]:
        for speaker, dialogues in dialogue_contents.items():
            # 按天分组时间戳
            timestamps_by_day = defaultdict(list)
            for dialogue in dialogues:
                day = dialogue['day']
                timestamp_str = dialogue.get('timestamp', '')
                # 从timestamp字符串中解析datetime
                if format_type in ["format1", "format2"]:
                    dt = parse_datetime_format1_2(timestamp_str, format_type)
                else:  # format5
                    dt = parse_datetime_format5(timestamp_str)
                if dt:
                    timestamps_by_day[day].append(dt)

            # 计算每天的参与时长
            for day, timestamps in timestamps_by_day.items():
                participation_minutes = calculate_participation_time(timestamps)
                daily_stats[day][speaker]['participation_minutes'] = participation_minutes

    return daily_stats, dialogue_contents
