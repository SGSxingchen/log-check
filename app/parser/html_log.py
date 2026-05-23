"""HTML / Word 日志预处理。

将海豹骰 logrender.dice.center 导出的 HTML/MHTML/.doc，以及可抽取文本的
.docx/.doc 转换为现有解析器能处理的纯文本日志。
"""
from datetime import datetime
from email import policy
from email.parser import BytesParser
from html import unescape
from html.parser import HTMLParser
import re
import zipfile
import xml.etree.ElementTree as ET


HTML_LOG_MARKERS = (
    'log_child_id_',
    'log_child_time',
    'log_child_content',
    'logrender.dice.center',
)

# 形如 00:01:17<某某>: 的 Word 内联导出格式
WORD_INLINE_PATTERN = re.compile(r'(\d{2}:\d{2}:\d{2})<([^>\n]{1,80})>:', re.S)

# img alt/title 中常见的"实质上是文件名/URL"的占位符（应丢弃，不当作内容）
_IMG_ALT_NOISE = re.compile(
    r'^(?:[\w./\\:?&=%~+\-\s{}\[\]\(\)#@!,]+\.(?:png|jpg|jpeg|gif|webp|bmp))$',
    re.IGNORECASE,
)


def is_html_log(text_head):
    """根据文本内容判断是否为海豹骰 HTML log。"""
    return any(m in text_head for m in HTML_LOG_MARKERS)


def is_word_inline_log(text):
    """检测 Word 内联导出格式（HH:MM:SS<名字>:内容 全部堆在一段里）。"""
    return len(WORD_INLINE_PATTERN.findall(text)) >= 3


def _class_tokens(attrs):
    return set((attrs.get('class') or '').split())


def _normalize_time(time_text):
    """把常见 HTML 导出时间归一为 format1 的 YYYY-MM-DD HH:MM:SS。"""
    match = re.search(
        r'(\d{4})[-/](\d{1,2})[-/](\d{1,2}).*?(\d{1,2}):(\d{2})(?::(\d{2}))?',
        time_text
    )
    if not match:
        return None

    year, month, day, hour, minute, second = match.groups()
    second = second or '00'
    try:
        dt = datetime(
            int(year), int(month), int(day),
            int(hour), int(minute), int(second)
        )
    except ValueError:
        return None
    return dt.strftime('%Y-%m-%d %H:%M:%S')


class LogRenderHTMLParser(HTMLParser):
    """容忍属性顺序、单双引号、多 class 的 logrender HTML 解析器。"""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.entries = []
        self.current = None
        self.entry_depth = 0
        self.capture_stack = []

    def handle_starttag(self, tag, attrs):
        attrs_dict = {k.lower(): (v or '') for k, v in attrs}
        classes = _class_tokens(attrs_dict)
        tag = tag.lower()

        if tag == 'div' and any(c.startswith('log_child_id_') for c in classes):
            self.current = {'time': [], 'speaker': [], 'content': []}
            self.entry_depth = 1
            self.capture_stack = [None]
            return

        if not self.current:
            return

        parent_capture = self.capture_stack[-1] if self.capture_stack else None
        if tag in ('br', 'img'):
            if parent_capture == 'content' and tag == 'br':
                self.current['content'].append('\n')
            elif parent_capture == 'content' and tag == 'img':
                alt = attrs_dict.get('alt') or attrs_dict.get('title')
                if alt and not _IMG_ALT_NOISE.match(alt.strip()):
                    self.current['content'].append(alt)
            return

        self.entry_depth += 1
        capture = None
        if 'log_child_time' in classes:
            capture = 'time'
        elif 'log_child_content' in classes or 'contenteditable' in attrs_dict:
            capture = 'content'
        elif parent_capture == 'content':
            capture = 'content'

        self.capture_stack.append(capture)

    def handle_endtag(self, tag):
        if not self.current:
            return

        if self.capture_stack:
            self.capture_stack.pop()
        self.entry_depth -= 1

        if self.entry_depth <= 0:
            time_text = ''.join(self.current['time']).strip()
            speaker_text = ''.join(self.current['speaker']).strip()
            content = ''.join(self.current['content']).strip()
            self._finish_entry(time_text, speaker_text, content)
            self.current = None
            self.entry_depth = 0
            self.capture_stack = []

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_data(self, data):
        if not self.current or not data:
            return
        capture = self.capture_stack[-1] if self.capture_stack else None
        if capture == 'time':
            self.current['time'].append(data)
        elif capture == 'content':
            self.current['content'].append(data)
        else:
            self.current['speaker'].append(data)

    def _finish_entry(self, time_text, speaker_text, content):
        if not time_text or not content:
            return
        speaker_match = re.search(r'<\s*(.+?)\s*>', speaker_text)
        if not speaker_match:
            return
        time_str = _normalize_time(time_text)
        if not time_str:
            return
        speaker = unescape(speaker_match.group(1)).strip()
        if speaker:
            self.entries.append((speaker, time_str, content))


def html_to_format1(html_text):
    """把 HTML log 转换为 format1 风格的纯文本。"""
    parser = LogRenderHTMLParser()
    parser.feed(html_text)

    out_lines = []
    for name, time_str, content in parser.entries:
        out_lines.append(f"{name}(0) {time_str}")
        out_lines.append(content)
    return '\n'.join(out_lines)


def _strip_html(html_text):
    """剥掉 <style>/<script>/注释/标签，把 <br> 和段落转成换行；保留 img 的 alt（噪声除外）。"""
    text = re.sub(r'<!--.*?-->', '', html_text, flags=re.S)
    text = re.sub(r'<(style|script)[^>]*>.*?</\1>', '', text, flags=re.S | re.I)
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.I)
    text = re.sub(r'</p\s*>', '\n', text, flags=re.I)

    def _img_repl(m):
        attrs = m.group(0)
        alt_match = re.search(r'\b(?:alt|title)\s*=\s*["\']([^"\']*)["\']', attrs, re.I)
        if not alt_match:
            return ''
        alt = alt_match.group(1).strip()
        if not alt or _IMG_ALT_NOISE.match(alt):
            return ''
        return alt

    text = re.sub(r'<img[^>]*>', _img_repl, text, flags=re.I)
    text = re.sub(r'<[^>]+>', '', text)
    return unescape(text)


def word_inline_to_format4(text):
    """把 Word 内联格式（HH:MM:SS<名字>:内容HH:MM:SS<名字>:内容...）切成 format4。

    输出每条占独立两行：
        HH:MM:SS<名字>:第一行
        续行...
    """
    matches = list(WORD_INLINE_PATTERN.finditer(text))
    if not matches:
        return ''

    out_lines = []
    for i, m in enumerate(matches):
        time_str = m.group(1)
        speaker = m.group(2).strip()
        if not speaker:
            continue
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        content = text[start:end].strip()
        if not content:
            continue
        # 折行规整：保留段落但避免空白堆积
        content_lines = [ln.rstrip() for ln in content.splitlines() if ln.strip()]
        if not content_lines:
            continue
        first = content_lines[0]
        out_lines.append(f"{time_str}<{speaker}>:{first}")
        for ln in content_lines[1:]:
            out_lines.append(ln)
    return '\n'.join(out_lines)


def is_docx_file(file_path):
    """检查文件是否为 .docx (zip + word/document.xml)。"""
    try:
        if not zipfile.is_zipfile(file_path):
            return False
        with zipfile.ZipFile(file_path) as z:
            return 'word/document.xml' in z.namelist()
    except (zipfile.BadZipFile, OSError):
        return False


def docx_to_text(file_path):
    """从 .docx 中提取段落纯文本，保持原顺序。"""
    w_ns = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
    with zipfile.ZipFile(file_path) as z:
        with z.open('word/document.xml') as f:
            xml = f.read()

    root = ET.fromstring(xml)
    out = []
    for p_el in root.iter(w_ns + 'p'):
        parts = []
        for child in p_el.iter():
            tag = child.tag
            if tag == w_ns + 't':
                if child.text:
                    parts.append(child.text)
            elif tag == w_ns + 'tab':
                parts.append('\t')
            elif tag == w_ns + 'br':
                parts.append('\n')
        text = ''.join(parts)
        if text.strip():
            out.append(text)
    return '\n'.join(out)


def _decode_bytes(data):
    """尽量按常见网页/Word 保存编码解码文本。"""
    if data.startswith(b'\xef\xbb\xbf'):
        return data.decode('utf-8-sig', errors='replace')
    if data.startswith(b'\xff\xfe') or data.startswith(b'\xfe\xff'):
        return data.decode('utf-16', errors='replace')

    head = data[:4096].decode('ascii', errors='ignore')
    charset_match = re.search(r'charset=["\']?([\w.-]+)', head, re.IGNORECASE)
    encodings = []
    if charset_match:
        encodings.append(charset_match.group(1))
    encodings.extend(['utf-8', 'gb18030', 'utf-16', 'latin1'])

    for enc in encodings:
        try:
            return data.decode(enc)
        except (LookupError, UnicodeDecodeError):
            continue
    return data.decode('utf-8', errors='replace')


def _extract_mhtml_text(data):
    """从 MHTML 邮件包中取 HTML 正文；普通 HTML 会返回 None。"""
    try:
        message = BytesParser(policy=policy.default).parsebytes(data)
    except Exception:
        return None

    if not message.is_multipart():
        return None

    html_parts = []
    text_parts = []
    for part in message.walk():
        content_type = part.get_content_type()
        if content_type not in ('text/html', 'text/plain'):
            continue
        payload = part.get_payload(decode=True)
        if payload is None:
            continue
        charset = part.get_content_charset() or 'utf-8'
        try:
            text = payload.decode(charset, errors='replace')
        except LookupError:
            text = payload.decode('utf-8', errors='replace')
        if content_type == 'text/html':
            html_parts.append(text)
        else:
            text_parts.append(text)

    if html_parts:
        return '\n'.join(html_parts)
    if text_parts:
        return '\n'.join(text_parts)
    return None


def _extract_binary_doc_text(data):
    """兜底从二进制 .doc 中抽可见文本片段，适配简单日志文档。"""
    candidates = []
    for encoding in ('utf-16le', 'gb18030', 'latin1'):
        text = data.decode(encoding, errors='ignore')
        fragments = re.findall(r'[\u4e00-\u9fffA-Za-z0-9_()<>\-/:：，。,.\s]{8,}', text)
        if fragments:
            candidates.append('\n'.join(f.strip() for f in fragments if f.strip()))
    return max(candidates, key=len) if candidates else ''


def _write_converted(file_path, text):
    new_path = file_path + '.converted.txt'
    with open(new_path, 'w', encoding='utf-8') as f:
        f.write(text)
    return new_path, True


def preprocess_log_file(file_path):
    """检测并预处理日志文件。

    支持：
      - .docx (Microsoft Word) -> 提取段落文本
      - logrender HTML/MHTML/.doc -> 转 format1
      - 可抽取文本的二进制 .doc -> 提取文本
      - 其他 .txt 直接返回原路径
    """
    ext = file_path.rsplit('.', 1)[-1].lower() if '.' in file_path else ''

    if is_docx_file(file_path):
        try:
            text = docx_to_text(file_path)
        except Exception:
            return file_path, False
        if not text.strip():
            return file_path, False
        return _write_converted(file_path, text)

    try:
        with open(file_path, 'rb') as f:
            data = f.read()
    except OSError:
        return file_path, False

    full = _extract_mhtml_text(data) or _decode_bytes(data)
    if is_html_log(full):
        converted = html_to_format1(full)
        if converted.strip():
            return _write_converted(file_path, converted)
        return file_path, False

    # Word 内联格式（如溯回骰）：HTML 标签里整段堆着 HH:MM:SS<名字>:...
    if '<' in full and '>' in full:
        stripped = _strip_html(full)
        if is_word_inline_log(stripped):
            converted = word_inline_to_format4(stripped)
            if converted.strip():
                return _write_converted(file_path, converted)
    elif is_word_inline_log(full):
        # 已经是纯文本但凑巧符合内联格式
        converted = word_inline_to_format4(full)
        if converted.strip():
            return _write_converted(file_path, converted)

    if ext == 'doc':
        extracted = _extract_binary_doc_text(data)
        if extracted.strip():
            return _write_converted(file_path, extracted)

    return file_path, False
