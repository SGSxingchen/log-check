"""CSV报表生成模块"""
import csv
from collections import defaultdict
from .excel_generator import generate_excel


def generate_csv(daily_stats, dialogue_contents, output_file="对话统计.csv"):
    """生成统计数据的CSV文件，并输出Excel文件"""
    total_stats = defaultdict(lambda: {
        'messages': 0,
        'chars': 0,
        'ooc_messages': 0,
        'ooc_chars': 0,
        'participation_minutes': 0
    })

    # 计算总计数据并检查是否有参与时长数据
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
    
    try:
        # 生成CSV文件
        with open(output_file, 'w', newline='', encoding='utf-8-sig') as csvfile:
            writer = csv.writer(csvfile)
            
            # 写入总体统计数据
            writer.writerow(['总体统计'])
            if has_participation_time:
                writer.writerow(['角色名', '总发言数', '总字数', '平均字数', '场外次数', '场外字数', '参与时长'])
            else:
                writer.writerow(['角色名', '总发言数', '总字数', '平均字数', '场外次数', '场外字数'])

            for speaker, stats in sorted(total_stats.items(),
                                      key=lambda x: x[1]['messages'],
                                      reverse=True):
                avg_chars = stats['chars'] / stats['messages'] if stats['messages'] > 0 else 0
                row = [
                    speaker,
                    stats['messages'],
                    stats['chars'],
                    f"{avg_chars:.1f}",
                    stats['ooc_messages'],
                    stats['ooc_chars']
                ]
                if has_participation_time:
                    # 格式化时长为 "X小时Y分钟"
                    hours = stats['participation_minutes'] // 60
                    minutes = stats['participation_minutes'] % 60
                    time_str = f"{hours}小时{minutes}分钟" if hours > 0 else f"{minutes}分钟"
                    row.append(time_str)
                writer.writerow(row)
            
            # 添加空行
            writer.writerow([])
            
            # 写入按日统计数据
            for day, day_stats in sorted(daily_stats.items()):
                writer.writerow([f'第{day}天统计'])
                if has_participation_time:
                    writer.writerow(['角色名', '发言数', '字数', '平均字数', '场外次数', '场外字数', '参与时长'])
                else:
                    writer.writerow(['角色名', '发言数', '字数', '平均字数', '场外次数', '场外字数'])

                daily_total = defaultdict(int)

                for speaker, stats in sorted(day_stats.items(),
                                         key=lambda x: x[1]['messages'],
                                         reverse=True):
                    avg_chars = stats['chars'] / stats['messages'] if stats['messages'] > 0 else 0
                    row = [
                        speaker,
                        stats['messages'],
                        stats['chars'],
                        f"{avg_chars:.1f}",
                        stats['ooc_messages'],
                        stats['ooc_chars']
                    ]
                    if has_participation_time:
                        hours = stats.get('participation_minutes', 0) // 60
                        minutes = stats.get('participation_minutes', 0) % 60
                        time_str = f"{hours}小时{minutes}分钟" if hours > 0 else f"{minutes}分钟"
                        row.append(time_str)
                    writer.writerow(row)

                    # 累计当日总数
                    daily_total['messages'] += stats['messages']
                    daily_total['chars'] += stats['chars']
                    daily_total['ooc_messages'] += stats['ooc_messages']
                    daily_total['ooc_chars'] += stats['ooc_chars']
                    daily_total['participation_minutes'] += stats.get('participation_minutes', 0)

                # 写入当日总计
                avg_chars_total = daily_total['chars'] / daily_total['messages'] if daily_total['messages'] > 0 else 0
                row_total = [
                    '当日总计',
                    daily_total['messages'],
                    daily_total['chars'],
                    f"{avg_chars_total:.1f}",
                    daily_total['ooc_messages'],
                    daily_total['ooc_chars']
                ]
                if has_participation_time:
                    hours = daily_total['participation_minutes'] // 60
                    minutes = daily_total['participation_minutes'] % 60
                    time_str = f"{hours}小时{minutes}分钟" if hours > 0 else f"{minutes}分钟"
                    row_total.append(time_str)
                writer.writerow(row_total)

                # 添加空行
                writer.writerow([])

        print(f"CSV文件已生成：{output_file}")

        # 生成Excel文件，包含统计数据和对话内容
        if output_file.endswith('.csv'):
            excel_file = output_file.replace('.csv', '.xlsx')
        else:
            excel_file = output_file + '.xlsx'

        generate_excel(daily_stats, dialogue_contents, excel_file)

    except Exception as e:
        print(f"生成文件时出错：{e}")
                
