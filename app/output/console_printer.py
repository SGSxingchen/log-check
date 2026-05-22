"""终端控制台输出模块"""
from collections import defaultdict
from utils import get_display_width, pad_string


def print_summary_stats(daily_stats):
    """打印汇总统计数据"""
    total_stats = defaultdict(lambda: {
        'messages': 0,
        'chars': 0,
        'ooc_messages': 0,
        'ooc_chars': 0,
        'participation_minutes': 0
    })

    # 计算总计数据
    has_participation_time = False
    for day_stats in daily_stats.values():
        for speaker, stats in day_stats.items():
            total_stats[speaker]['messages'] += stats['messages']
            total_stats[speaker]['chars'] += stats['chars']
            total_stats[speaker]['ooc_messages'] += stats['ooc_messages']
            total_stats[speaker]['ooc_chars'] += stats['ooc_chars']
            total_stats[speaker]['participation_minutes'] += stats.get('participation_minutes', 0)
            if stats.get('participation_minutes', 0) > 0:
                has_participation_time = True

    # 表头
    name_width = 30  # 角色名列宽
    num_width = 10   # 数字列宽

    if has_participation_time:
        # 包含参与时长列
        print("=" * 100)
        print("角色对话统计")
        print("=" * 100)
        print(pad_string('角色名', name_width) + ' '.join(pad_string(col, num_width, 'right') for col in ['总发言数', '总字数', '平均字数', '场外次数', '场外字数', '参与时长']))
        print("-" * 100)

        # 按总发言数排序并打印数据
        for speaker, stats in sorted(total_stats.items(),
                                   key=lambda x: x[1]['messages'],
                                   reverse=True):
            avg_chars = stats['chars'] / stats['messages'] if stats['messages'] > 0 else 0
            # 格式化时长为 "X小时Y分钟"
            hours = stats['participation_minutes'] // 60
            minutes = stats['participation_minutes'] % 60
            time_str = f"{hours}h{minutes}m" if hours > 0 else f"{minutes}m"

            print(pad_string(speaker, name_width) +
                  pad_string(str(stats['messages']), num_width, 'right') +
                  pad_string(str(stats['chars']), num_width, 'right') +
                  pad_string(f"{avg_chars:.1f}", num_width, 'right') +
                  pad_string(str(stats['ooc_messages']), num_width, 'right') +
                  pad_string(str(stats['ooc_chars']), num_width, 'right') +
                  pad_string(time_str, num_width, 'right'))
        print("=" * 100)
    else:
        # 不包含参与时长列(format3/4)
        print("=" * 80)
        print("角色对话统计")
        print("=" * 80)
        print(pad_string('角色名', name_width) + ' '.join(pad_string(col, num_width, 'right') for col in ['总发言数', '总字数', '平均字数', '场外次数', '场外字数']))
        print("-" * 80)

        # 按总发言数排序并打印数据
        for speaker, stats in sorted(total_stats.items(),
                                   key=lambda x: x[1]['messages'],
                                   reverse=True):
            avg_chars = stats['chars'] / stats['messages'] if stats['messages'] > 0 else 0
            print(pad_string(speaker, name_width) +
                  pad_string(str(stats['messages']), num_width, 'right') +
                  pad_string(str(stats['chars']), num_width, 'right') +
                  pad_string(f"{avg_chars:.1f}", num_width, 'right') +
                  pad_string(str(stats['ooc_messages']), num_width, 'right') +
                  pad_string(str(stats['ooc_chars']), num_width, 'right'))
        print("=" * 80)
