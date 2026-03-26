import sys
import os
import json
import struct
import re
import binascii
import csv
import time

from datetime import datetime, timezone, timedelta

# 🌟 引入串口通信库
try:
    import serial
    import serial.tools.list_ports
except ImportError:
    print("未检测到 pyserial 库！请运行: pip install pyserial")
    sys.exit(1)

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QPushButton, QFileDialog, QTableView, QTreeView, QComboBox,
                             QLabel, QProgressBar, QSplitter, QMessageBox, QHeaderView, QAbstractItemView, QLineEdit,
                             QPlainTextEdit, QCheckBox)
from PyQt6.QtGui import QStandardItemModel, QStandardItem, QFont, QTextCursor, QSyntaxHighlighter, QTextCharFormat, QColor, QTextBlockFormat
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QAbstractTableModel, QEvent, QRegularExpression


# ==========================================
# 🌟 新增：日志智能高亮引擎 (支持全局搜索多级高亮)
# ==========================================
class LogHighlighter(QSyntaxHighlighter):
    def __init__(self, document, is_dark_mode=True):
        super().__init__(document)
        self.rules = []
        self.search_keyword = ""  # 🌟 新增：记录当前搜索的关键字
        self.is_dark = is_dark_mode
        self.update_theme(is_dark_mode)

    def set_search_keyword(self, keyword):
        # 🌟 触发器：当用户输入搜索词时，要求底层引擎重新渲染全局
        if self.search_keyword != keyword:
            self.search_keyword = keyword
            self.rehighlight()

    def update_theme(self, is_dark_mode):
        self.is_dark = is_dark_mode
        self.rules.clear()

        # 1. 灰蓝色: 时间戳
        ts_format = QTextCharFormat()
        ts_format.setForeground(QColor("#9CA3AF") if is_dark_mode else QColor("#6B7280"))
        self.rules.append((QRegularExpression(r"^\[\d{2}:\d{2}:\d{2}\.\d{3}\]"), ts_format))

        # 2. 亮红色: 错误/异常
        err_format = QTextCharFormat()
        err_format.setForeground(QColor("#EF4444") if is_dark_mode else QColor("#DC2626"))
        err_format.setFontWeight(QFont.Weight.Bold)
        self.rules.append((QRegularExpression(r"(?i)(error|fail|timeout|异常|失败)"), err_format))
        self.rehighlight()

    def highlightBlock(self, text):
        import re

        for pattern, format in self.rules:
            match_iterator = pattern.globalMatch(text)
            while match_iterator.hasNext():
                match = match_iterator.next()
                self.setFormat(match.capturedStart(), match.capturedLength(), format)

        is_tx = re.search(r"(?i)(nb_send|send|发送|\[上行\])", text)
        is_rx = re.search(r"(?i)(nb_recv|recv|接收|\[下行\])", text)

        # 狙击 HEX 数据流
        hex_pattern = QRegularExpression(r"\b(?:[0-9a-fA-F]{2}[\s\-]+){3,}[0-9a-fA-F]{2}\b")
        hex_iterator = hex_pattern.globalMatch(text)
        while hex_iterator.hasNext():
            match = hex_iterator.next()
            hex_fmt = QTextCharFormat()
            hex_fmt.setFontWeight(QFont.Weight.Bold)
            if is_tx:
                hex_fmt.setForeground(QColor("#38BDF8") if self.is_dark else QColor("#0284C7"))
            elif is_rx:
                hex_fmt.setForeground(QColor("#FBBF24") if self.is_dark else QColor("#D97706"))
            else:
                hex_fmt.setForeground(QColor("#A855F7") if self.is_dark else QColor("#9333EA"))
            self.setFormat(match.capturedStart(), match.capturedLength(), hex_fmt)

        # 狙击 JSON
        json_pattern = QRegularExpression(r"\{.*?\}")
        json_iterator = json_pattern.globalMatch(text)
        while json_iterator.hasNext():
            match = json_iterator.next()
            json_fmt = QTextCharFormat()
            json_fmt.setFontWeight(QFont.Weight.Bold)
            if is_tx:
                json_fmt.setForeground(QColor("#38BDF8") if self.is_dark else QColor("#0284C7"))
            elif is_rx:
                json_fmt.setForeground(QColor("#FBBF24") if self.is_dark else QColor("#D97706"))
            else:
                json_fmt.setForeground(QColor("#10B981") if self.is_dark else QColor("#059669"))
            self.setFormat(match.capturedStart(), match.capturedLength(), json_fmt)

        # =========================================================
        # 4. 🌟 终极渲染：全局搜索结果铺底色 (底层无感执行，极其流畅)
        # =========================================================
        if self.search_keyword:
            # 忽略大小写进行匹配
            search_pattern = QRegularExpression(
                QRegularExpression.escape(self.search_keyword),
                QRegularExpression.PatternOption.CaseInsensitiveOption
            )
            search_iterator = search_pattern.globalMatch(text)

            search_fmt = QTextCharFormat()
            # 🌟 设置【全局搜索】的强力高亮底色！
            if self.is_dark:
                # 深色模式：极其亮眼的 荧光蓝 (DeepSkyBlue) 底色 + 纯黑字 (对比度拉满)
                search_fmt.setBackground(QColor("#00BFFF"))
                search_fmt.setForeground(QColor("#000000"))
            else:
                # 浅色模式：极其亮眼的 亮翠绿 底色 + 纯黑字
                search_fmt.setBackground(QColor("#4ADE80"))
                search_fmt.setForeground(QColor("#000000"))

            while search_iterator.hasNext():
                match = search_iterator.next()
                self.setFormat(match.capturedStart(), match.capturedLength(), search_fmt)

# ==========================================
# 高级 UI 组件: 视口冻结终端
# ==========================================
from PyQt6.QtWidgets import QTextEdit  # 确保引入了满血版引擎
class TerminalTextEdit(QTextEdit):  # 🌟 变化 1：继承自 QTextEdit
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main_window = main_window

        font = QFont("Consolas", 10)
        font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
        self.setFont(font)

        self.setReadOnly(True)  # 🌟 变化 2：富文本组件默认可编辑，这里强制锁死为只读模式
        self.document().setMaximumBlockCount(50000)  # 🌟 变化 3：最大行数的 API 写法变了

        # 挂载动态高亮引擎
        self.highlighter = LogHighlighter(self.document(), is_dark_mode=True)

    def wheelEvent(self, event):
        if event.angleDelta().y() > 0:
            if self.main_window.cb_auto_scroll.isChecked():
                self.main_window.cb_auto_scroll.setChecked(False)
        super().wheelEvent(event)
# ==========================================
# 🌟 新增：高级 UI 组件: 视口冻结表格 (右侧流水线)
# ==========================================
class AutoScrollTableView(QTableView):
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main_window = main_window

    def wheelEvent(self, event):
        # 向上滚动滚轮时，自动取消表格的自动滚动
        if event.angleDelta().y() > 0:
            if hasattr(self.main_window, 'cb_table_auto_scroll') and self.main_window.cb_table_auto_scroll.isChecked():
                self.main_window.cb_table_auto_scroll.setChecked(False)
        super().wheelEvent(event)

# ==========================================
# 🌟 新增：高级 UI 组件: 自动扫描串口下拉框
# ==========================================
class AutoRefreshComboBox(QComboBox):
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main_window = main_window

    def showPopup(self):
        # 核心魔法：在下拉菜单弹出的瞬间，强制调用主窗口的扫描函数
        self.main_window.refresh_serial_ports()
        super().showPopup()

# ==========================================
# 串口守护线程: 后台独立无损抓包
# ==========================================
class SerialWorker(QThread):
    data_received = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    finished_signal = pyqtSignal()

    def __init__(self, port, baudrate):
        super().__init__()
        self.port = port
        self.baudrate = baudrate
        self.running = True
        self.serial = None

    def run(self):
        try:
            self.serial = serial.Serial(self.port, self.baudrate, timeout=0.1)
            while self.running:
                if self.serial.in_waiting:
                    raw_data = self.serial.read(self.serial.in_waiting)
                    try:
                        text = raw_data.decode('utf-8', errors='replace')
                        self.data_received.emit(text)
                    except:
                        pass
                else:
                    self.msleep(10)
        except Exception as e:
            self.error_occurred.emit(f"串口异常: {str(e)}")
        finally:
            if self.serial and self.serial.is_open:
                self.serial.close()
            self.finished_signal.emit()

    def stop(self):
        self.running = False


# ==========================================
# 核心业务层 (Model): 解析引擎
# ==========================================
class ProtocolDecoder:
    def __init__(self, config_path):
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"找不到配置文件: {config_path}")
        with open(config_path, 'r', encoding='utf-8-sig') as f:
            self.schema = json.load(f)
        self.msgs = self.schema.get('messages', {})
        self.config = self.schema.get('config', {})
        self.common_mappings = self.schema.get('common_mappings', {})

    def format_time(self, timestamp):
        try:
            if 0 < timestamp < 4102444800:
                dt = datetime.fromtimestamp(timestamp, timezone.utc) + timedelta(hours=8)
                return dt.strftime('%Y-%m-%d %H:%M:%S')
            return str(timestamp)
        except:
            return str(timestamp)

    def parse_bcd(self, data):
        return binascii.hexlify(data).decode('ascii')

    def parse_bitfield(self, value, mapping, width=32):
        result = {}
        for bit_index_str, desc in mapping.items():
            try:
                bit_index = int(bit_index_str)
                is_set = (value >> bit_index) & 1
                result[desc] = int(is_set)
            except:
                continue
        return result

    def _process_value(self, val, field_info):
        if isinstance(val, (int, float)):
            if 'scale' in field_info:
                val = val * field_info['scale']
                scale = field_info['scale']
                if abs(scale - 0.000001) < 1e-9:
                    val = round(val, 6)
                elif abs(scale - 0.1) < 1e-9:
                    val = round(val, 1)
                elif abs(scale - 0.01) < 1e-9:
                    val = round(val, 2)
                else:
                    val = round(val, 6)

            if 'offset' in field_info:
                val = val + field_info['offset']

            if 'mapping' in field_info:
                val = field_info['mapping'].get(str(int(val)), val)

        elif isinstance(val, str) and 'mapping' in field_info:
            val = field_info['mapping'].get(val.strip(), val)

        if 'unit' in field_info and str(val).strip() != "":
            val = f"{val}{field_info['unit']}"

        return val

    def read_field(self, f_type, chunk, field_info):
        val = None
        if f_type == 'U1':
            val = struct.unpack('>B', chunk)[0]
        elif f_type == 'U2':
            val = struct.unpack('>H', chunk)[0]
        elif f_type == 'U4':
            val = struct.unpack('>I', chunk)[0]
        elif f_type == 'I1':
            val = struct.unpack('>b', chunk)[0]
        elif f_type == 'I2':
            val = struct.unpack('>h', chunk)[0]
        elif f_type == 'I4':
            val = struct.unpack('>i', chunk)[0]
        elif f_type == 'BCD':
            val = self.parse_bcd(chunk)
        elif f_type == 'BYTES':
            val = binascii.hexlify(chunk).decode('ascii')
        elif f_type == 'HEX2DEC':
            val = str(int(binascii.hexlify(chunk).decode('ascii'), 16))
        elif f_type == 'TIMESTAMP_BJ':
            seconds = struct.unpack('>I', chunk)[0]
            try:
                dt = datetime.fromtimestamp(seconds, timezone.utc) + timedelta(hours=8)
                val = dt.strftime('%Y-%m-%d %H:%M:%S')
            except:
                val = str(seconds)
        elif f_type == 'MZ_LATLNG':
            val = round(struct.unpack('>I', chunk)[0] / 1800000.0, 6)
        elif f_type == 'ASCII_STR':
            try:
                val = chunk.decode('ascii', errors='ignore').strip('\x00')
            except:
                val = str(chunk)
        elif f_type == 'TLV':
            tlv_result = {}
            tlv_cursor = 0
            tlv_config = field_info.get('tlv_dict', {})
            while tlv_cursor + 2 <= len(chunk):
                tag = chunk[tlv_cursor]
                val_len = chunk[tlv_cursor + 1]
                tlv_cursor += 2
                if tlv_cursor + val_len > len(chunk): break
                val_chunk = chunk[tlv_cursor: tlv_cursor + val_len]
                tlv_cursor += val_len
                tag_hex = f"0x{tag:02X}"
                tag_def = tlv_config.get(tag_hex)
                if tag_def:
                    parsed_val = self.read_field(tag_def.get('type', 'BYTES'), val_chunk, tag_def)
                    if 'segments' in tag_def and isinstance(parsed_val, int):
                        for seg in tag_def['segments']:
                            seg_val = (parsed_val & seg.get('mask', 0xFF)) >> seg.get('shift', 0)
                            tlv_result[seg['name']] = self._process_value(seg_val, seg)
                    else:
                        tlv_result[tag_def['name']] = self._process_value(parsed_val, tag_def)
                else:
                    tlv_result[f"TLV_未知外设_{tag_hex}"] = binascii.hexlify(val_chunk).decode('ascii')
            val = tlv_result
        elif f_type.startswith('BITFIELD_'):
            fmt, width = {'BITFIELD_U4': ('>I', 32), 'BITFIELD_U2': ('>H', 16)}.get(f_type, ('>B', 8))
            int_val = struct.unpack(fmt, chunk)[0]
            mapping = field_info.get('mapping', self.common_mappings.get(field_info.get('mapping_ref'), {}))
            val = self.parse_bitfield(int_val, mapping, width)

        if isinstance(val, (int, float)) and 'BITFIELD' not in f_type and 'segments' not in field_info:
            if 'time' in field_info.get('name', '').lower() and field_info.get('unit') is None:
                val = self.format_time(val)
        return val

    def decode_body(self, msg_type_hex, body_bytes):
        if len(body_bytes) == 0:
            return {"_note": "✅ 无附加消息体 (平台确认 ACK)"}
        msg_def = self.msgs.get(msg_type_hex)
        if not msg_def:
            return {"raw_body": binascii.hexlify(body_bytes).decode('ascii'), "_note": "未定义的消息类型"}
        result = {}
        cursor = 0
        try:
            def get_chunk(f_def, current_cursor):
                ft = f_def['type']
                length = {'U1': 1, 'BITFIELD_U1': 1, 'I1': 1, 'U2': 2, 'I2': 2, 'BITFIELD_U2': 2,
                          'U4': 4, 'I4': 4, 'BITFIELD_U4': 4, 'TIMESTAMP_BJ': 4, 'MZ_LATLNG': 4}.get(ft,
                                                                                                     f_def.get('length',
                                                                                                               1))
                if length == -1: length = len(body_bytes) - current_cursor
                if current_cursor + length > len(body_bytes): return None, length
                return body_bytes[current_cursor: current_cursor + length], length

            for field in msg_def['fields']:
                chunk, length = get_chunk(field, cursor)
                if chunk is None:
                    result[field['name']] = "<Truncated>"
                    break
                val = self.read_field(field['type'], chunk, field)
                if field['type'] == 'TLV' and isinstance(val, dict):
                    for k, v in val.items(): result[k] = v
                elif 'segments' in field and isinstance(val, int):
                    for seg in field['segments']:
                        seg_val = (val & seg.get('mask', 0xFF)) >> seg.get('shift', 0)
                        result[seg['name']] = self._process_value(seg_val, seg)
                else:
                    result[field['name']] = self._process_value(val, field)
                cursor += length

            if msg_def.get('is_loop') and 'sub_struct' in msg_def:
                loop_count = int(result.get(msg_def.get('loop_count_field'), 0))
                item_list = []
                for _ in range(loop_count):
                    item = {}
                    for sub_f in msg_def['sub_struct']:
                        chunk, slen = get_chunk(sub_f, cursor)
                        if chunk is None: break
                        val = self.read_field(sub_f['type'], chunk, sub_f)
                        if 'segments' in sub_f and isinstance(val, int):
                            for seg in sub_f['segments']:
                                seg_val = (val & seg.get('mask', 0xFF)) >> seg.get('shift', 0)
                                item[seg['name']] = self._process_value(seg_val, seg)
                        else:
                            item[sub_f['name']] = self._process_value(val, sub_f)
                        cursor += slen
                    if item: item_list.append(item)
                result['point_list'] = item_list

            if 'tail_fields' in msg_def:
                for tail_f in msg_def['tail_fields']:
                    chunk, tlen = get_chunk(tail_f, cursor)
                    if chunk is not None:
                        val = self.read_field(tail_f['type'], chunk, tail_f)
                        result[tail_f['name']] = self._process_value(val, tail_f)
                        cursor += tlen
        except Exception as e:
            import traceback
            result['_error'] = f"解析异常: {str(e)} | {traceback.format_exc()}"
        return result


# ==========================================
# 流解析器 (支持实时与离线)
# ==========================================
class StreamParser:
    def __init__(self, decoder):
        self.decoder = decoder
        self.buffer = bytearray()
        self.SYNC_HEADER = bytes.fromhex(self.decoder.config.get('sync_header', '4244'))
        self.header_size = self.decoder.config.get('header_size', 8)
        self.len_offset = self.decoder.config.get('len_offset', 6)
        self.len_size = self.decoder.config.get('len_size', 2)
        self.checksum_size = self.decoder.config.get('checksum_size', 2)
        self.len_includes_all = self.decoder.config.get('len_includes_all', False)
        default_msg_offset = 5 if self.SYNC_HEADER.hex().upper() == 'AAAA' else 2
        self.msg_type_offset = self.decoder.config.get('msg_type_offset', default_msg_offset)

    def feed(self, raw_text):
        import re, struct
        lines = raw_text.splitlines()
        sync_hex = self.SYNC_HEADER.hex().lower()

        for line in lines:
            line = line.strip()
            if not line: continue
            line_lower = line.lower()
            if "ble send" in line_lower or "ble recv" in line_lower or "ctrl send" in line_lower or "ctrl_recv" in line_lower or "mz_send" in line_lower or "mz_recv" in line_lower:
                continue

            match = re.search(r'(?:[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}:|[0-9A-Fa-f]{8}:)\s*(.*)', line)
            if match:
                payload = match.group(1)
                hex_part = re.split(r'\s{3,}', payload)[0]
                pure_hex = re.sub(r'[^0-9a-fA-F]', '', hex_part)
                if len(pure_hex) % 2 != 0: pure_hex = pure_hex[:-1]
                if pure_hex:
                    try:
                        self.buffer.extend(bytes.fromhex(pure_hex))
                    except:
                        pass
                continue

            found_server_log = False
            for word in line.split():
                word_clean = re.sub(r'[^0-9a-fA-F]', '', word)
                if word_clean.lower().startswith(sync_hex) and len(word_clean) >= self.header_size * 2:
                    if len(word_clean) % 2 != 0: word_clean = word_clean[:-1]
                    try:
                        self.buffer.extend(bytes.fromhex(word_clean))
                        found_server_log = True
                    except:
                        pass
            if found_server_log: continue

            if re.match(r'^[A-Z]/[A-Za-z0-9_]+', line): continue

            spaced_text = re.sub(r'[^0-9a-fA-F]', ' ', line)
            chunks = spaced_text.split()
            for chunk in chunks:
                if len(chunk) % 2 != 0: chunk = chunk[:-1]
                if chunk:
                    try:
                        self.buffer.extend(bytes.fromhex(chunk))
                    except:
                        pass

        frames = []
        while True:
            head_idx = self.buffer.find(self.SYNC_HEADER)
            if head_idx == -1:
                keep = len(self.SYNC_HEADER) - 1 if len(self.buffer) > 0 else 0
                self.buffer = self.buffer[-keep:]
                break
            if head_idx > 0: self.buffer = self.buffer[head_idx:]
            if len(self.buffer) < self.header_size: break

            if getattr(self, 'len_size', 2) == 1:
                body_len = self.buffer[self.len_offset]
            else:
                body_len = struct.unpack('>H', self.buffer[self.len_offset: self.len_offset + 2])[0]

            if self.len_includes_all:
                total_len = body_len
            else:
                total_len = self.header_size + body_len + self.checksum_size

            if len(self.buffer) < total_len: break

            frame_bytes = self.buffer[:total_len]
            parsed_frame = self.process_frame(frame_bytes)
            if parsed_frame: frames.append(parsed_frame)
            self.buffer = self.buffer[total_len:]
        return frames

    def process_frame(self, data):
        import struct
        if self.msg_type_offset >= len(data): return None
        msg_type = data[self.msg_type_offset]
        msg_type_hex = f"0x{msg_type:02X}"
        try:
            if self.header_size == 8:
                seq = struct.unpack('>H', data[3:5])[0]
            elif self.header_size == 10:
                seq = data[6]
            elif self.header_size == 6:
                seq = data[3]
            else:
                seq = "N/A"
        except:
            seq = "N/A"

        if self.checksum_size > 0:
            body = data[self.header_size: -self.checksum_size]
        else:
            body = data[self.header_size:]

        decoded_data = self.decoder.decode_body(msg_type_hex, body)
        return {"type": msg_type_hex, "seq": seq, "data": decoded_data}


# ==========================================
# 离线解析线程 (用于导入文件)
# ==========================================
class ParseWorker(QThread):
    progress = pyqtSignal(int)
    batch_ready = pyqtSignal(list)
    finished = pyqtSignal(int)
    error = pyqtSignal(str)

    def __init__(self, filename, decoder):
        super().__init__()
        self.filename = filename
        self.decoder = decoder

    def run(self):
        try:
            tx_parser = StreamParser(self.decoder)
            rx_parser = StreamParser(self.decoder)
            count = 0
            batch = []
            with open(self.filename, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    line_lower = line.lower()
                    frames = []
                    if "nb_send" in line_lower or "发送" in line_lower:
                        _frames = tx_parser.feed(line)
                        for fr in _frames: fr['direction'] = '[上行]'
                        frames.extend(_frames)
                    elif "nb_recv" in line_lower or "接收" in line_lower:
                        _frames = rx_parser.feed(line)
                        for fr in _frames: fr['direction'] = '[下行]'
                        frames.extend(_frames)
                    else:
                        _frames = tx_parser.feed(line)
                        for fr in _frames: fr['direction'] = ''
                        frames.extend(_frames)

                    if frames:
                        batch.extend(frames)
                        count += len(frames)
                        if len(batch) >= 200:
                            self.batch_ready.emit(batch)
                            self.progress.emit(count)
                            batch = []
            if batch:
                self.batch_ready.emit(batch)
                self.progress.emit(count)
            self.finished.emit(count)
        except Exception as e:
            import traceback
            self.error.emit(str(e) + "\n" + traceback.format_exc())


# ==========================================
# 视图层 (View): GUI 界面及数据模型
# ==========================================
class FrameTableModel(QAbstractTableModel):
    def __init__(self, data=None):
        super().__init__()
        self._data = data or []
        self.headers = ["Seq", "时间", "类型", "消息名称", "关键数据摘要"]

    def update_data(self, new_data):
        self.beginResetModel()
        # 🌟 关键修复：加上 [:] 进行浅拷贝，强行切断与主界面的内存指针绑定！
        # 这样无论主界面怎么过滤，表格底层的列表永远是独立安全的。
        self._data = new_data[:]
        self.endResetModel()

    def append_frames(self, frames):
        start_row = len(self._data)
        self.beginInsertRows(self.index(0, 0).parent(), start_row, start_row + len(frames) - 1)
        self._data.extend(frames)
        self.endInsertRows()

    def rowCount(self, parent=None):
        return len(self._data)

    def columnCount(self, parent=None):
        return len(self.headers)

    def headerData(self, section, orientation, role):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.headers[section]

    def data(self, index, role):
        if role == Qt.ItemDataRole.DisplayRole:
            frame = self._data[index.row()]
            col = index.column()
            f_data = frame['data']

            direction = frame.get('direction', '')
            is_xiaoan = False
            msg_0x00 = self.get_msg_name('0x00')
            if '透传' in msg_0x00 or 'WILD' in msg_0x00: is_xiaoan = True

            if col == 0: return str(frame['seq'])
            if col == 1: return str(f_data.get('time', f_data.get('timestamp', 'N/A')))
            if col == 2: return frame['type']

            if col == 3:
                msg_type = frame['type']
                base_name = self.get_msg_name(msg_type).split('(')[0]
                if not is_xiaoan:
                    if msg_type in ('0x08', '0x28'):
                        ack_type = f_data.get('ack_msg_type')
                        prefix = "终端应答" if msg_type == '0x08' else "平台应答"
                        if ack_type:
                            ack_type_hex = f"0x{str(ack_type).upper()}"
                            ack_name = self.get_msg_name(ack_type_hex).split('(')[0]
                            return f"{prefix} ({ack_name})"
                        return f"通用{prefix}"
                    return base_name
                else:
                    if '下行' in direction and msg_type != '0x00': return f"平台回复 ({base_name})"
                    return base_name

            if col == 4:
                msg_type = frame['type']
                if not is_xiaoan:
                    if msg_type in ('0x08', '0x28'):
                        ack_type = f_data.get('ack_msg_type')
                        prefix = "终端应答" if msg_type == '0x08' else "平台应答"
                        if ack_type:
                            ack_type_hex = f"0x{str(ack_type).upper()}"
                            ack_name = self.get_msg_name(ack_type_hex).split('(')[0]
                            err_code = f_data.get('error_code')
                            if err_code and "成功" not in str(err_code) and str(err_code) != "0":
                                return f"[ACK] ❌ {prefix} ({ack_name}) [{err_code}]"
                            else:
                                return f"[ACK] ✅ {prefix} ({ack_name})"
                        return f"[ACK] ✅ 通用{prefix}"

                    if '下行' in direction:
                        base_name = self.get_msg_name(msg_type).split('(')[0]
                        summary = [f"{direction} 📥 {base_name}"]
                        params = []
                        for k, v in f_data.items():
                            if k not in ('time', 'timestamp', 'seq', '_note'): params.append(f"{k}:{v}")
                        if params: summary.append(f"({', '.join(params)})")
                        return " ".join(summary)

                else:
                    if '下行' in direction and msg_type != '0x00':
                        base_name = self.get_msg_name(msg_type).split('(')[0]
                        if msg_type == '0x23' and 'raw_body' in f_data:
                            import struct, binascii
                            try:
                                raw_hex = f_data['raw_body']
                                if len(raw_hex) == 8:
                                    ts = struct.unpack('>I', binascii.unhexlify(raw_hex))[0]
                                    return f"[ACK] ✅ {base_name} (平台同步时间戳: {ts})"
                            except:
                                pass
                        return f"[ACK] ✅ {base_name}"

                    if '下行' in direction and msg_type == '0x00':
                        summary = [f"{direction} 📥 透传命令"]
                        json_str = f_data.get('json_data', '')
                        if json_str: summary.append(f"📜 {json_str}")
                        return " ".join(summary)

                summary = []
                if direction: summary.append(f"{direction}")

                if msg_type == '0x00':
                    json_str = f_data.get('json_data', '')
                    if json_str: summary.append(f"📜 {json_str}")
                elif msg_type == '0x05':
                    alarm = f_data.get('alarm_type')
                    if alarm: summary.append(f"🚨 {alarm}")
                elif msg_type in ('0x34', '0x48'):
                    evt_type = f_data.get('type')
                    if evt_type: summary.append(f"📢 事件: {evt_type}")
                elif msg_type == '0x46':
                    faults = []
                    for k, v in f_data.items():
                        if str(k).startswith("Bit") and str(v) not in ("正常", "0", 0):
                            fault_name = k.split('_')[-1] if '_' in k else k
                            faults.append(f"{fault_name}:{v}")
                    if faults:
                        summary.append(f"🛠️ 故障: {'/'.join(faults)}")
                    else:
                        summary.append("✅ 全部正常")
                elif msg_type in ('0x44', '0x29'):
                    lat = f_data.get('latitude')
                    lon = f_data.get('longitude')
                    ts = f_data.get('timestamp')
                    if lon is not None and lat is not None: summary.append(f"📍 {lon}, {lat}")
                    if ts is not None: summary.append(f"🕒 {ts}")
                    if 'voltage' in f_data: summary.append(f"V:{f_data['voltage']}")
                    if 'SOC' in f_data:
                        summary.append(f"SOC:{f_data['SOC']}")
                    elif '电池SOC' in f_data:
                        summary.append(f"SOC:{f_data['电池SOC']}")

                elif 'alarm_bits' in f_data:
                    active_alarms = []
                    for alarm_name, is_active in f_data['alarm_bits'].items():
                        if is_active == 1: active_alarms.append(alarm_name)
                    if active_alarms: summary.append(f"🚨告警: {'/'.join(active_alarms)}")
                elif msg_type == '0x5C':
                    faults = []
                    fault_keys = ["Bit0_堵转", "Bit1_转把", "Bit2_欠压", "Bit3_过压", "Bit4_刹车", "Bit5_霍尔"]
                    for fk in fault_keys:
                        val = f_data.get(fk)
                        if val and val not in ("正常", 0, "0"): faults.append(str(val))
                    if faults:
                        summary.append(f"🛠️故障: {'/'.join(faults)}")
                    else:
                        summary.append("✅无故障")
                else:
                    if 'voltage' in f_data: summary.append(f"V:{f_data['voltage']}")
                    if 'SOC' in f_data:
                        summary.append(f"SOC:{f_data['SOC']}")
                    elif '电池SOC' in f_data:
                        summary.append(f"SOC:{f_data['电池SOC']}")

                if msg_type == '0x52':
                    pt1_lat = f_data.get('pt1_lat')
                    pt1_lng = f_data.get('pt1_lng')
                    pt1_time = f_data.get('pt1_time')
                    sat_count = f_data.get('sat_count')
                    if pt1_lng is not None and pt1_lat is not None: summary.append(f"📍 {pt1_lng}, {pt1_lat}")
                    if pt1_time is not None: summary.append(f"🕒 {pt1_time}")
                    if sat_count is not None: summary.append(f"🛰️ {sat_count}星")
                    total_pts = 0
                    if pt1_lat is not None: total_pts = 1
                    if 'point_list' in f_data: total_pts += len(f_data['point_list'])
                    summary.append(f"(共 {total_pts} 个点)")
                else:
                    lat_val = f_data.get('lat')
                    total_pts = 0
                    if lat_val is not None: total_pts = 1
                    if 'point_list' in f_data: total_pts += len(f_data['point_list'])
                    if total_pts > 0: summary.append(f"共包含 {total_pts} 个定位点")

                if 'health' in f_data: summary.append(f"健康度:{f_data['health']}%")
                return " ".join(summary) if summary else "无摘要"

    def get_msg_name(self, hex_type):
        return "详情见下"

    def get_raw_data(self, row):
        return self._data[row]


class EcuMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("多协议实时解析工作站 (GUI Pro 版)")
        self.resize(1300, 800)

        self.is_dark_mode = False
        self.all_frames = []
        self.filtered_frames = []
        self.decoder = None

        self.rt_tx_parser = None
        self.rt_rx_parser = None
        self.serial_buffer_line = ""
        self.serial_worker = None
        self._last_char_was_newline = True
        # 🌟 新增：实时录制状态
        self.is_recording = False
        self.record_filename = ""

        self.init_ui()

    def init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)

        # 🌟 减小主边缘空白，释放最大视觉空间
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(6)

        # ==========================================
        # 1. 顶部极简控制栏 (合并为单行，极其紧凑)
        # ==========================================
        top_bar_layout = QHBoxLayout()
        top_bar_layout.setContentsMargins(0, 0, 0, 0)

        # 串口控制区
        top_bar_layout.addWidget(QLabel("端口:"))
        self.combo_port = AutoRefreshComboBox(self)  # 🌟 替换为智能下拉框
        self.combo_port.setMinimumWidth(80)
        self.refresh_serial_ports()
        top_bar_layout.addWidget(self.combo_port)

        self.btn_refresh_port = QPushButton("🔄")
        self.btn_refresh_port.setFixedWidth(30)
        self.btn_refresh_port.clicked.connect(self.refresh_serial_ports)
        top_bar_layout.addWidget(self.btn_refresh_port)

        top_bar_layout.addWidget(QLabel("波特率:"))
        self.combo_baud = QComboBox()
        self.combo_baud.addItems(["9600", "38400", "57600", "115200", "230400", "460800", "921600", "2000000"])
        self.combo_baud.setCurrentText("115200")
        top_bar_layout.addWidget(self.combo_baud)

        self.btn_serial_toggle = QPushButton("🔌 打开")
        self.btn_serial_toggle.clicked.connect(self.toggle_serial)
        top_bar_layout.addWidget(self.btn_serial_toggle)

        # 竖线分割
        line1 = QWidget()
        line1.setFixedSize(1, 20)
        line1.setStyleSheet("background-color: #aaa;")
        top_bar_layout.addWidget(line1)

        # 协议与快捷解析区
        top_bar_layout.addWidget(QLabel("📜 协议:"))
        self.combo_protocol = QComboBox()
        self.populate_protocols()
        self.combo_protocol.currentIndexChanged.connect(self.change_protocol)
        top_bar_layout.addWidget(self.combo_protocol)

        self.quick_parse_input = QLineEdit()
        self.quick_parse_input.setPlaceholderText("粘贴报文快捷解析...")
        self.quick_parse_input.setClearButtonEnabled(True)
        top_bar_layout.addWidget(self.quick_parse_input)

        self.quick_parse_btn = QPushButton("🚀 解析")
        self.quick_parse_btn.clicked.connect(self.on_quick_parse_clicked)
        self.quick_parse_input.returnPressed.connect(self.on_quick_parse_clicked)
        top_bar_layout.addWidget(self.quick_parse_btn)

        # 竖线分割
        line2 = QWidget()
        line2.setFixedSize(1, 20)
        line2.setStyleSheet("background-color: #aaa;")
        top_bar_layout.addWidget(line2)

        # 辅助功能区
        top_bar_layout.addWidget(QLabel("筛选:"))
        self.combo_filter = QComboBox()
        self.combo_filter.addItem("显示所有类型", "ALL")
        self.combo_filter.currentIndexChanged.connect(self.apply_filter)
        top_bar_layout.addWidget(self.combo_filter)

        self.btn_load = QPushButton("📂 日志")
        self.btn_load.clicked.connect(self.load_file)
        top_bar_layout.addWidget(self.btn_load)

        self.btn_export = QPushButton("💾 导出")
        self.btn_export.clicked.connect(self.export_csv)
        self.btn_export.setEnabled(False)
        top_bar_layout.addWidget(self.btn_export)

        self.btn_theme = QPushButton("🌙 深色")
        self.btn_theme.clicked.connect(self.toggle_theme)
        top_bar_layout.addWidget(self.btn_theme)

        main_layout.addLayout(top_bar_layout)

        # ==========================================
        # 2. 三屏联动核心布局
        # ==========================================
        main_splitter = QSplitter(Qt.Orientation.Horizontal)

        # --- 左侧：原始终端区 ---
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        term_toolbar = QHBoxLayout()
        term_toolbar.setContentsMargins(0, 0, 0, 0)
        term_toolbar.addWidget(QLabel("🖥️ 终端控制台"))

        self.cb_timestamp = QCheckBox("时间戳")
        self.cb_timestamp.setChecked(True)
        self.cb_auto_scroll = QCheckBox("自动滚动")
        self.cb_auto_scroll.setChecked(True)

        # ==========================================
        # 🌟 新增：极速搜索框组件 (已修复 import 冲突)
        # ==========================================
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 搜索关键字 (回车向下)...")
        self.search_input.setMinimumWidth(180)
        self.search_input.setMaximumWidth(250)
        self.search_input.returnPressed.connect(self.search_next)

        self.btn_search_prev = QPushButton("向上")
        self.btn_search_prev.clicked.connect(self.search_prev)

        self.btn_search_next = QPushButton("向下")
        self.btn_search_next.clicked.connect(self.search_next)

        # 保存与清空按钮
        self.btn_save_term = QPushButton("💾 保存当前")
        self.btn_save_term.clicked.connect(self.save_raw_log)

        self.btn_record = QPushButton("⏺️ 录制")
        self.btn_record.clicked.connect(self.toggle_recording)

        self.btn_clear_term = QPushButton("🗑️ 清空")
        self.btn_clear_term.clicked.connect(self.clear_all_data)

        # 将搜索组件放在最左侧，然后加上弹簧把其他按钮挤到右边
        term_toolbar.addWidget(self.search_input)
        term_toolbar.addWidget(self.btn_search_prev)
        term_toolbar.addWidget(self.btn_search_next)

        term_toolbar.addStretch()  # 这个弹簧保持左右排版美观

        term_toolbar.addWidget(self.cb_timestamp)
        term_toolbar.addWidget(self.cb_auto_scroll)
        term_toolbar.addWidget(self.btn_save_term)
        term_toolbar.addWidget(self.btn_record)
        term_toolbar.addWidget(self.btn_clear_term)
        left_layout.addLayout(term_toolbar)

        self.raw_log_console = TerminalTextEdit(self)
        self.raw_log_console.setReadOnly(True)
        left_layout.addWidget(self.raw_log_console)
        main_splitter.addWidget(left_widget)

        # --- 右侧：解析详情区 ---
        right_splitter = QSplitter(Qt.Orientation.Vertical)

        # 🌟 右上角：表格与专属控制栏
        right_top_widget = QWidget()
        right_top_layout = QVBoxLayout(right_top_widget)
        right_top_layout.setContentsMargins(0, 0, 0, 0)

        table_toolbar = QHBoxLayout()
        table_toolbar.setContentsMargins(0, 0, 0, 0)
        table_toolbar.addWidget(QLabel("📊 解析流水线"))

        # 🌟 右侧专属的自动滚动复选框
        self.cb_table_auto_scroll = QCheckBox("自动滚动")
        self.cb_table_auto_scroll.setChecked(True)

        table_toolbar.addStretch()
        table_toolbar.addWidget(self.cb_table_auto_scroll)
        right_top_layout.addLayout(table_toolbar)

        # 使用我们刚才写的高级表格组件
        self.table_view = AutoScrollTableView(self)
        self.table_model = FrameTableModel()
        self.table_model.get_msg_name = lambda t: self.decoder.msgs.get(t, {}).get('name',
                                                                                   '未知') if self.decoder else '未知'
        self.table_view.setModel(self.table_model)
        self.table_view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table_view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table_view.horizontalHeader().setStretchLastSection(True)
        self.table_view.clicked.connect(self.on_row_clicked)
        self.table_view.selectionModel().currentChanged.connect(self.on_current_changed)

        right_top_layout.addWidget(self.table_view)
        right_splitter.addWidget(right_top_widget)

        # 右下角：字段结构树
        self.tree_view = QTreeView()
        self.tree_model = QStandardItemModel()
        self.tree_model.setHorizontalHeaderLabels(["字段结构解析详情"])
        self.tree_view.setModel(self.tree_model)
        self.tree_view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        right_splitter.addWidget(self.tree_view)

        right_splitter.setSizes([500, 300])
        main_splitter.addWidget(right_splitter)

        main_splitter.setSizes([400, 800])
        main_layout.addWidget(main_splitter)

        # ==========================================
        # 3. 底部极简状态栏 (下沉显示，绝不占用上方空间)
        # ==========================================
        self.statusBar().showMessage("状态: 待命")
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setMaximumWidth(200)
        self.statusBar().addPermanentWidget(self.progress_bar)

        self.change_protocol()
        self.setStyleSheet(self.get_light_qss())
        self.apply_terminal_style()

    # ==========================================
    # 串口监控核心逻辑
    # ==========================================
    def refresh_serial_ports(self):
        self.combo_port.clear()
        ports = serial.tools.list_ports.comports()
        for p in ports:
            self.combo_port.addItem(f"{p.device}", p.device)

    def toggle_serial(self):
        if self.serial_worker and self.serial_worker.isRunning():
            self.serial_worker.stop()
            self.btn_serial_toggle.setText("🔌 打开")
            self.btn_serial_toggle.setStyleSheet("")
            self.combo_port.setEnabled(True)
            self.combo_baud.setEnabled(True)
            self.statusBar().showMessage("状态: 串口已关闭")

            # 🌟 新增：关闭串口时，结束写入标记
            self.current_log_filename = None
        else:
            port = self.combo_port.currentData()
            baud = self.combo_baud.currentText()
            if not port:
                QMessageBox.warning(self, "错误", "未选择有效的串口！")
                return

            self.rt_tx_parser = StreamParser(self.decoder)
            self.rt_rx_parser = StreamParser(self.decoder)
            self.serial_buffer_line = ""

            self.serial_worker = SerialWorker(port, int(baud))
            self.serial_worker.data_received.connect(self.on_serial_data_received)
            self.serial_worker.error_occurred.connect(self.on_serial_error)
            self.serial_worker.start()

            self.btn_serial_toggle.setText("🛑 停止")
            self.btn_serial_toggle.setStyleSheet("background-color: #d32f2f; color: white; font-weight: bold;")
            self.combo_port.setEnabled(False)
            self.combo_baud.setEnabled(False)

            # 🌟 新增：在软件同级目录下，按当前时间自动生成一个 txt 日志文件名
            # os.makedirs("Logs", exist_ok=True)  # 自动创建一个Logs文件夹保持整洁
            # self.current_log_filename = f"Logs/COM_Log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"

            self.statusBar().showMessage(f"状态: 正在监听 {port} ({baud}bps)")

    def on_serial_error(self, err):
        # 🌟 修复无限弹窗：不要调用拨动开关 toggle_serial()
        # 而是直接老老实实地重置 UI 状态，彻底掐断死循环！
        if self.serial_worker:
            self.serial_worker.stop()

        self.btn_serial_toggle.setText("🔌 打开")
        self.btn_serial_toggle.setStyleSheet("")
        self.combo_port.setEnabled(True)
        self.combo_baud.setEnabled(True)
        self.statusBar().showMessage("状态: 串口已异常断开")
        self.current_log_filename = None

        # 最后再弹窗提示，避免阻塞后台清理
        QMessageBox.critical(self, "串口断开", f"硬件连接异常，已停止采集。\n详细信息: {err}")

    def append_raw_log(self, text):
        # ==========================================
        # 1. 注入时间戳处理
        # ==========================================
        if self.cb_timestamp.isChecked():
            now_str = datetime.now().strftime('%H:%M:%S.%f')[:-3]
            time_prefix = f"[{now_str}] "
            processed_text = ""
            if self._last_char_was_newline: processed_text += time_prefix
            processed_text += text.replace('\n', f'\n{time_prefix}')
            if processed_text.endswith(time_prefix): processed_text = processed_text[:-len(time_prefix)]
            self._last_char_was_newline = text.endswith('\n')
            final_text = processed_text
        else:
            final_text = text
            self._last_char_was_newline = text.endswith('\n')

        # ==========================================
        # 2. 磁带机实时录制 (写硬盘)
        # ==========================================
        if getattr(self, 'is_recording', False) and self.record_filename:
            try:
                with open(self.record_filename, 'a', encoding='utf-8', errors='ignore') as f:
                    f.write(final_text)
            except Exception as e:
                self.statusBar().showMessage(f"⚠️ 写入录制文件失败: {str(e)}")

        # ==========================================
        # 3. 满血版富文本渲染与插入 (唯一插入点)
        # ==========================================
        scrollbar = self.raw_log_console.verticalScrollBar()
        current_scroll = scrollbar.value()

        cursor = self.raw_log_console.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)

        from PyQt6.QtGui import QTextBlockFormat
        block_format = QTextBlockFormat()
        block_format.setBottomMargin(8)  # 🌟 这里控制那完美的 8 像素行间距
        cursor.setBlockFormat(block_format)

        # 🚨 整个方法中，这一句绝不能出现第二次！
        cursor.insertText(final_text)

        # ==========================================
        # 4. 视口冻结与自动滚动控制
        # ==========================================
        if self.cb_auto_scroll.isChecked():
            scrollbar.setValue(scrollbar.maximum())
        else:
            scrollbar.setValue(current_scroll)

    def on_serial_data_received(self, text):
        self.append_raw_log(text)
        self.serial_buffer_line += text
        if '\n' in self.serial_buffer_line:
            lines = self.serial_buffer_line.split('\n')
            self.serial_buffer_line = lines.pop()

            parsed_frames = []
            for line in lines:
                line_lower = line.lower()
                if "nb_recv" in line_lower or "接收" in line_lower:
                    _frames = self.rt_rx_parser.feed(line)
                    for fr in _frames: fr['direction'] = '[下行]'
                    parsed_frames.extend(_frames)
                elif "nb_send" in line_lower or "发送" in line_lower:
                    _frames = self.rt_tx_parser.feed(line)
                    for fr in _frames: fr['direction'] = '[上行]'
                    parsed_frames.extend(_frames)
                else:
                    _frames = self.rt_tx_parser.feed(line)
                    for fr in _frames: fr['direction'] = ''
                    parsed_frames.extend(_frames)

            if parsed_frames:
                for frame in parsed_frames:
                    msg_def = self.decoder.msgs.get(frame['type'], {})
                    frame['name'] = msg_def.get('name', '未知消息')
                    if frame.get('seq') is None or frame.get('seq') == "N/A": frame['seq'] = "实时"
                self.all_frames.extend(parsed_frames)

                target_type = self.combo_filter.currentData()
                if target_type == "ALL" or not target_type:
                    self.filtered_frames.extend(parsed_frames)
                    self.table_model.append_frames(parsed_frames)
                else:
                    valid_frames = [f for f in parsed_frames if f['type'] == target_type]
                    if valid_frames:
                        self.filtered_frames.extend(valid_frames)
                        self.table_model.append_frames(valid_frames)

                self.update_filter_combo_silently()

                # 🌟 改为判断右侧自己专属的开关
                if self.cb_table_auto_scroll.isChecked() and self.filtered_frames:
                    self.table_view.scrollToBottom()

                self.btn_export.setEnabled(True)

    def update_filter_combo_silently(self):
        types = set(f['type'] for f in self.all_frames)
        current = self.combo_filter.currentData()
        self.combo_filter.blockSignals(True)
        self.combo_filter.clear()
        self.combo_filter.addItem("显示所有类型", "ALL")
        for t in sorted(types):
            name = self.decoder.msgs.get(t, {}).get('name', 'Unknown')
            self.combo_filter.addItem(f"{t} - {name}", t)
        idx = self.combo_filter.findData(current)
        if idx >= 0: self.combo_filter.setCurrentIndex(idx)
        self.combo_filter.blockSignals(False)

    # ==========================================
    # 🌟 新增：手动保存左侧终端日志
    # ==========================================
    def save_raw_log(self):
        text = self.raw_log_console.toPlainText()
        if not text.strip():
            QMessageBox.information(self, "提示", "当前控制台没有内容可保存！")
            return

        # 弹出保存文件对话框，默认文件名带上当前时间
        filename, _ = QFileDialog.getSaveFileName(
            self, "保存串口原始日志",
            f"SerialLog_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
            "Text Files (*.txt);;All Files (*)"
        )
        if not filename: return  # 用户取消了保存

        try:
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(text)
            self.statusBar().showMessage(f"✅ 串口日志已成功保存至: {filename}")
            QMessageBox.information(self, "保存成功", "原始串口日志导出完毕！")
        except Exception as e:
            QMessageBox.critical(self, "保存失败", str(e))

    # ==========================================
    # 🌟 新增：实时录制开关控制逻辑
    # ==========================================
    def toggle_recording(self):
        if not self.is_recording:
            # 准备开始录制，先让用户选个保存文件的地方
            filename, _ = QFileDialog.getSaveFileName(
                self, "选择实时录制日志存放位置",
                f"Record_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                "Text Files (*.txt);;All Files (*)"
            )
            if not filename: return  # 用户点取消就不录了

            self.record_filename = filename
            self.is_recording = True

            # 按钮变成醒目的红色“停止”状态
            self.btn_record.setText("⏹️ 停止录制")
            self.btn_record.setStyleSheet("color: #EF4444; font-weight: bold;")
            self.statusBar().showMessage(f"🔴 正在实时录制日志至: {filename}")
        else:
            # 停止录制
            self.is_recording = False
            self.record_filename = ""

            # 按钮恢复原样
            self.btn_record.setText("⏺️ 开始录制")
            self.btn_record.setStyleSheet("")
            self.statusBar().showMessage("⏹️ 实时录制已安全停止！")

    def clear_all_data(self):
        self.raw_log_console.clear()
        self.all_frames.clear()
        self.filtered_frames.clear()
        self.table_model.update_data([])
        self.tree_model.removeRows(0, self.tree_model.rowCount())
        if self.rt_tx_parser: self.rt_tx_parser.buffer.clear()
        if self.rt_rx_parser: self.rt_rx_parser.buffer.clear()
        self.serial_buffer_line = ""
        self.statusBar().showMessage("状态: 数据已清空")

    # ==========================================
    # 🌟 新增：日志关键字搜索核心逻辑
    # ==========================================
    def search_next(self):
        self._execute_search(backward=False)

    def search_prev(self):
        self._execute_search(backward=True)

    def _execute_search(self, backward=False):
        from PyQt6.QtGui import QTextDocument, QTextCursor, QColor
        from PyQt6.QtWidgets import QTextEdit

        keyword = self.search_input.text()

        # 1. 触发底层渲染引擎，对【全文档】符合条件的词铺上全局底色
        if hasattr(self.raw_log_console, 'highlighter'):
            self.raw_log_console.highlighter.set_search_keyword(keyword)

        if not keyword:
            self.raw_log_console.setExtraSelections([])  # 清除焦点高亮
            return

        options = QTextDocument.FindFlag(0)  # 默认不区分大小写
        if backward:
            options |= QTextDocument.FindFlag.FindBackward

        found = self.raw_log_console.find(keyword, options)

        # 智能折返逻辑
        if not found:
            cursor = self.raw_log_console.textCursor()
            if backward:
                cursor.movePosition(QTextCursor.MoveOperation.End)
            else:
                cursor.movePosition(QTextCursor.MoveOperation.Start)
            self.raw_log_console.setTextCursor(cursor)

            found = self.raw_log_console.find(keyword, options)
            if not found:
                self.statusBar().showMessage(f"⚠️ 搜索完毕：未找到 '{keyword}'")
                self.search_input.setStyleSheet("border: 1px solid #EF4444;")
                self.raw_log_console.setExtraSelections([])
            else:
                self.statusBar().showMessage(f"🔄 已折返并找到 '{keyword}'")
                self.search_input.setStyleSheet("")
        else:
            self.statusBar().showMessage(f"✅ 找到匹配项 '{keyword}'")
            self.search_input.setStyleSheet("")

            # =========================================================
        # 🌟 2. 单点爆破：用最极其刺眼的颜色，标出【当前跳到的这一个词】
        # =========================================================
        if found:
            extra_selections = []
            selection = QTextEdit.ExtraSelection()

            # 设置【当前选中点】为极具冲击力的：亮橙色/亮黄色 + 纯黑字
            selection.format.setBackground(QColor("#FF9800"))
            selection.format.setForeground(QColor("#000000"))

            cursor = self.raw_log_console.textCursor()
            selection.cursor = QTextCursor(cursor)
            extra_selections.append(selection)

            self.raw_log_console.setExtraSelections(extra_selections)

            # 智能挪动隐形光标，防止向上搜索卡死
            if backward:
                cursor.setPosition(cursor.selectionStart())
            else:
                cursor.setPosition(cursor.selectionEnd())
            self.raw_log_console.setTextCursor(cursor)

            if self.cb_auto_scroll.isChecked():
                self.cb_auto_scroll.setChecked(False)
                self.statusBar().showMessage("⏸️ 触发搜索，已暂停自动滚动", 3000)

    def populate_protocols(self):
        json_files = [f for f in os.listdir('.') if f.endswith('.json')]
        if not json_files:
            QMessageBox.warning(self, "警告", "当前目录下没有找到任何 .json 协议文件！")
            return
        for jf in json_files: self.combo_protocol.addItem(jf, jf)

    def change_protocol(self):
        protocol_file = self.combo_protocol.currentData()
        if not protocol_file: return
        try:
            self.decoder = ProtocolDecoder(protocol_file)
            self.clear_all_data()
            self.combo_filter.blockSignals(True)
            self.combo_filter.clear()
            self.combo_filter.addItem("显示所有类型", "ALL")
            self.combo_filter.blockSignals(False)
            self.statusBar().showMessage(f"✅ 已切换协议为: {protocol_file}")

            if self.serial_worker and self.serial_worker.isRunning():
                self.rt_tx_parser = StreamParser(self.decoder)
                self.rt_rx_parser = StreamParser(self.decoder)
        except Exception as e:
            QMessageBox.critical(self, "协议加载失败", str(e))

    def on_quick_parse_clicked(self):
        import traceback
        try:
            raw_text = self.quick_parse_input.text().strip()
            if not raw_text: return
            if self.decoder is None:
                QMessageBox.warning(self, "警告", "底层协议配置未加载！")
                return

            tx_parser = StreamParser(self.decoder)
            rx_parser = StreamParser(self.decoder)
            parsed_frames = []

            for line in raw_text.splitlines():
                line_lower = line.lower()
                if "nb_recv" in line_lower or "接收" in line_lower:
                    _frames = rx_parser.feed(line)
                    for fr in _frames: fr['direction'] = '[下行]'
                    parsed_frames.extend(_frames)
                elif "nb_send" in line_lower or "发送" in line_lower:
                    _frames = tx_parser.feed(line)
                    for fr in _frames: fr['direction'] = '[上行]'
                    parsed_frames.extend(_frames)
                else:
                    _frames = tx_parser.feed(line)
                    for fr in _frames: fr['direction'] = ''
                    parsed_frames.extend(_frames)

            if not parsed_frames:
                QMessageBox.warning(self, "解析失败", "未能识别出有效的协议帧。")
                return

            for frame in parsed_frames:
                msg_def = self.decoder.msgs.get(frame['type'], {})
                frame['name'] = msg_def.get('name', '未知消息')
                if frame.get('seq') is None or frame.get('seq') == "N/A": frame['seq'] = "手动"
                self.all_frames.append(frame)

            self.update_filter_combo_silently()
            self.apply_filter()

            if self.filtered_frames:
                model_index = self.table_model.index(len(self.filtered_frames) - 1, 0)
                self.table_view.scrollToBottom()
                self.table_view.setCurrentIndex(model_index)
                self.on_row_clicked(model_index)

            self.statusBar().showMessage("⚡ 快速解析成功！已追加至列表。")
            self.quick_parse_input.clear()
        except Exception as e:
            QMessageBox.critical(self, "程序崩溃拦截", f"底层解析抛出异常：\n{traceback.format_exc()}")

    def load_file(self):
        if self.decoder is None: return
        file_path, _ = QFileDialog.getOpenFileName(self, "选择日志文件", "", "Text Files (*.txt *.log);;All Files (*)")
        if not file_path: return

        self.clear_all_data()
        self.btn_load.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(0)
        self.statusBar().showMessage("正在离线清洗和解析日志中...")

        self.worker = ParseWorker(file_path, self.decoder)
        self.worker.batch_ready.connect(lambda frames: self.all_frames.extend(frames))
        self.worker.progress.connect(lambda count: self.statusBar().showMessage(f"已解析 {count} 条..."))
        self.worker.finished.connect(self.on_parse_finished)
        self.worker.error.connect(lambda err: QMessageBox.warning(self, "解析出错", err))
        self.worker.start()

    def on_parse_finished(self, total_count):
        self.btn_load.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.statusBar().showMessage(f"解析完成！共提取 {total_count} 条有效指令。")
        self.btn_export.setEnabled(True)

        for frame in self.all_frames:
            msg_def = self.decoder.msgs.get(frame['type'], {})
            frame['name'] = msg_def.get('name', '未知消息')

        self.update_filter_combo_silently()
        self.apply_filter()

    def apply_filter(self):
        target_type = self.combo_filter.currentData()
        if target_type == "ALL" or not target_type:
            self.filtered_frames = self.all_frames[:]
        else:
            self.filtered_frames = [f for f in self.all_frames if f['type'] == target_type]

        self.table_model.update_data(self.filtered_frames)
        self.statusBar().showMessage(f"当前视图: {len(self.filtered_frames)} 条记录")
        self.tree_model.removeRows(0, self.tree_model.rowCount())

    def on_current_changed(self, current, previous):
        if current.isValid(): self.on_row_clicked(current)

    def on_row_clicked(self, index):
        if not index.isValid(): return
        frame = self.table_model.get_raw_data(index.row())

        self.tree_model.removeRows(0, self.tree_model.rowCount())
        root_node = self.tree_model.invisibleRootItem()

        info = QStandardItem(f"[基本信息] Seq: {frame.get('seq', '')}, Type: {frame['type']}")
        info.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
        root_node.appendRow(info)

        self._populate_tree(root_node, frame['data'])
        self.tree_view.expandAll()

    def _populate_tree(self, parent_item, data_node):
        if isinstance(data_node, dict):
            keys = list(data_node.keys())
            if 'time' in keys: keys.remove('time'); keys.insert(0, 'time')
            for key in keys:
                val = data_node[key]
                if isinstance(val, (dict, list)):
                    node = QStandardItem(str(key))
                    node.setForeground(Qt.GlobalColor.darkBlue if not self.is_dark_mode else Qt.GlobalColor.cyan)
                    parent_item.appendRow(node)
                    self._populate_tree(node, val)
                else:
                    item = QStandardItem(f"{key}: {val}")
                    parent_item.appendRow(item)
        elif isinstance(data_node, list):
            for i, item in enumerate(data_node):
                if isinstance(item, (dict, list)):
                    node = QStandardItem(f"[{i}]")
                    node.setForeground(Qt.GlobalColor.darkRed if not self.is_dark_mode else Qt.GlobalColor.yellow)
                    parent_item.appendRow(node)
                    self._populate_tree(node, item)
                else:
                    child = QStandardItem(f"[{i}]: {item}")
                    parent_item.appendRow(child)

    def export_csv(self):
        if not self.filtered_frames: return
        filename, _ = QFileDialog.getSaveFileName(self, "保存 CSV",
                                                  f"export_{datetime.now().strftime('%Y%m%d%H%M')}.csv",
                                                  "CSV Files (*.csv)")
        if not filename: return

        field_names = set(['seq', 'type'])
        processed_rows = []
        for frame in self.filtered_frames:
            row = {'seq': frame['seq'], 'type': frame['type']}
            for k, v in frame['data'].items():
                if isinstance(v, (dict, list)):
                    row[k] = json.dumps(v, ensure_ascii=False)
                else:
                    row[k] = v
                field_names.add(k)
            processed_rows.append(row)
        sorted_fields = ['seq', 'type'] + sorted([f for f in field_names if f not in ['seq', 'type']])

        try:
            with open(filename, 'w', newline='', encoding='utf-8-sig') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=sorted_fields)
                writer.writeheader()
                writer.writerows(processed_rows)
            QMessageBox.information(self, "导出成功", f"成功导出 {len(processed_rows)} 条数据！")
        except Exception as e:
            QMessageBox.critical(self, "导出失败", str(e))

    def toggle_theme(self):
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtCore import Qt

        # =========================================================
        # 🚀 性能优化 1：瞬间变成“转圈/沙漏”鼠标，提升 UX 体验
        # =========================================================
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        # 强制刷新一下事件循环，确保鼠标状态瞬间改变，不被后续的计算阻塞
        QApplication.processEvents()

        # =========================================================
        # 🚀 性能优化 2：【核心大招】强行挂起整个主界面的 UI 渲染引擎！
        # 屏蔽所有中间过程的重绘，防止 QTextEdit 一行行重新计算排版导致卡死
        # =========================================================
        self.setUpdatesEnabled(False)

        try:
            self.is_dark_mode = not self.is_dark_mode
            if self.is_dark_mode:
                self.btn_theme.setText("☀️ 浅色")
                self.setStyleSheet(self.get_dark_qss())
            else:
                self.btn_theme.setText("🌙 深色")
                self.setStyleSheet(self.get_light_qss())

            # 这里面包含了最耗时的正则重新高亮 rehighlight()
            self.apply_terminal_style()

            # 强制表格重新渲染
            if hasattr(self, 'table_model'):
                self.table_model.layoutChanged.emit()

        finally:
            # =========================================================
            # 🚀 性能优化 3：恢复 UI 渲染，把计算好的最终画面“唰”地一下一次性贴上去
            # =========================================================
            self.setUpdatesEnabled(True)

            # 恢复正常的鼠标指针
            QApplication.restoreOverrideCursor()

    def apply_terminal_style(self):
        # 1. 设置极简护眼的终端基底色调 (告别刺眼纯绿)
        if self.is_dark_mode:
            # 深色模式：VSCode 经典黑灰底 + 柔和白字
            self.raw_log_console.setStyleSheet("background-color: #1E1E1E; color: #D4D4D4; border: 1px solid #43454a;")
        else:
            # 浅色模式：GitHub 极简白底 + 深灰字
            self.raw_log_console.setStyleSheet("background-color: #FAFAFA; color: #24292E; border: 1px solid #d1d5db;")

        # 2. 🌟 通知智能高亮引擎切换色彩策略
        if hasattr(self.raw_log_console, 'highlighter'):
            self.raw_log_console.highlighter.update_theme(self.is_dark_mode)

    def get_light_qss(self):
        return """
        QWidget { background-color: #f3f4f6; color: #1f2937; font-family: "Microsoft YaHei", "Segoe UI"; }
        QLineEdit, QTextEdit, QComboBox, QCheckBox { background-color: #ffffff; color: #1f2937; border: 1px solid #d1d5db; border-radius: 4px; padding: 4px; }
        QPushButton { background-color: #ffffff; color: #374151; border: 1px solid #d1d5db; border-radius: 4px; padding: 4px 8px; }
        QPushButton:hover { background-color: #e5e7eb; color: #111827; }
        QTableView { background-color: #ffffff; color: #1f2937; gridline-color: #e5e7eb; border: 1px solid #d1d5db; selection-background-color: #3b82f6; selection-color: #ffffff; alternate-background-color: #f9fafb; }
        QTreeView { background-color: #ffffff; color: #1f2937; border: 1px solid #d1d5db; selection-background-color: #3b82f6; selection-color: #ffffff; }
        QHeaderView::section { background-color: #f3f4f6; color: #374151; border: none; border-right: 1px solid #d1d5db; border-bottom: 1px solid #d1d5db; padding: 4px; font-weight: bold; }
        QSplitter::handle { background-color: #d1d5db; width: 2px; }
        QSplitter::handle:horizontal:hover { background-color: #3b82f6; }
        QScrollBar:vertical { background: #f3f4f6; width: 12px; margin: 0px; }
        QScrollBar::handle:vertical { background: #d1d5db; border-radius: 6px; min-height: 20px; }
        QScrollBar::handle:vertical:hover { background: #9ca3af; }
        """

    def get_dark_qss(self):
        return """
        QWidget { background-color: #2b2d30; color: #a9b7c6; font-family: "Microsoft YaHei", "Segoe UI"; }
        QLineEdit, QTextEdit, QComboBox, QCheckBox { background-color: #1e1f22; color: #a9b7c6; border: 1px solid #43454a; border-radius: 4px; padding: 4px; }
        QPushButton { background-color: #36393f; color: #a9b7c6; border: 1px solid #43454a; border-radius: 4px; padding: 4px 8px; }
        QPushButton:hover { background-color: #43454a; color: #ffffff; }
        QPushButton:pressed { background-color: #2b2d30; }
        QTableView { background-color: #1e1f22; color: #a9b7c6; gridline-color: #393b40; border: 1px solid #43454a; selection-background-color: #2f65ca; selection-color: #ffffff; }
        QTreeView { background-color: #1e1f22; color: #a9b7c6; border: 1px solid #43454a; selection-background-color: #2f65ca; selection-color: #ffffff; }
        QHeaderView::section { background-color: #2b2d30; color: #a9b7c6; border: none; border-right: 1px solid #43454a; border-bottom: 1px solid #43454a; padding: 4px; font-weight: bold; }
        QSplitter::handle { background-color: #43454a; width: 2px; }
        QSplitter::handle:horizontal:hover { background-color: #3574d0; }
        QScrollBar:vertical { background: #2b2d30; width: 12px; margin: 0px; }
        QScrollBar::handle:vertical { background: #565a60; border-radius: 6px; min-height: 20px; }
        QScrollBar::handle:vertical:hover { background: #6f737a; }
        """


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = EcuMainWindow()
    window.show()
    sys.exit(app.exec())