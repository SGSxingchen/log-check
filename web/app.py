"""
角色对话统计工具 - Web应用
"""

import os
import sys
import io
from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_file
from werkzeug.utils import secure_filename
import uuid

# 修复 Windows 下的编码问题
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# 添加项目根目录和app目录到路径，以便导入app模块
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
app_dir = os.path.join(project_root, 'app')
sys.path.insert(0, project_root)
sys.path.insert(0, app_dir)

from parser.log_parser import parse_log_file
from output.excel_generator import generate_excel

app = Flask(__name__)

# 配置
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'uploads')
OUTPUT_FOLDER = os.path.join(os.path.dirname(__file__), 'generated')
ALLOWED_EXTENSIONS = {'txt'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['OUTPUT_FOLDER'] = OUTPUT_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# 确保文件夹存在
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)


def allowed_file(filename):
    """检查文件扩展名是否允许"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def format_time_display(minutes):
    """格式化时间显示"""
    if minutes == 0:
        return "0分钟"
    hours = minutes // 60
    mins = minutes % 60
    if hours > 0:
        return f"{hours}小时{mins}分钟"
    return f"{mins}分钟"


@app.route('/')
def index():
    """主页"""
    return render_template('index.html')


@app.route('/api/upload', methods=['POST'])
def upload_file():
    """
    处理文件上传和分析
    返回统计结果JSON
    """
    if 'file' not in request.files:
        return jsonify({'error': '没有上传文件'}), 400

    file = request.files['file']

    if file.filename == '':
        return jsonify({'error': '未选择文件'}), 400

    if not allowed_file(file.filename):
        return jsonify({'error': '只支持 .txt 格式的日志文件'}), 400

    try:
        # 保存上传的文件
        filename = secure_filename(file.filename)
        unique_id = str(uuid.uuid4())
        upload_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{unique_id}_{filename}")
        file.save(upload_path)

        # 解析日志文件
        daily_stats, dialogue_contents = parse_log_file(upload_path)

        # 生成Excel文件
        base_filename = os.path.splitext(filename)[0]
        excel_filename = f"{base_filename}.xlsx"
        excel_path = os.path.join(app.config['OUTPUT_FOLDER'], f"{unique_id}_{excel_filename}")

        generate_excel(daily_stats, dialogue_contents, excel_path)

        # 计算总计数据
        from collections import defaultdict
        total_stats = defaultdict(lambda: {
            'messages': 0,
            'chars': 0,
            'ooc_messages': 0,
            'ooc_chars': 0,
            'participation_minutes': 0
        })

        for day_stats_data in daily_stats.values():
            for speaker, stats in day_stats_data.items():
                total_stats[speaker]['messages'] += stats['messages']
                total_stats[speaker]['chars'] += stats['chars']
                total_stats[speaker]['ooc_messages'] += stats['ooc_messages']
                total_stats[speaker]['ooc_chars'] += stats['ooc_chars']
                total_stats[speaker]['participation_minutes'] += stats.get('participation_minutes', 0)

        # 准备返回的统计数据
        stats_list = []

        # 添加总计统计
        total_list = []
        for name, data in sorted(total_stats.items(), key=lambda x: x[1]['messages'], reverse=True):
            avg_chars = data['chars'] / data['messages'] if data['messages'] > 0 else 0

            stat_item = {
                '角色名': name,
                '总发言数': data['messages'],
                '总字数': data['chars'],
                '平均字数': f"{avg_chars:.1f}",
                '场外次数': data['ooc_messages'],
                '场外字数': data['ooc_chars']
            }

            # 添加参与时长（如果有）
            if data['participation_minutes'] > 0:
                stat_item['参与时长'] = format_time_display(data['participation_minutes'])

            total_list.append(stat_item)

        stats_list.append({
            'day': '总计',
            'stats': total_list
        })

        # 添加每日统计
        for day_key, stats in sorted(daily_stats.items()):
            day_stats = []
            for name, data in sorted(stats.items(), key=lambda x: x[1]['messages'], reverse=True):
                # 计算平均字数
                avg_chars = data['chars'] / data['messages'] if data['messages'] > 0 else 0

                stat_item = {
                    '角色名': name,
                    '总发言数': data['messages'],
                    '总字数': data['chars'],
                    '平均字数': f"{avg_chars:.1f}",
                    '场外次数': data['ooc_messages'],
                    '场外字数': data['ooc_chars']
                }

                # 添加参与时长（如果有）
                if 'participation_minutes' in data and data['participation_minutes'] > 0:
                    stat_item['参与时长'] = format_time_display(data['participation_minutes'])

                day_stats.append(stat_item)

            stats_list.append({
                'day': f"第{day_key}天",
                'stats': day_stats
            })

        # 清理上传的文件
        os.remove(upload_path)

        return jsonify({
            'success': True,
            'filename': filename,
            'stats': stats_list,
            'download_id': unique_id,
            'excel_filename': excel_filename
        })

    except Exception as e:
        return jsonify({'error': f'处理文件时出错: {str(e)}'}), 500


@app.route('/api/download/<download_id>/<filename>')
def download_file(download_id, filename):
    """下载生成的Excel文件"""
    try:
        file_path = os.path.join(app.config['OUTPUT_FOLDER'], f"{download_id}_{filename}")

        if not os.path.exists(file_path):
            return jsonify({'error': '文件不存在'}), 404

        return send_file(
            file_path,
            as_attachment=True,
            download_name=filename,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )

    except Exception as e:
        return jsonify({'error': f'下载文件时出错: {str(e)}'}), 500


@app.route('/api/cleanup/<download_id>/<filename>', methods=['POST'])
def cleanup_file(download_id, filename):
    """清理生成的文件"""
    try:
        file_path = os.path.join(app.config['OUTPUT_FOLDER'], f"{download_id}_{filename}")
        if os.path.exists(file_path):
            os.remove(file_path)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
