"""
角色对话统计工具 - Web应用
"""

import os
import sys
import io
import csv
import ipaddress
import re
import json
import threading
import urllib.request
import urllib.error
from urllib.parse import urlparse
from collections import defaultdict, Counter
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
from parser.html_log import preprocess_log_file
from output.excel_generator import generate_excel

app = Flask(__name__)

# 配置
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'uploads')
OUTPUT_FOLDER = os.path.join(os.path.dirname(__file__), 'generated')
FEEDBACK_FOLDER = os.path.join(os.path.dirname(__file__), 'feedback')
FEEDBACK_DB = os.path.join(FEEDBACK_FOLDER, 'feedback.json')
FEEDBACK_ATTACH = os.path.join(FEEDBACK_FOLDER, 'attachments')
ALLOWED_EXTENSIONS = {'txt', 'doc', 'docx', 'html', 'htm'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['OUTPUT_FOLDER'] = OUTPUT_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 32 * 1024 * 1024  # 32MB max file size

# 确保文件夹存在
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)
os.makedirs(FEEDBACK_FOLDER, exist_ok=True)
os.makedirs(FEEDBACK_ATTACH, exist_ok=True)
FEEDBACK_LOCK = threading.RLock()

# 中文常见停用词（用于词频分析）
STOPWORDS = set([
    '的', '了', '是', '在', '我', '你', '他', '她', '它', '们',
    '这', '那', '一', '不', '就', '都', '也', '和', '与', '吗',
    '呢', '啊', '吧', '呀', '哦', '嗯', '哈', '没', '有', '会',
    '说', '去', '来', '到', '把', '让', '被', '给', '从', '向',
    '对', '于', '所', '以', '为', '之', '其', '此', '若', '但',
    '可', '能', '要', '想', '觉', '得', '过', '着', '上', '下',
    '里', '外', '前', '后', '中', '间', '时', '候', '什么', '怎么',
    '为什么', '可以', '应该', '已经', '正在', '一个', '我们', '你们',
    '他们', '自己', '现在', '今天', '昨天', '明天', '只是', '还是',
    '或者', '或', '而', '及', '又', '才', '却', '只', '再', '且',
])


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


def is_ai_base_url_allowed(base_url):
    """限制 AI 代理地址，避免服务端被用来探测内网。"""
    try:
        parsed = urlparse((base_url or '').strip())
    except ValueError:
        return False

    if parsed.scheme not in ('http', 'https') or not parsed.hostname:
        return False
    if parsed.username or parsed.password:
        return False

    host = parsed.hostname.lower()
    if host == 'localhost' or host.endswith('.localhost'):
        return True

    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return True

    if ip.is_loopback:
        return True
    return not (
        ip.is_private
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def sanitize_csv_cell(value):
    """防止 Excel 将 CSV 单元格当公式执行。"""
    if value is None:
        return ''
    text = str(value)
    if text and text.lstrip()[:1] in ('=', '+', '-', '@'):
        return "'" + text
    return text


def extract_keywords(text, top_n=20):
    """简单的中文词频分析（基于2-gram）"""
    text = re.sub(r'[（(].*?[）)]', '', text)
    text = re.sub(r'[^一-鿿]', ' ', text)
    chunks = [c for c in text.split() if len(c) >= 2]

    counter = Counter()
    for chunk in chunks:
        for i in range(len(chunk) - 1):
            bigram = chunk[i:i + 2]
            if bigram in STOPWORDS:
                continue
            if any(c in STOPWORDS for c in bigram):
                continue
            counter[bigram] += 1

        if len(chunk) >= 3:
            for i in range(len(chunk) - 2):
                trigram = chunk[i:i + 3]
                if trigram in STOPWORDS:
                    continue
                counter[trigram] += 2

    return counter.most_common(top_n)


def build_speaker_stat(name, data, is_total=False):
    """构建单条角色统计数据"""
    avg_chars = data['chars'] / data['messages'] if data['messages'] > 0 else 0
    stat = {
        '角色名': name,
        '总发言数': data['messages'],
        '总字数': data['chars'],
        '平均字数': round(avg_chars, 1),
        '场外次数': data['ooc_messages'],
        '场外字数': data['ooc_chars'],
    }
    if data.get('participation_minutes', 0) > 0:
        stat['参与时长'] = format_time_display(data['participation_minutes'])
        stat['_minutes'] = data['participation_minutes']
    return stat


@app.route('/')
def index():
    """主页"""
    return render_template('index.html')


def _try_extract_json(text):
    """从文本中尽力提取一个 JSON 对象（兜底解析）

    依次尝试：
      1. 直接 json.loads
      2. 去掉 markdown 代码块包装
      3. 找带 roleplay_score 的 JSON 块
      4. 最大花括号块
    """
    if not text:
        return None
    text = text.strip()

    # 直接尝试
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        pass

    # 去 markdown 代码块
    m = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass

    # 带关键字段的 JSON
    m = re.search(r'\{[^{}]*"roleplay_score"[^{}]*\}', text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass

    # 最大花括号块
    m = re.search(r'\{.*\}', text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass

    return None


@app.route('/api/upload', methods=['POST'])
def upload_file():
    """处理文件上传和分析，返回完整统计结果JSON"""
    if 'file' not in request.files:
        return jsonify({'error': '没有上传文件'}), 400

    file = request.files['file']

    if file.filename == '':
        return jsonify({'error': '未选择文件'}), 400

    if not allowed_file(file.filename):
        return jsonify({'error': '只支持 .txt / .doc / .docx / .html 格式的日志文件'}), 400

    try:
        filename = secure_filename(file.filename)
        unique_id = str(uuid.uuid4())
        upload_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{unique_id}_{filename}")
        file.save(upload_path)

        # 海豹骰 logrender 导出的 HTML log 预处理
        parse_path, was_converted = preprocess_log_file(upload_path)

        daily_stats, dialogue_contents = parse_log_file(parse_path)
        if not any(day_stats for day_stats in daily_stats.values()):
            raise ValueError('未识别到可统计的发言，请确认文件是支持的日志格式；.doc 需为 logrender 导出的 HTML/MHTML 或包含可抽取文本。')

        base_filename = os.path.splitext(filename)[0]
        excel_filename = f"{base_filename}.xlsx"
        excel_path = os.path.join(app.config['OUTPUT_FOLDER'], f"{unique_id}_{excel_filename}")
        generate_excel(daily_stats, dialogue_contents, excel_path)

        # 计算总计数据
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

        # 总计统计
        total_list = []
        for name, data in sorted(total_stats.items(), key=lambda x: x[1]['messages'], reverse=True):
            total_list.append(build_speaker_stat(name, data, is_total=True))

        stats_list = [{'day': '总计', 'stats': total_list}]

        # 每日统计
        for day_key, stats in sorted(daily_stats.items()):
            day_stats = []
            for name, data in sorted(stats.items(), key=lambda x: x[1]['messages'], reverse=True):
                day_stats.append(build_speaker_stat(name, data))
            stats_list.append({
                'day': f"第{day_key}天",
                'stats': day_stats
            })

        # 概览数据
        total_speakers = len(total_stats)
        total_messages = sum(s['messages'] for s in total_stats.values())
        total_chars = sum(s['chars'] for s in total_stats.values())
        total_ooc = sum(s['ooc_messages'] for s in total_stats.values())
        total_minutes = sum(s['participation_minutes'] for s in total_stats.values())
        total_days = len(daily_stats)

        # 对话内容（在线查看）+ 每个角色的额外洞察
        dialogues_payload = {}
        speaker_insights = {}

        for speaker, dialogues in dialogue_contents.items():
            sorted_dialogues = sorted(dialogues, key=lambda x: (x.get('day', 0), x.get('timestamp', '')))
            payload = []
            longest = {'content': '', 'length': 0}
            ic_chars = 0
            ic_count = 0
            ooc_chars_total = 0
            ooc_count = 0
            all_text = []

            for d in sorted_dialogues:
                content = d.get('content', '')
                payload.append({
                    'day': d.get('day', 1),
                    'timestamp': d.get('timestamp', ''),
                    'content': content,
                    'is_ooc': bool(d.get('is_ooc', False))
                })

                length = len(content)
                if not d.get('is_ooc') and length > longest['length']:
                    longest = {'content': content, 'length': length, 'timestamp': d.get('timestamp', '')}

                if d.get('is_ooc'):
                    ooc_count += 1
                    ooc_chars_total += length
                else:
                    ic_count += 1
                    ic_chars += length

                if not d.get('is_ooc'):
                    all_text.append(content)

            dialogues_payload[speaker] = payload

            # 词频分析
            keywords = extract_keywords('\n'.join(all_text), top_n=15)
            speaker_insights[speaker] = {
                'longest_message': longest,
                'avg_ic_length': round(ic_chars / ic_count, 1) if ic_count > 0 else 0,
                'avg_ooc_length': round(ooc_chars_total / ooc_count, 1) if ooc_count > 0 else 0,
                'keywords': [{'word': w, 'count': c} for w, c in keywords]
            }

        # 全局词频分析
        all_text_global = []
        for sp, dialogues in dialogue_contents.items():
            for d in dialogues:
                if not d.get('is_ooc'):
                    all_text_global.append(d.get('content', ''))
        global_keywords = extract_keywords('\n'.join(all_text_global), top_n=30)

        os.remove(upload_path)
        if was_converted:
            try:
                os.remove(parse_path)
            except OSError:
                pass

        return jsonify({
            'success': True,
            'filename': filename,
            'stats': stats_list,
            'overview': {
                'speakers': total_speakers,
                'messages': total_messages,
                'chars': total_chars,
                'ooc_messages': total_ooc,
                'minutes': total_minutes,
                'days': total_days,
                'time_display': format_time_display(total_minutes) if total_minutes > 0 else None
            },
            'dialogues': dialogues_payload,
            'insights': speaker_insights,
            'global_keywords': [{'word': w, 'count': c} for w, c in global_keywords],
            'download_id': unique_id,
            'excel_filename': excel_filename
        })

    except Exception as e:
        for path in {locals().get('upload_path'), locals().get('parse_path')}:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass
        if isinstance(e, ValueError):
            return jsonify({'error': str(e)}), 400
        import traceback
        traceback.print_exc()
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


@app.route('/api/download_csv/<download_id>', methods=['POST'])
def download_csv(download_id):
    """根据前端传入的统计数据生成并下载CSV"""
    try:
        payload = request.get_json() or {}
        stats_list = payload.get('stats', [])
        filename = payload.get('filename', '统计结果.csv')

        csv_path = os.path.join(app.config['OUTPUT_FOLDER'], f"{download_id}_{secure_filename(filename)}")

        with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            for section in stats_list:
                day_name = section.get('day', '')
                stats = section.get('stats', [])
                writer.writerow([f'== {day_name} =='])
                if stats:
                    headers = [k for k in stats[0].keys() if not k.startswith('_')]
                    writer.writerow(headers)
                    for row in stats:
                        writer.writerow([sanitize_csv_cell(row.get(h, '')) for h in headers])
                writer.writerow([])

        return send_file(
            csv_path,
            as_attachment=True,
            download_name=secure_filename(filename),
            mimetype='text/csv'
        )

    except Exception as e:
        return jsonify({'error': f'生成CSV时出错: {str(e)}'}), 500


@app.route('/api/ai_models', methods=['POST'])
def ai_models():
    """通过 OpenAI 兼容 API 或 Anthropic API 拉取可用模型列表

    请求 JSON: {base_url, api_key, provider}
        provider: "openai" (默认) 或 "anthropic"
    响应 JSON: {models: ["model-id", ...]} 或 {error}
    """
    try:
        data = request.get_json(force=True) or {}
        base_url = (data.get('base_url') or '').strip().rstrip('/')
        api_key = (data.get('api_key') or '').strip()
        provider = (data.get('provider') or 'openai').strip().lower()
        if not base_url or not api_key:
            return jsonify({'error': '缺少 base_url 或 api_key'}), 400
        if not is_ai_base_url_allowed(base_url):
            return jsonify({'error': 'Base URL 不允许访问内网、保留地址或无效协议'}), 400

        if provider == 'anthropic':
            url = base_url + '/v1/models'
            headers = {
                'x-api-key': api_key,
                'anthropic-version': '2023-06-01',
            }
        else:
            url = base_url + '/models'
            headers = {'Authorization': f'Bearer {api_key}'}

        req = urllib.request.Request(url, headers=headers, method='GET')
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                resp_data = json.loads(resp.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            err_body = e.read().decode('utf-8', errors='replace')[:300]
            return jsonify({'error': f'API 返回 {e.code}: {err_body}'}), 502
        except urllib.error.URLError as e:
            return jsonify({'error': f'无法连接: {e.reason}'}), 502

        items = resp_data.get('data') or resp_data.get('models') or []
        models = []
        for it in items:
            if isinstance(it, dict):
                mid = it.get('id') or it.get('name') or it.get('model')
                if mid:
                    models.append(str(mid))
            elif isinstance(it, str):
                models.append(it)

        models = sorted(set(models))
        if not models:
            return jsonify({'error': '响应中未找到模型列表', 'raw': resp_data}), 502
        return jsonify({'models': models})

    except Exception as e:
        return jsonify({'error': f'服务器错误: {str(e)}'}), 500


# ============ 评分档位标签 ============
# 与 system_prompt 里的锚点对齐，按分数映射成简短标签

_PL_ROLEPLAY_TIERS = [
    (95, '完美无瑕'),
    (85, '优秀'),
    (75, '良好'),
    (65, '合格'),
    (55, '平淡'),
    (45, '一般'),
    (35, '浮于表面'),
    (25, '出戏严重'),
    (15, '几乎无扮演'),
    (0,  '完全失格'),
]

_PL_IMPACT_TIERS = [
    (95, '主角级'),
    (85, '关键决策者'),
    (75, '主动玩家'),
    (65, '称职队员'),
    (55, '跟随者'),
    (45, '边缘参与'),
    (35, '拖油瓶'),
    (25, '旁观角色'),
    (15, '工具人'),
    (0,  '无贡献'),
]

_KP_ROLEPLAY_TIERS = [
    (95, '小说级叙事'),
    (85, 'NPC 鲜活'),
    (75, '描写充分'),
    (65, '功能合格'),
    (55, '机械描写'),
    (45, '只读设定'),
    (35, '指令为主'),
    (25, '流水账'),
    (15, '剧本目录'),
    (0,  '几乎无叙事'),
]

_KP_IMPACT_TIERS = [
    (95, '掌控全场'),
    (85, '稳压全场'),
    (75, '职责到位'),
    (65, '流畅但被动'),
    (55, '反应迟缓'),
    (45, '裁判随意'),
    (35, '秩序混乱'),
    (25, '只是骰检定'),
    (15, '严重失控'),
    (0,  '完全失职'),
]


def _score_to_tier(score, tiers):
    """根据分数返回档位标签。"""
    for threshold, label in tiers:
        if score >= threshold:
            return label
    return tiers[-1][1]


def _score_to_tier_index(score, tiers):
    """根据分数返回档位序号，10 为最高档（95+），1 为最低档（0-14）。"""
    total = len(tiers)
    for idx, (threshold, _) in enumerate(tiers):
        if score >= threshold:
            return total - idx
    return 1


@app.route('/api/ai_review', methods=['POST'])
def ai_review():
    """为单个角色生成扮演分 / 影响分 / 评语

    使用结构化输出：
      - OpenAI 兼容: response_format=json_schema，强制 JSON Schema
      - Anthropic Claude: tool use + tool_choice，强制调用 submit_review 工具
    """
    try:
        data = request.get_json(force=True) or {}
        base_url = (data.get('base_url') or '').strip().rstrip('/')
        api_key = (data.get('api_key') or '').strip()
        model = (data.get('model') or '').strip()
        provider = (data.get('provider') or 'openai').strip().lower()
        speaker = data.get('speaker') or ''
        samples = data.get('samples') or []
        stats = data.get('stats') or {}
        context = data.get('context') or {}
        is_kp = bool(data.get('is_kp', False))
        # 高级参数（可前端配置）
        max_tokens = int(data.get('max_tokens') or 8192)
        ic_sample_n = int(data.get('ic_sample_n') or 60)
        ooc_sample_n = int(data.get('ooc_sample_n') or 20)
        sample_hard_cap = int(data.get('sample_hard_cap') or 16000)
        temperature = float(data.get('temperature') if data.get('temperature') is not None else 1.0)

        if not base_url or not api_key or not model:
            return jsonify({'error': '缺少 base_url / api_key / model'}), 400
        if not is_ai_base_url_allowed(base_url):
            return jsonify({'error': 'Base URL 不允许访问内网、保留地址或无效协议'}), 400
        if not speaker or not samples:
            return jsonify({'error': '缺少角色或对话样本'}), 400

        # ============ 采样策略 ============
        # 平均、首、中、尾各取一些；优先选长度适中、信息密度高的样本
        ic = [s for s in samples if not s.get('is_ooc')]
        ooc = [s for s in samples if s.get('is_ooc')]

        def smart_sample(arr, max_n, min_len=8, max_len=400):
            """从数组中均匀取样，跳过过短/过长的"""
            if not arr:
                return []
            filtered = [s for s in arr if min_len <= len(s.get('content', '')) <= max_len]
            pool = filtered if len(filtered) >= max_n else arr
            if len(pool) <= max_n:
                return pool
            step = len(pool) / max_n
            return [pool[int(i * step)] for i in range(max_n)]

        ic_picks = smart_sample(ic, ic_sample_n)
        ooc_picks = smart_sample(ooc, ooc_sample_n, min_len=4, max_len=200)

        def fmt(arr, hard_cap=sample_hard_cap):
            buf, total = [], 0
            for s in arr:
                day = s.get('day', '?')
                ts = s.get('timestamp', '')
                # 提取时间戳里的 HH:MM 部分（如果有）
                ts_match = re.search(r'\d{2}:\d{2}(:\d{2})?', str(ts))
                ts_short = ts_match.group(0) if ts_match else ''
                content = (s.get('content') or '').strip().replace('\n', ' ')
                if len(content) > 380:
                    content = content[:380] + '…'
                tag = '[OOC]' if s.get('is_ooc') else '[IC]'
                line = f"D{day} {ts_short} {tag} {content}"
                if total + len(line) > hard_cap:
                    buf.append(f"……(还有 {len(arr) - len(buf)} 条略)")
                    break
                buf.append(line)
                total += len(line) + 1
            return '\n'.join(buf)

        # IC 占大头（约 75%），OOC 占少（25%），保证两者都不会被对方挤掉
        ic_cap = int(sample_hard_cap * 0.75)
        ooc_cap = sample_hard_cap - ic_cap
        ic_text = fmt(ic_picks, hard_cap=ic_cap) if ic_picks else '(无在场发言)'
        ooc_text = fmt(ooc_picks, hard_cap=ooc_cap) if ooc_picks else '(无场外发言)'

        # ============ 提示词 ============
        # ============ 提示词 ============
        if is_kp:
            system_prompt = """你是一位严苛、克制的桌面角色扮演（TRPG/跑团）评论员，本次评价的对象是 **KP（Keeper / 守密人 / DM）**——主持整局团的人。

# 评分原则（必须遵守）

1. **每 10 分一档**，禁止集中在 70-85 区间。请充分使用 0-100 全段。
2. KP 与 PL 的评分维度不同。下方锚点已为 KP 重写，不要套用玩家锚点。
3. 评分必须基于样本中的**具体证据**，不要凭借数据数字脑补。

# 扮演分锚点（KP 版 — 衡量"叙事力"）

KP 的扮演分 = NPC 塑造 + 场景描写 + 氛围营造 + 旁白文学性
- **95-100**: 多个 NPC 各有独立人格、台词鲜活；环境描写有画面感；恐怖/悬疑氛围拿捏精准；旁白如小说。
- **85-94**: NPC 有辨识度、能让玩家记住名字；场景描写丰富；偶有妙笔。
- **75-84**: NPC 形象基本成型但偏脸谱化；环境描写充分但缺少情绪渲染。
- **65-74**: 完成 NPC 必要功能；环境多用简短叙述；偶有亮点。
- **55-64**: NPC 多为传声筒；描写偏机械；以"你看到 XX"开头的句式较多。
- **45-54**: 几乎只读规则书设定；NPC 没有性格；缺乏氛围。
- **35-44**: 基本不写描写，只发指令和检定要求。
- **25-34**: 完全是流水账："出现 X、然后 Y"，无任何文学性。
- **15-24**: 像在念剧本目录，玩家完全感受不到世界。
- **0-14**: 几乎无叙事内容。

# 影响分锚点（KP 版 — 衡量"主持力"）

KP 的影响分 = 节奏掌控 + 应变 + 公平裁判 + 玩家体验
- **95-100**: 节奏张弛有度；面对 PL 意外行动有精彩应对；裁判公正；让所有 PL 都得到聚光灯时间。
- **85-94**: 节奏稳定、能力压全场；有效处理冲突和疑问。
- **75-84**: 完成主持基本职责；规则裁判明确；偶有节奏不稳。
- **65-74**: 主持流畅但被动；多由 PL 推进；少量裁判含糊。
- **55-64**: 反应慢、卡剧本；不擅处理 PL 突发；裁判前后不一致。
- **45-54**: 经常打断节奏；规则裁判随意；偏袒/打压个别 PL。
- **35-44**: 团内秩序混乱；多次冷场；剧情推进困难。
- **25-34**: 几乎不主导，只是骰检定的人。
- **15-24**: 团内严重失控，玩家自顾自玩。
- **0-14**: 完全失职。

# 评分方式

1. 先在脑内默念该 KP 应处于哪一档，写下大致档位
2. 再在该档 ±5 分内调整出最终分
3. 扮演分（叙事力）和影响分（主持力）必须独立给出
4. 点评必须引用至少一条具体台词或场景作为证据，并明确指出关键不足"""
        else:
            system_prompt = """你是一位严苛、克制的桌面角色扮演（TRPG/跑团）评论员，曾担任 KP/DM 多年。本次评价的对象是 **PL（玩家角色）**。你以打分严格、能在不同角色间拉开梯度而著称。

# 评分原则（必须遵守）

1. **每 10 分一档**，禁止集中在 70-85 区间。请充分使用 0-100 全段，让强弱差距清晰可见。
2. 一局团里，扮演分的最高分与最低分之间应至少有 **20-30 分差距**；如果你给所有角色都打 75-85，说明你没有用心区分。
3. **高发言数 ≠ 高扮演分**。话痨堆字数但缺角色感的，应在 50-65 区间；话少但每句都鲜活的，可以给 80+。
4. **本规则允许甚至鼓励场外沟通**，场外比例本身不影响扮演分；只看 IC 部分的角色塑造质量。OOC 仅在挤占 IC 表达、导致 IC 样本过少或全是出戏调侃时才反映为低分。
5. 评分必须基于样本中的**具体证据**，不要凭借数据数字脑补；若样本几乎全是骰子或战斗指令，直接判 30-50。

# 扮演分锚点（PL 版 — 每档 10 分）

PL 的扮演分 = 角色塑造的真实性 + 立体度 + 代入感
- **95-100 完美无瑕**: 角色立体丰满、有标志性台词或习惯、内心动机清晰、有完整情感弧线。
- **85-94 优秀**: 多数 IC 发言贴合角色身份；动作描写、心理刻画、独白俱备；偶有妙笔。
- **75-84 良好**: 角色性格基本成型，有可识别特征；但描写多停留在表层。
- **65-74 合格**: 完成扮演任务，有一定个性；但偏功能性，缺乏深度。
- **55-64 平淡**: 多数发言为信息陈述或骰子操作，少量角色色彩。
- **45-54 一般**: 几乎只关心机制（hp/san/检定）；台词如玩家而非角色。
- **35-44 浮于表面**: 角色名仅是占位符；几乎没有性格或世界观体现。
- **25-34 出戏严重**: 在 IC 场景中也很难看出在扮演谁。
- **15-24 几乎无扮演**: 全是规则讨论、表情包、调侃。
- **0-14 完全失格**: 无任何扮演意图。

# 影响分锚点（PL 版 — 每档 10 分）

PL 的影响分 = 对剧情、团队、其他角色的实际改变力
- **95-100 主角级**: 多次推动核心情节、决定团队走向、与他人形成深刻羁绊或冲突。
- **85-94 关键决策者**: 在重要场合做出有效行动、解决困境、与多位角色建立有意义互动。
- **75-84 主动玩家**: 经常提出方案、有目的性行动、对剧情有正面贡献。
- **65-74 称职队员**: 完成自己的角色职能、配合他人、偶尔主动。
- **55-64 跟随者**: 多数时候被动响应、跟从主角行动；少数时刻有亮点。
- **45-54 边缘参与**: 大量时间旁观或简单附和。
- **35-44 拖油瓶**: 常掉线/沉默/答非所问。
- **25-34 旁观角色**: 几乎不影响剧情走向。
- **15-24 工具人**: 仅在被点名或骰检定时出场。
- **0-14 无贡献**: 几乎不发言或仅有水印式存在。

# 评分方式

1. 先在脑内默念该角色应处于哪一档（不要默认 70-80），写下大致档位
2. 再在该档 ±5 分内调整出最终分
3. 扮演分和影响分必须独立给出（一个角色可以扮演 90 影响 50）
4. 点评必须引用至少一条具体台词或场景作为证据，并明确指出关键不足"""

        role_label = 'KP（守密人/主持人）' if is_kp else 'PL（玩家角色）'
        user_prompt = f"""请评价【{role_label}】「{speaker}」。

# 整局背景
- 在场角色: {context.get('total_speakers', '?')} 位
- 全场总发言: {context.get('total_messages', '?')} 条
- 跨越天数: {context.get('days', '?')} 天

# 该角色定量数据
- 总发言: {stats.get('messages', 0)} 条 (含场外 {stats.get('ooc_messages', 0)} 条)
- 场外比例: {round(stats.get('ooc_messages', 0) / max(stats.get('messages', 1), 1) * 100, 1)}%
- 总字数: {stats.get('chars', 0)}
- 平均字长: {round(stats.get('chars', 0) / max(stats.get('messages', 1), 1), 1)}
- 参与时长: {stats.get('participation_minutes', 0)} 分钟

# 发言样本（已均匀采样，[IC]=在场发言，[OOC]=场外发言，D=第几天）

## 在场发言（{len(ic_picks)}/{len(ic)} 条节选）
{ic_text}

## 场外发言（{len(ooc_picks)}/{len(ooc)} 条节选）
{ooc_text}

# 输出要求

1. **打分要拉开差距** —— 不要默认 70-85，请用 0-100 全段
2. 引用至少一条具体台词或场景作为评分依据
3. 同时指出 1 个亮点 + 1 个不足
4. 简体中文，80-160 字"""

        # ============ 结构化输出 ============
        # 共用的 schema
        schema_props = {
            "roleplay_score": {
                "type": "integer",
                "minimum": 0,
                "maximum": 100,
                "description": "扮演分 0-100，依据系统提示中的扮演分锚点"
            },
            "impact_score": {
                "type": "integer",
                "minimum": 0,
                "maximum": 100,
                "description": "影响分 0-100，依据系统提示中的影响分锚点"
            },
            "comment": {
                "type": "string",
                "minLength": 60,
                "maxLength": 400,
                "description": "80-160 字的中文点评，需引用具体台词或场景"
            }
        }
        schema_required = ["roleplay_score", "impact_score", "comment"]

        if provider == 'anthropic':
            url = base_url + '/v1/messages'
            headers = {
                'Content-Type': 'application/json',
                'x-api-key': api_key,
                'anthropic-version': '2023-06-01',
            }
            tool_def = {
                "name": "submit_review",
                "description": "提交对该角色的评分与点评。这是唯一允许的输出方式。",
                "input_schema": {
                    "type": "object",
                    "properties": schema_props,
                    "required": schema_required
                }
            }
            payload = {
                'model': model,
                'max_tokens': max_tokens,
                'temperature': temperature,
                'system': system_prompt,
                'messages': [{'role': 'user', 'content': user_prompt}],
                'tools': [tool_def],
                'tool_choice': {'type': 'tool', 'name': 'submit_review'},
            }
            body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        else:
            url = base_url + '/chat/completions'
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {api_key}',
            }
            payload = {
                'model': model,
                'messages': [
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': user_prompt},
                ],
                'temperature': temperature,
                'max_tokens': max_tokens,
                # 优先尝试 json_schema 模式（OpenAI gpt-4o 系列、部分代理支持）
                'response_format': {
                    'type': 'json_schema',
                    'json_schema': {
                        'name': 'role_review',
                        'strict': True,
                        'schema': {
                            'type': 'object',
                            'properties': schema_props,
                            'required': schema_required,
                            'additionalProperties': False
                        }
                    }
                }
            }
            body = json.dumps(payload, ensure_ascii=False).encode('utf-8')

        # ============ 调用 ============
        def do_request(req_body):
            req = urllib.request.Request(url, data=req_body, headers=headers, method='POST')
            with urllib.request.urlopen(req, timeout=90) as resp:
                return json.loads(resp.read().decode('utf-8'))

        try:
            resp_data = do_request(body)
        except urllib.error.HTTPError as e:
            err_body = e.read().decode('utf-8', errors='replace')[:500]
            # 如果是 OpenAI 协议、json_schema 不被支持，退化到 json_object
            if (provider != 'anthropic' and e.code == 400
                    and ('json_schema' in err_body or 'response_format' in err_body)):
                payload['response_format'] = {'type': 'json_object'}
                # json_object 模式下需要在 prompt 里强调返回 JSON
                payload['messages'][1]['content'] += "\n\n请以 JSON 对象形式回复，仅包含 roleplay_score、impact_score、comment 三个字段。"
                try:
                    resp_data = do_request(json.dumps(payload, ensure_ascii=False).encode('utf-8'))
                except urllib.error.HTTPError as e2:
                    err2 = e2.read().decode('utf-8', errors='replace')[:300]
                    # 再退化：去掉 response_format
                    if e2.code == 400 and 'response_format' in err2:
                        payload.pop('response_format', None)
                        try:
                            resp_data = do_request(json.dumps(payload, ensure_ascii=False).encode('utf-8'))
                        except urllib.error.HTTPError as e3:
                            err3 = e3.read().decode('utf-8', errors='replace')[:300]
                            return jsonify({'error': f'API 返回 {e3.code}: {err3}'}), 502
                    else:
                        return jsonify({'error': f'API 返回 {e2.code}: {err2}'}), 502
            else:
                return jsonify({'error': f'API 返回 {e.code}: {err_body}'}), 502
        except urllib.error.URLError as e:
            return jsonify({'error': f'无法连接 API: {e.reason}'}), 502
        except Exception as e:
            return jsonify({'error': f'调用失败: {str(e)}'}), 502

        # ============ 解析结构化响应 ============
        parsed = None
        raw_text_for_debug = ''

        if provider == 'anthropic':
            blocks = resp_data.get('content', [])
            for b in blocks:
                if isinstance(b, dict) and b.get('type') == 'tool_use' and b.get('name') == 'submit_review':
                    parsed = b.get('input') or {}
                    break
                if isinstance(b, dict) and b.get('type') == 'text':
                    raw_text_for_debug += b.get('text', '')
            if parsed is None:
                # 模型未走 tool_use（罕见，但兜底从 text 抓 JSON）
                parsed = _try_extract_json(raw_text_for_debug)
        else:
            try:
                content = resp_data['choices'][0]['message']['content']
                raw_text_for_debug = content
                parsed = json.loads(content)
            except (KeyError, IndexError, TypeError):
                return jsonify({'error': 'API 响应格式异常', 'raw': resp_data}), 502
            except json.JSONDecodeError:
                parsed = _try_extract_json(content)

        if not parsed:
            return jsonify({'error': '无法从响应中提取结构化数据', 'raw_text': raw_text_for_debug[:500]}), 502

        try:
            rp = max(0, min(100, int(parsed.get('roleplay_score', 0))))
            ip = max(0, min(100, int(parsed.get('impact_score', 0))))
        except (TypeError, ValueError):
            return jsonify({'error': '分数字段非整数', 'raw': parsed}), 502

        comment = str(parsed.get('comment', '')).strip()
        if not comment:
            return jsonify({'error': '点评字段为空', 'raw': parsed}), 502

        rp_tier_pool = _KP_ROLEPLAY_TIERS if is_kp else _PL_ROLEPLAY_TIERS
        ip_tier_pool = _KP_IMPACT_TIERS if is_kp else _PL_IMPACT_TIERS
        return jsonify({
            'roleplay_score': rp,
            'impact_score': ip,
            'roleplay_tier': _score_to_tier(rp, rp_tier_pool),
            'impact_tier': _score_to_tier(ip, ip_tier_pool),
            'roleplay_tier_index': _score_to_tier_index(rp, rp_tier_pool),
            'impact_tier_index': _score_to_tier_index(ip, ip_tier_pool),
            'tier_total': len(rp_tier_pool),
            'comment': comment,
            'speaker': speaker,
            'is_kp': is_kp,
            'sampled': {
                'ic_used': len(ic_picks),
                'ic_total': len(ic),
                'ooc_used': len(ooc_picks),
                'ooc_total': len(ooc),
            }
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'服务器错误: {str(e)}'}), 500


@app.route('/api/cleanup/<download_id>/<filename>', methods=['POST'])
def cleanup_file(download_id, filename):
    """清理生成的文件"""
    try:
        safe_filename = secure_filename(filename)
        if not download_id or not safe_filename:
            return jsonify({'error': '参数无效'}), 400

        file_path = os.path.abspath(os.path.join(
            app.config['OUTPUT_FOLDER'],
            f"{download_id}_{safe_filename}"
        ))
        output_root = os.path.abspath(app.config['OUTPUT_FOLDER'])
        if os.path.commonpath([output_root, file_path]) != output_root:
            return jsonify({'error': '路径无效'}), 400

        if os.path.exists(file_path):
            os.remove(file_path)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ========== Feedback / 留言板 ==========

FEEDBACK_ALLOWED_EXT = {'txt', 'doc', 'docx', 'html', 'htm', 'log', 'json'}


def _load_feedback():
    with FEEDBACK_LOCK:
        if not os.path.exists(FEEDBACK_DB):
            return []
        try:
            with open(FEEDBACK_DB, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return []


def _save_feedback(items):
    with FEEDBACK_LOCK:
        tmp_path = FEEDBACK_DB + '.tmp'
        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump(items, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, FEEDBACK_DB)


@app.route('/api/feedback', methods=['GET'])
def list_feedback():
    """列出全部反馈，按时间倒序。前端公开可读。"""
    items = _load_feedback()
    # 倒序输出（最新在前）
    items = sorted(items, key=lambda x: x.get('created_at', 0), reverse=True)
    # 前端不需要服务器内部存储路径，过滤敏感字段
    safe = []
    for it in items:
        safe.append({
            'id': it.get('id'),
            'nickname': it.get('nickname') or '路过者',
            'message': it.get('message', ''),
            'description': it.get('description', ''),
            'created_at': it.get('created_at'),
            'attachment': it.get('attachment_name'),  # 仅文件名，下载用 id 拼
        })
    return jsonify({'items': safe})


@app.route('/api/feedback', methods=['POST'])
def submit_feedback():
    """提交反馈：multipart form
        nickname (可选，<=20 字)
        message  (必填，<=200 字，留言条)
        description (可选，<=4000 字)
        attachment (可选，文件)
    """
    try:
        nickname = (request.form.get('nickname') or '').strip()[:20]
        message = (request.form.get('message') or '').strip()
        description = (request.form.get('description') or '').strip()
        if not message:
            return jsonify({'error': '留言条不能为空'}), 400
        if len(message) > 200:
            return jsonify({'error': '留言条最多 200 字'}), 400
        if len(description) > 4000:
            return jsonify({'error': '详细描述最多 4000 字'}), 400

        feedback_id = str(uuid.uuid4())[:12]
        attachment_name = None

        if 'attachment' in request.files:
            f = request.files['attachment']
            if f and f.filename:
                ext = f.filename.rsplit('.', 1)[-1].lower() if '.' in f.filename else ''
                if ext not in FEEDBACK_ALLOWED_EXT:
                    return jsonify({'error': f'附件只支持: {", ".join(sorted(FEEDBACK_ALLOWED_EXT))}'}), 400
                safe_name = secure_filename(f.filename) or f'log.{ext}'
                save_path = os.path.join(FEEDBACK_ATTACH, f"{feedback_id}_{safe_name}")
                f.save(save_path)
                # 限制单文件大小由 MAX_CONTENT_LENGTH 兜底
                attachment_name = safe_name

        item = {
            'id': feedback_id,
            'nickname': nickname,
            'message': message,
            'description': description,
            'attachment_name': attachment_name,
            'created_at': int(datetime.now().timestamp()),
            'ip_hint': request.headers.get('X-Forwarded-For', request.remote_addr or '')[:40],
        }
        with FEEDBACK_LOCK:
            items = _load_feedback()
            items.append(item)
            _save_feedback(items)

        return jsonify({'success': True, 'id': feedback_id})

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'提交失败: {str(e)}'}), 500


@app.route('/api/feedback/<feedback_id>/attachment')
def download_feedback_attachment(feedback_id):
    """下载某条反馈的附件（公开）"""
    try:
        # 找到该 id 对应的实际文件
        prefix = f"{feedback_id}_"
        for f in os.listdir(FEEDBACK_ATTACH):
            if f.startswith(prefix):
                file_path = os.path.join(FEEDBACK_ATTACH, f)
                download_name = f[len(prefix):]
                return send_file(file_path, as_attachment=True, download_name=download_name)
        return jsonify({'error': '附件不存在'}), 404
    except Exception as e:
        return jsonify({'error': f'下载出错: {str(e)}'}), 500


if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=5000)
