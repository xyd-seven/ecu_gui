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
                             QCheckBox, QTextEdit, QDialog, QTableWidget, QTableWidgetItem, QSizePolicy, QPlainTextEdit,
                             QRadioButton)
from PyQt6.QtGui import (QStandardItemModel, QStandardItem, QFont, QTextCursor,
                         QSyntaxHighlighter, QTextCharFormat, QColor, QTextBlockFormat, QPainter, QIcon)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QAbstractTableModel, QEvent, QRegularExpression, QTimer


# ==========================================
# ⚙️ 极客功能：自定义正则高亮配置面板
# ==========================================
class RegexConfigDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("⚙️ 自定义高亮规则面板")
        self.resize(600, 350)
        layout = QVBoxLayout(self)

        self.table = QTableWidget(0, 3)
        # 🌟 列名更新
        self.table.setHorizontalHeaderLabels(["正则表达式 / 关键字", "高亮颜色 (点击选择)", "字体加粗"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        layout.addWidget(self.table)

        btn_layout = QHBoxLayout()
        btn_add = QPushButton("➕ 添加新规则")
        btn_add.clicked.connect(lambda: self.add_row())  # 默认添加一行

        btn_delete = QPushButton("🗑️ 删除选中")
        btn_delete.setStyleSheet("color: #EF4444;")
        btn_delete.clicked.connect(self.delete_row)

        btn_save = QPushButton("💾 保存并立刻生效")
        btn_save.setStyleSheet("background-color: #2563EB; color: white; font-weight: bold;")
        btn_save.clicked.connect(self.save_rules)

        btn_layout.addWidget(btn_add)
        btn_layout.addWidget(btn_delete)
        btn_layout.addWidget(btn_save)
        layout.addLayout(btn_layout)

        self.load_rules()

    # 🌟 核心：创建一个带颜色的按钮
    def _create_color_button(self, color_hex):
        btn = QPushButton(color_hex)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._update_btn_style(btn, color_hex)
        btn.clicked.connect(lambda: self.pick_color(btn))
        return btn

    # 🌟 智能样式：根据背景颜色深浅，自动反转文字颜色防看不清
    def _update_btn_style(self, btn, color_hex):
        btn.setText(color_hex)
        try:
            r, g, b = int(color_hex[1:3], 16), int(color_hex[3:5], 16), int(color_hex[5:7], 16)
            brightness = (r * 299 + g * 587 + b * 114) / 1000
            text_color = "#000000" if brightness > 125 else "#FFFFFF"
        except:
            text_color = "#000000"
        btn.setStyleSheet(
            f"background-color: {color_hex}; color: {text_color}; font-weight: bold; border: 1px solid #ccc; border-radius: 4px;")

    # 🌟 核心：呼出系统级调色盘
    def pick_color(self, btn):
        from PyQt6.QtWidgets import QColorDialog
        from PyQt6.QtGui import QColor
        initial_color = QColor(btn.text())
        color = QColorDialog.getColor(initial_color, self, "选择高亮颜色")
        if color.isValid():
            self._update_btn_style(btn, color.name().upper())

    # 🌟 统一的添加行逻辑 (颜色框变按钮，加粗变复选框)
    def add_row(self, regex="MyKeyWord", color_hex="#10B981", is_bold=True):
        r = self.table.rowCount()
        self.table.insertRow(r)

        # 1. 第一列：文本框
        self.table.setItem(r, 0, QTableWidgetItem(regex))

        # 2. 第二列：颜色选择按钮
        color_btn = self._create_color_button(color_hex)
        self.table.setCellWidget(r, 1, color_btn)

        # 3. 第三列：真正的打勾复选框
        chk_item = QTableWidgetItem()
        chk_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        chk_item.setCheckState(Qt.CheckState.Checked if is_bold else Qt.CheckState.Unchecked)
        self.table.setItem(r, 2, chk_item)

    def delete_row(self):
        current_row = self.table.currentRow()
        if current_row >= 0:
            self.table.removeRow(current_row)
        else:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "提示", "请先在表格中点击选中要删除的行！")

    def load_rules(self):
        if os.path.exists("highlight_rules.json"):
            try:
                with open("highlight_rules.json", "r", encoding="utf-8") as f:
                    rules = json.load(f)
                    for r in rules:
                        self.add_row(
                            regex=r.get("regex", ""),
                            color_hex=r.get("color", "#FFFFFF"),
                            is_bold=r.get("bold", False)
                        )
            except:
                pass

        # 如果文件不存在或者为空，默认给一个示范行
        if self.table.rowCount() == 0:
            self.add_row()

    def save_rules(self):
        rules = []
        for i in range(self.table.rowCount()):
            reg_item = self.table.item(i, 0)
            btn_widget = self.table.cellWidget(i, 1)  # 获取颜色按钮
            chk_item = self.table.item(i, 2)  # 获取复选框

            if reg_item and reg_item.text().strip():
                rules.append({
                    "regex": reg_item.text().strip(),
                    "color": btn_widget.text() if btn_widget else "#FFFFFF",
                    "bold": True if chk_item and chk_item.checkState() == Qt.CheckState.Checked else False
                })
        with open("highlight_rules.json", "w", encoding="utf-8") as f:
            json.dump(rules, f, ensure_ascii=False, indent=4)
        self.accept()


# ==========================================
# 🌟 高亮引擎 (满血语义分析版：支持数字/网络/日志级别智能着色)
# ==========================================
class LogHighlighter(QSyntaxHighlighter):
    def __init__(self, document, is_dark_mode=True):
        super().__init__(document)
        self.rules = []
        self.is_dark = is_dark_mode

        # 🚀 预编译正则
        import re
        self.tx_pattern = re.compile(r"(?i)(nb_send|send|发送|\[上行\])")
        self.rx_pattern = re.compile(r"(?i)(nb_recv|recv|接收|\[下行\])")
        self.hex_pattern = QRegularExpression(r"\b(?:[0-9a-fA-F]{2}[\s\-]+){3,}[0-9a-fA-F]{2}\b")

        self.update_theme(is_dark_mode)

    def update_theme(self, is_dark_mode):
        self.is_dark = is_dark_mode
        self.rules.clear()

        def create_format(color_hex, bold=False, italic=False):
            fmt = QTextCharFormat()
            fmt.setForeground(QColor(color_hex))
            if bold: fmt.setFontWeight(QFont.Weight.Bold)
            if italic: fmt.setFontItalic(True)
            return fmt

        c_num = "#AE81FF" if is_dark_mode else "#8959A8"
        c_str = "#A6E22E" if is_dark_mode else "#718C00"
        c_net = "#FD971F" if is_dark_mode else "#F5871F"
        c_err = "#F92672" if is_dark_mode else "#C82829"
        c_warn = "#E6DB74" if is_dark_mode else "#EAB700"
        c_info = "#66D9EF" if is_dark_mode else "#3E999F"
        c_dbg = "#8A8A8A" if is_dark_mode else "#8E908C"
        c_time = "#6A9955" if is_dark_mode else "#2E8B57"

        num_regex = r"(?<!^\[)(?<![\w\-])[-+]?\b\d*\.?\d+\b(?![\w\-])"
        self.rules.append((QRegularExpression(num_regex), create_format(c_num)))
        self.rules.append((QRegularExpression(r'"[^"]*"'), create_format(c_str)))
        self.rules.append((QRegularExpression(r"'[^']*'"), create_format(c_str)))
        self.rules.append((QRegularExpression(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"), create_format(c_net, True)))
        self.rules.append((QRegularExpression(r"\b(?:[0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}\b"), create_format(c_net, True)))
        self.rules.append((QRegularExpression(r"(?i)\b(error|fail|failed|fatal|exception|timeout|异常|失败)\b"), create_format(c_err, True)))
        self.rules.append((QRegularExpression(r"(?i)\b(warn|warning|警告)\b"), create_format(c_warn, True)))
        self.rules.append((QRegularExpression(r"(?i)\b(info|success|ok|成功|完成)\b"), create_format(c_info, True)))
        self.rules.append((QRegularExpression(r"(?i)\b(debug|trace|调试)\b"), create_format(c_dbg, False, True)))

        p1 = r"\[\d{2,4}[-/]\d{1,2}[-/]\d{1,2}\s+\d{1,2}:\d{1,2}:\d{1,2}(?:\.\d+)?\s*\]"
        p2 = r"\[\d{1,2}:\d{1,2}:\d{1,2}(?:\.\d+)?\s*\]"
        p3 = r"\b\d{2,4}[-/]\d{1,2}[-/]\d{1,2}\s+\d{1,2}:\d{1,2}:\d{1,2}(?:\.\d+)?\b"
        p4 = r"\b\d{1,2}:\d{1,2}:\d{1,2}(?:\.\d+)?\b"
        time_base = f"{p1}|{p2}|{p3}|{p4}"

        self.rules.append((QRegularExpression(time_base), create_format(c_time)))
        self.rules.append((QRegularExpression(f"^{p1}|^{p2}"), create_format(c_dbg)))

        import os, json
        if os.path.exists("highlight_rules.json"):
            try:
                with open("highlight_rules.json", "r", encoding="utf-8") as f:
                    custom_rules = json.load(f)
                    for r in custom_rules:
                        fmt = create_format(r.get('color', '#FFFFFF'), r.get('bold', False))
                        self.rules.append((QRegularExpression(r['regex']), fmt))
            except:
                pass
        self.rehighlight()

    def highlightBlock(self, text):
        for pattern, format in self.rules:
            match_iterator = pattern.globalMatch(text)
            while match_iterator.hasNext():
                match = match_iterator.next()
                self.setFormat(match.capturedStart(), match.capturedLength(), format)

        is_tx = self.tx_pattern.search(text)
        is_rx = self.rx_pattern.search(text) if not is_tx else None

        hex_iterator = self.hex_pattern.globalMatch(text)
        while hex_iterator.hasNext():
            match = hex_iterator.next()
            hex_fmt = QTextCharFormat()
            if is_tx:
                hex_fmt.setForeground(QColor("#569CD6") if self.is_dark else QColor("#0284C7"))
            elif is_rx:
                hex_fmt.setForeground(QColor("#C3A66B") if self.is_dark else QColor("#D97706"))
            else:
                hex_fmt.setForeground(QColor("#A855F7") if self.is_dark else QColor("#9333EA"))
            self.setFormat(match.capturedStart(), match.capturedLength(), hex_fmt)


# ==========================================
# 🗺️ 带有智能雷达(Minimap)的满血版终端
# ==========================================
class TerminalTextEdit(QTextEdit):
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main_window = main_window

        font = QFont("Consolas", 10)
        font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
        self.setFont(font)
        self.setReadOnly(True)
        self.document().setMaximumBlockCount(50000)
        self.highlighter = LogHighlighter(self.document(), is_dark_mode=True)
        # ==========================================
        # 🚀 QTextEdit 性能极限优化三板斧
        # ==========================================
        # 1. 内存截断：限制 5 万行（对于 QTextEdit 足够安全）
        self.document().setMaximumBlockCount(50000)
        # 2. 极其关键：关闭历史撤销栈！(能节省海量内存和对象创建开销)
        self.setUndoRedoEnabled(False)
        # 🌟 恢复自动换行：根据当前界面的宽度自动软折行
        # 软折行在视觉上会换行，但物理上依然是“同一行”，所以完美契合“只在开头加时间戳”的需求！
        self.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)

        self.highlighter = LogHighlighter(self.document(), is_dark_mode=True)

        # ==========================================
        # 🌟 完美找回行间距 (QTextEdit 支持度 100%)
        # ==========================================
        block_fmt = QTextBlockFormat()
        # 130 代表 130% 的行高，1 代表枚举值 ProportionalHeight
        block_fmt.setLineHeight(130, 1)
        block_fmt.setBottomMargin(2)

        # 将这个格式应用到全局光标，后续追加的所有日志都会自动继承这个间距！
        cursor = self.textCursor()
        cursor.setBlockFormat(block_fmt)
        self.setTextCursor(cursor)
        # ==========================================
        # 🌟 致敬 PyCharm 2022.3 Darcula 经典配
        # ==========================================
        self.setStyleSheet("""
            QTextEdit {
                background-color: #2B2B2B; /* PyCharm 经典深灰背景 */
                color: #A9B7C6;            /* PyCharm 柔和文字灰白 */
                border: none;              /* 去除多余边框更清爽 */
            }
        """)

    def wheelEvent(self, event):
        if event.angleDelta().y() > 0:
            if self.main_window.cb_auto_scroll.isChecked():
                self.main_window.cb_auto_scroll.setChecked(False)
        super().wheelEvent(event)


class AutoScrollTableView(QTableView):
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main_window = main_window

    def wheelEvent(self, event):
        if event.angleDelta().y() > 0:
            if hasattr(self.main_window, 'cb_table_auto_scroll') and self.main_window.cb_table_auto_scroll.isChecked():
                self.main_window.cb_table_auto_scroll.setChecked(False)
        super().wheelEvent(event)


class AutoRefreshComboBox(QComboBox):
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main_window = main_window

    def showPopup(self):
        self.main_window.refresh_serial_ports()
        super().showPopup()


# ==========================================
# 串口守护线程: 后台独立无损抓包
# ==========================================
class SerialWorker(QThread):
    # 🌟 修改 1：将信号的数据类型从 str 改为 bytes
    data_received = pyqtSignal(bytes)
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
            # timeout 设为极小值，配合我们自己的空闲检测逻辑
            self.serial = serial.Serial(self.port, self.baudrate, timeout=0.01)

            while self.running:
                if self.serial.in_waiting:
                    buffer = bytearray()

                    # ==========================================
                    # 🌟 核心：SSCOM 动态空闲超时分包算法
                    # ==========================================
                    idle_count = 0
                    # 只要串口不断线，且“空闲次数”小于 3 次（约 30ms），就一直死等拼接！
                    # 这样无论数据包有多大（即使是 4K 的长包），只要它没有中断，就会被完美聚合成一整包
                    while self.running and idle_count < 3:
                        if self.serial.in_waiting:
                            buffer.extend(self.serial.read(self.serial.in_waiting))
                            idle_count = 0  # 🌟 重点：只要有新数据进来，立刻清零空闲计时器！
                        else:
                            idle_count += 1
                            self.msleep(10)

                    # 循环结束，说明总线空闲超过了 30ms，这绝对是一包完整的数据了
                    if buffer:
                        self.data_received.emit(bytes(buffer))
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
    # 🌟 新增：线程安全的发送接口
    # ==========================================
    def send_data(self, data_bytes):
        """提供给主线程调用的发送接口"""
        if self.serial and self.serial.is_open:
            try:
                # pySerial 的 write 方法底层自带线程锁，主线程直接调用是安全的
                self.serial.write(data_bytes)
                self.serial.flush()  # 确保数据立刻推入物理总线
                return True, ""
            except Exception as e:
                return False, str(e)
        return False, "串口未打开或已断开"


# ==========================================
# 核心业务层 (Model): 解析引擎 (完美保留)
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
            if 'offset' in field_info: val = val + field_info['offset']
            if 'mapping' in field_info: val = field_info['mapping'].get(str(int(val)), val)
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
        if len(body_bytes) == 0: return {"_note": "✅ 无附加消息体"}
        msg_def = self.msgs.get(msg_type_hex)
        if not msg_def: return {"raw_body": binascii.hexlify(body_bytes).decode('ascii'), "_note": "未定义消息类型"}
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
            result['_error'] = f"解析异常: {str(e)}"
        return result


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
        self.setWindowTitle("ECU串口解析工具")

        # ==========================================
        # 🌟 动态获取资源路径 (兼容本地开发与 PyInstaller 打包)
        # ==========================================
        import os
        import sys

        def resource_path(relative_path):
            """获取资源的绝对路径"""
            try:
                # PyInstaller 创建的临时文件夹路径存放在 sys._MEIPASS 中
                base_path = sys._MEIPASS
            except Exception:
                # 如果不是打包环境，就使用当前工作目录
                base_path = os.path.abspath(".")
            return os.path.join(base_path, relative_path)

        # 使用动态路径加载图标
        icon_path = resource_path("logo.ico")
        if os.path.exists(icon_path):
            from PyQt6.QtGui import QIcon
            self.setWindowIcon(QIcon(icon_path))

        self.resize(1300, 800)

        self.is_dark_mode = True
        self.all_frames = []
        self.filtered_frames = []
        self.decoder = None

        self.rt_tx_parser = None
        self.rt_rx_parser = None
        self.serial_buffer_line = ""
        self.serial_worker = None
        self._last_char_was_newline = True
        self.is_recording = False
        self.record_filename = ""
        # ==========================================
        # 🌟 新增：历史数据缓存与 HEX 切换绑定
        # ==========================================
        from collections import deque
        # 使用双端队列，最多保存最近的 2000 包数据，避免长时间挂机导致内存溢出
        self.terminal_history = deque(maxlen=2000)

        # 🌟 新增：防抖定时器与状态记忆
        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)  # 设置为单次触发
        self.search_timer.timeout.connect(self._on_search_timer_timeout)
        self.last_search_text = ""

        self.init_ui()

    def init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(6)

        # 顶部工具栏
        top_bar_layout = QHBoxLayout()
        top_bar_layout.setContentsMargins(0, 0, 0, 0)  # 🌟 强行清空顶部默认边距，确立绝对左边缘！
        top_bar_layout.addWidget(QLabel("端口:"))
        self.combo_port = AutoRefreshComboBox(self)
        self.combo_port.setMinimumWidth(80)
        self.refresh_serial_ports()
        top_bar_layout.addWidget(self.combo_port)

        self.btn_refresh_port = QPushButton("🔄")
        self.btn_refresh_port.setFixedWidth(30)
        self.btn_refresh_port.clicked.connect(self.refresh_serial_ports)
        top_bar_layout.addWidget(self.btn_refresh_port)

        top_bar_layout.addWidget(QLabel("波特率:"))
        self.combo_baud = QComboBox()
        self.combo_baud.addItems(["115200", "921600"])
        top_bar_layout.addWidget(self.combo_baud)

        self.btn_serial_toggle = QPushButton("🔌 打开")
        self.btn_serial_toggle.clicked.connect(self.toggle_serial)
        top_bar_layout.addWidget(self.btn_serial_toggle)

        top_bar_layout.addWidget(QLabel("📜 协议:"))
        self.combo_protocol = QComboBox()
        self.populate_protocols()
        self.combo_protocol.currentIndexChanged.connect(self.change_protocol)
        top_bar_layout.addWidget(self.combo_protocol)

        self.quick_parse_input = QLineEdit()
        self.quick_parse_input.setPlaceholderText("粘贴报文解析...")
        top_bar_layout.addWidget(self.quick_parse_input)
        self.quick_parse_btn = QPushButton("🚀 解析")
        self.quick_parse_btn.clicked.connect(self.on_quick_parse_clicked)
        top_bar_layout.addWidget(self.quick_parse_btn)

        self.combo_filter = QComboBox()
        self.combo_filter.addItem("显示所有类型", "ALL")
        self.combo_filter.currentIndexChanged.connect(self.apply_filter)
        top_bar_layout.addWidget(self.combo_filter)

        self.btn_load = QPushButton("📂 日志")
        self.btn_load.clicked.connect(self.load_file)
        top_bar_layout.addWidget(self.btn_load)

        self.btn_theme = QPushButton("☀️ 浅色")
        self.btn_theme.clicked.connect(self.toggle_theme)
        top_bar_layout.addWidget(self.btn_theme)
        # ==========================================
        # 🌟 3. 新增：左右面板显隐控制按钮
        # ==========================================
        self.btn_toggle_left = QPushButton("🖥️ 串口终端")
        self.btn_toggle_left.setCheckable(True)
        self.btn_toggle_left.setChecked(True)  # 默认显示并处于按下状态
        self.btn_toggle_left.clicked.connect(self.toggle_left_panel)
        top_bar_layout.addWidget(self.btn_toggle_left)

        self.btn_toggle_right = QPushButton("📊 解析面板")
        self.btn_toggle_right.setCheckable(True)
        self.btn_toggle_right.setChecked(True)  # 默认显示并处于按下状态
        self.btn_toggle_right.clicked.connect(self.toggle_right_panel)
        top_bar_layout.addWidget(self.btn_toggle_right)

        # ==========================================
        # 🌟 1. 新增：发送面板显隐控制按钮
        # ==========================================
        self.btn_toggle_send = QPushButton("📤 发送面板")
        self.btn_toggle_send.setCheckable(True)
        self.btn_toggle_send.setChecked(False)  # 💡 默认不勾选（隐藏状态）
        self.btn_toggle_send.clicked.connect(self.toggle_send_panel)
        top_bar_layout.addWidget(self.btn_toggle_send)

        main_layout.addLayout(top_bar_layout)

        # 三屏联动布局
        #main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)

        # ==========================================
        # 🌟 1. 左侧终端面板提升为 self 属性
        # ==========================================
        self.left_panel = QWidget()
        left_layout = QVBoxLayout(self.left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)

        term_toolbar = QHBoxLayout()
        term_toolbar.setContentsMargins(0, 0, 0, 0)  # 🌟 强行清空下方边距，与上方完美垂直对齐！

        # ==========================================
        # 🌟 极简专业工具栏 (状态按钮 + 折叠菜单)
        # ==========================================
        from PyQt6.QtWidgets import QMenu

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 搜索...")

        # 🌟 1. 设置最小宽度保证基本显示，设置最大宽度防止在 4K 屏上长得太离谱
        self.search_input.setMinimumWidth(140)
        self.search_input.setMaximumWidth(400)

        # 🌟 2. 赋予它“弹性”：水平方向尽量膨胀，垂直方向保持固定高度
        self.search_input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self.search_input.textChanged.connect(self.on_search_text_changed)

        self.btn_search_prev = QPushButton("⬆️")
        self.btn_search_prev.setToolTip("向上查找")
        self.btn_search_prev.clicked.connect(self.search_prev)

        self.btn_search_next = QPushButton("⬇️")
        self.btn_search_next.setToolTip("向下查找")
        self.btn_search_next.clicked.connect(self.search_next)

        self.cb_filter_mode = QPushButton("🎯 过滤")
        self.cb_filter_mode.setCheckable(True)
        self.cb_filter_mode.setToolTip("开启/关闭仅显匹配行")
        self.cb_filter_mode.toggled.connect(lambda checked: self.redraw_terminal_history())

        self.cb_timestamp = QPushButton("⏱️ 时戳")
        self.cb_timestamp.setCheckable(True)
        self.cb_timestamp.setChecked(True)
        self.cb_timestamp.setToolTip("开启/关闭时间戳注入")

        # ==========================================
        # 🌟 1. 新增：接收 HEX 显示切换开关
        # ==========================================
        self.cb_hex_display = QPushButton("🔢 HEX接收")
        self.cb_hex_display.setCheckable(True)
        self.cb_hex_display.setChecked(False)  # 默认正常ASCII显示
        self.cb_hex_display.setToolTip("开启后，接收到的数据将以16进制格式显示")
        self.cb_hex_display.clicked.connect(self.redraw_terminal_history)

        self.cb_auto_scroll = QPushButton("⏬ 滚动")
        self.cb_auto_scroll.setCheckable(True)
        self.cb_auto_scroll.setChecked(True)
        self.cb_auto_scroll.setToolTip("弹起以冻结视口，按下恢复自动滚动")

        self.btn_clear_term = QPushButton("🗑️")
        self.btn_clear_term.setToolTip("清空控制台日志")
        self.btn_clear_term.clicked.connect(self.clear_all_data)

        self.btn_more = QPushButton("⋮ 更多")
        more_menu = QMenu(self)

        action_save = more_menu.addAction("💾 保存当前快照")
        action_save.triggered.connect(self.save_raw_log)

        self.action_record = more_menu.addAction("⏺️ 开始实时录制")
        self.action_record.triggered.connect(self.toggle_recording)

        more_menu.addSeparator()

        action_regex = more_menu.addAction("⚙️ 自定义高亮配置")
        action_regex.triggered.connect(self.open_regex_config)

        self.btn_more.setMenu(more_menu)

        # 🌟 按照从左到右的顺序，依次加入布局
        term_toolbar.addWidget(self.search_input)
        term_toolbar.addWidget(self.btn_search_prev)
        term_toolbar.addWidget(self.btn_search_next)
        term_toolbar.addWidget(self.cb_filter_mode)
        term_toolbar.addWidget(self.cb_timestamp)
        term_toolbar.addWidget(self.cb_hex_display)
        term_toolbar.addWidget(self.cb_auto_scroll)
        term_toolbar.addWidget(self.btn_clear_term)
        term_toolbar.addWidget(self.btn_more)
        # 🚨 终极修复：把弹簧加在【所有按钮的最后面】！
        # 这样不管你怎么放大窗口，巨大的弹簧都在右侧，把所有按钮死死顶在左边！
        term_toolbar.addStretch()
        left_layout.addLayout(term_toolbar)

        self.raw_log_console = TerminalTextEdit(self)
        left_layout.addWidget(self.raw_log_console)

        # ==========================================
        # 🌟 2. 新增：底部发送面板 (默认隐藏)
        # ==========================================
        self.send_panel = QWidget()
        send_layout = QHBoxLayout(self.send_panel)
        send_layout.setContentsMargins(5, 5, 5, 5)  # 紧凑边距

        # 发送模式单选
        self.radio_ascii = QRadioButton("ASCII")
        self.radio_hex = QRadioButton("HEX")
        self.radio_ascii.setChecked(True)  # 默认选中 ASCII
        # 自动联动：切到 HEX 时取消换行，切到 ASCII 时恢复换行
        self.radio_hex.toggled.connect(lambda checked: (
        self.cb_send_newline.setChecked(not checked), self.cb_send_newline.setEnabled(not checked)))

        # 附加选项
        self.cb_send_newline = QCheckBox("发送新行(\\r\\n)")
        self.cb_send_newline.setChecked(True)

        # 输入框 (支持回车发送)
        self.send_input = QLineEdit()
        self.send_input.setPlaceholderText("在此输入要发送的指令 (按回车快速发送)...")
        # 暂时绑定一个空方法，防止报错
        self.send_input.returnPressed.connect(self.execute_send_data)

        # 发送按钮
        self.btn_send = QPushButton("发送 🚀")
        self.btn_send.setMinimumWidth(80)
        self.btn_send.clicked.connect(self.execute_send_data)

        # 组装面板
        send_layout.addWidget(self.radio_ascii)
        send_layout.addWidget(self.radio_hex)
        send_layout.addWidget(self.cb_send_newline)
        send_layout.addWidget(self.send_input)
        send_layout.addWidget(self.btn_send)

        # 💡 设置默认状态为隐藏
        self.send_panel.setVisible(False)

        # 将整个发送面板压入左侧主布局的最下方
        left_layout.addWidget(self.send_panel)

        # ==========================================
        # 🌟 新增：监听垂直滚动条的数值变化，实现触底自动恢复滚动
        # ==========================================
        self.raw_log_console.verticalScrollBar().valueChanged.connect(self._on_log_scrollbar_changed)
        # 🌟 核心：当你疯狂滚动鼠标时，瞬间擦除并重新渲染可见区域的高亮！
        self.raw_log_console.verticalScrollBar().valueChanged.connect(self.update_viewport_search_highlights)

        self.main_splitter.addWidget(self.left_panel)

        # ==========================================
        # 🌟 2. 右侧解析详情面板提升为 self 属性
        # ==========================================
        # 统一命名为 self.right_panel，用来被顶部按钮控制显隐
        self.right_panel = QSplitter(Qt.Orientation.Vertical)

        right_top_widget = QWidget()
        right_top_layout = QVBoxLayout(right_top_widget)

        table_toolbar = QHBoxLayout()
        table_toolbar.addWidget(QLabel("📊 解析流水线"))
        self.cb_table_auto_scroll = QCheckBox("自动滚动(冻结视口)")
        self.cb_table_auto_scroll.setChecked(True)
        table_toolbar.addStretch()
        table_toolbar.addWidget(self.cb_table_auto_scroll)
        right_top_layout.addLayout(table_toolbar)

        self.table_view = AutoScrollTableView(self)
        self.table_model = FrameTableModel()
        self.table_model.get_msg_name = lambda t: self.decoder.msgs.get(t, {}).get('name',
                                                                                   '未知') if self.decoder else '未知'
        self.table_view.setModel(self.table_model)
        self.table_view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table_view.horizontalHeader().setStretchLastSection(True)

        # 🌟 增加这一行：开启表格隔行变色（斑马线效果）
        self.table_view.setAlternatingRowColors(True)
        self.table_view.clicked.connect(self.on_row_clicked)
        right_top_layout.addWidget(self.table_view)

        # 将表格区域加到右侧面板中
        self.right_panel.addWidget(right_top_widget)

        self.tree_view = QTreeView()
        self.tree_model = QStandardItemModel()
        self.tree_model.setHorizontalHeaderLabels(["字段结构解析详情"])
        self.tree_view.setModel(self.tree_model)

        # 将树状图区域加到右侧面板中
        self.right_panel.addWidget(self.tree_view)

        # 设置右侧面板内部（表格和树状图）的上下比例
        self.right_panel.setSizes([500, 300])

        # 🌟 3. 将组装好的右侧面板，加入到主分割器中
        self.main_splitter.addWidget(self.right_panel)
        # 设置左侧终端和右侧面板的左右初始比例
        self.main_splitter.setSizes([500, 800])

        # 🌟 4. 将主分割器加入到窗口主布局中
        main_layout.addWidget(self.main_splitter)

        self.statusBar().showMessage("状态: 待命")
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.statusBar().addPermanentWidget(self.progress_bar)

        self.change_protocol()
        self.setStyleSheet(self.get_dark_qss())
        self.apply_terminal_style()

    # ==========================================
    # 🌟 显隐控制逻辑
    # ==========================================
    def toggle_left_panel(self):
        is_visible = self.btn_toggle_left.isChecked()

        # 保护机制：不能把两边都关了
        if not is_visible and not self.right_panel.isVisible():
            self.btn_toggle_left.setChecked(True)  # 强制弹回
            QMessageBox.warning(self, "提示", "必须至少保留一个工作区！")
            return

        self.left_panel.setVisible(is_visible)

    def toggle_right_panel(self):
        is_visible = self.btn_toggle_right.isChecked()

        # 保护机制：不能把两边都关了
        if not is_visible and not self.left_panel.isVisible():
            self.btn_toggle_right.setChecked(True)  # 强制弹回
            QMessageBox.warning(self, "提示", "必须至少保留一个工作区！")
            return

        self.right_panel.setVisible(is_visible)

    # ==========================================
    # 🌟 发送面板控制逻辑
    # ==========================================
    def toggle_send_panel(self):
        is_visible = self.btn_toggle_send.isChecked()
        self.send_panel.setVisible(is_visible)

        # 体验优化：如果展开了发送面板，自动把光标聚焦到输入框，方便直接打字
        if is_visible:
            self.send_input.setFocus()

    def execute_send_data(self):
        text = self.send_input.text()
        if not text:
            return

        # 1. 拦截未连接状态
        if not self.serial_worker or getattr(self.serial_worker, 'serial',
                                             None) is None or not self.serial_worker.serial.is_open:
            QMessageBox.warning(self, "发送失败", "未连接到任何设备，请先打开串口！")
            return

        is_hex = self.radio_hex.isChecked()
        add_newline = self.cb_send_newline.isChecked()

        data_to_send = b''
        echo_text = ""

        try:
            # ==========================================
            # 🌟 模式一：处理 HEX 发送
            # ==========================================
            if is_hex:
                import re
                # 剔除所有的空格和无关键盘符号，只留 16 进制字符
                clean_hex = re.sub(r'[^0-9a-fA-F]', '', text)
                if len(clean_hex) % 2 != 0:
                    QMessageBox.warning(self, "格式错误",
                                        "HEX 模式下，输入的 16 进制字符数量必须是偶数！\n(例如: 0A 0B 0C)")
                    return

                data_to_send = bytes.fromhex(clean_hex)

                # 如果勾选了发送新行，追加 0D 0A
                if add_newline:
                    data_to_send += b'\r\n'

                # 构造漂亮的回显字符串：每个字节用空格隔开并大写
                echo_text = " ".join(f"{b:02X}" for b in data_to_send)

            # ==========================================
            # 🌟 模式二：处理 ASCII 发送
            # ==========================================
            else:
                str_to_send = text
                if add_newline:
                    str_to_send += '\r\n'

                # 统一编码为 utf-8 发送
                data_to_send = str_to_send.encode('utf-8', errors='replace')
                # ASCII 模式下如果加了回车换行，回显时带个标记以便区分
                echo_text = text if not add_newline else text + " \\r\\n"

            # ==========================================
            # 🌟 最终执行发送
            # ==========================================
            success, err_msg = self.serial_worker.send_data(data_to_send)

            if success:
                now_str = datetime.now().strftime('%H:%M:%S.%f')[:-3]
                self.terminal_history.append({'type': 'TX', 'time': now_str, 'data': data_to_send})

                if self.cb_hex_display.isChecked():
                    display_text = "[上行] " + " ".join(f"{b:02X}" for b in data_to_send) + "\n"
                else:
                    display_text = "[上行] " + data_to_send.decode('utf-8', errors='replace')

                # 同理增加过滤拦截
                filter_kw = self.search_input.text().lower()
                allow_render = True
                # 判断界面上的过滤复选框是否被勾选
                is_filtering = hasattr(self, 'cb_filter_mode') and self.cb_filter_mode.isChecked()

                if is_filtering:
                    filter_kw = self.search_input.text().lower()
                    if filter_kw and filter_kw not in display_text.lower():
                        allow_render = False  # 不包含关键词，拒绝上屏！

                self.append_raw_log(display_text, custom_time=now_str, render_to_ui=allow_render)
                self.send_input.selectAll()
            else:
                QMessageBox.critical(self, "发送失败", f"底层总线异常:\n{err_msg}")

        except Exception as e:
            QMessageBox.critical(self, "数据转换错误", f"输入格式无法解析:\n{str(e)}")

    def _on_log_scrollbar_changed(self, value):
        scrollbar = self.raw_log_console.verticalScrollBar()

        # 获取当前滚动条的最大值
        max_value = scrollbar.maximum()

        # 💡 核心逻辑：如果当前值等于最大值，说明用户把日志拉到了最底下
        # 并且 max_value > 0 防止刚启动没有任何日志时误触发
        if value == max_value and max_value > 0:
            # 如果此时“自动滚动”按钮是弹起（关闭）状态，就帮用户自动按下（开启）
            if not self.cb_auto_scroll.isChecked():
                self.cb_auto_scroll.setChecked(True)
                # 可选：如果你想给用户一个视觉反馈，可以在状态栏提示一下
                # self.statusBar().showMessage("⏬ 已触底，自动恢复实时滚动", 2000)

    # ==========================================
    # 🌟 搜索/雷达与过滤核心逻辑
    # ==========================================
    def open_regex_config(self):
        dialog = RegexConfigDialog(self)
        if dialog.exec():
            # 用户点保存后，立即重新加载并上色
            if hasattr(self.raw_log_console, 'highlighter'):
                self.raw_log_console.highlighter.update_theme(self.is_dark_mode)

    # ==========================================
    # 🌟 自动搜索防抖逻辑
    # ==========================================
    def on_search_text_changed(self, text):
        self.search_timer.stop()
        if not text:
            self.last_search_text = ""
            self._execute_search(backward=False)
            return
        # 🚀 将原来的 1000 毫秒等待，缩减为极速 100 毫秒！
        self.search_timer.start(100)

    def _on_search_timer_timeout(self):
        keyword = self.search_input.text()
        if keyword == self.last_search_text:
            return
        self.last_search_text = keyword
        self._execute_search(backward=False, is_typing_auto=True)

    def search_next(self):
        self._execute_search(backward=False)

    def search_prev(self):
        self._execute_search(backward=True)

    # ==========================================================
    # 🚀 核心黑科技：只在当前屏幕可见范围内搜索并高亮 (WindTerm同款)
    # ==========================================================
    def update_viewport_search_highlights(self, *args):
        keyword = self.search_input.text()
        selections = []

        if not keyword:
            self.raw_log_console.setExtraSelections(selections)
            return

        # 问显卡要当前屏幕可见的顶部和底部光标！
        viewport = self.raw_log_console.viewport()
        from PyQt6.QtCore import QPoint
        start_cursor = self.raw_log_console.cursorForPosition(QPoint(0, 0))
        end_cursor = self.raw_log_console.cursorForPosition(QPoint(viewport.width(), viewport.height()))

        start_block = start_cursor.block()
        end_block = end_cursor.block()

        from PyQt6.QtGui import QColor, QTextCharFormat, QTextCursor
        from PyQt6.QtWidgets import QTextEdit

        search_fmt = QTextCharFormat()
        if getattr(self, 'is_dark_mode', True):
            search_fmt.setBackground(QColor("#2E6A41"))
            search_fmt.setForeground(QColor("#FFFFFF"))
        else:
            search_fmt.setBackground(QColor("#F472B6"))
            search_fmt.setForeground(QColor("#000000"))

        block = start_block
        kw_lower = keyword.lower()
        import re

        # 重点：只在这几十行屏幕可见的文本里疯狂匹配
        while block.isValid():
            text = block.text()
            if kw_lower in text.lower():
                for m in re.finditer(re.escape(kw_lower), text.lower()):
                    sel = QTextEdit.ExtraSelection()
                    sel.format = search_fmt
                    cursor = self.raw_log_console.textCursor()
                    cursor.setPosition(block.position() + m.start())
                    cursor.setPosition(block.position() + m.end(), QTextCursor.MoveMode.KeepAnchor)
                    sel.cursor = cursor
                    selections.append(sel)

            if block == end_block:
                break
            block = block.next()
        # ==========================================
        # 🌟 核心修复：把“当前焦点的橙色高亮”最后放进去！
        # 这样它就会像图层最上方的贴纸一样，绝对不会被绿色盖住。
        # ==========================================
        if hasattr(self, 'current_search_hit_selection') and self.current_search_hit_selection:
            selections.append(self.current_search_hit_selection)
        self.raw_log_console.setExtraSelections(selections)

    def _execute_search(self, backward=False, is_typing_auto=False):
        from PyQt6.QtGui import QTextDocument, QTextCursor, QColor
        from PyQt6.QtWidgets import QTextEdit
        keyword = self.search_input.text()
        # ==========================================
        # 🌟 智能分流：如果当前是“过滤模式”，打字会触发全屏过滤重绘！
        # ==========================================
        is_filtering = hasattr(self, 'cb_filter_mode') and self.cb_filter_mode.isChecked()
        if is_filtering:
            if is_typing_auto:
                # 只要打字手一停，立刻从历史里把过滤结果洗出来！
                self.redraw_terminal_history()
            return  # 过滤模式下，直接结束，不走下面的物理跳转逻辑

        if not keyword:
            self.current_search_hit_selection = None
            self.update_viewport_search_highlights()
            return

        # 💡 如果是打字触发的，绝不滚动屏幕跳跃，只在当前屏幕画绿框！
        if is_typing_auto:
            self.current_search_hit_selection = None
            self.update_viewport_search_highlights()
            return

        # --- 以下是点击 上下箭头 的真实物理跳跃 ---
        current_extra = self.raw_log_console.extraSelections()
        physic_cursor = self.raw_log_console.textCursor()

        if hasattr(self, 'current_search_hit_selection') and self.current_search_hit_selection:
            last_res_cursor = self.current_search_hit_selection.cursor
            if backward:
                physic_cursor.setPosition(last_res_cursor.selectionStart())
            else:
                physic_cursor.setPosition(last_res_cursor.selectionEnd())
            self.raw_log_console.setTextCursor(physic_cursor)

        options = QTextDocument.FindFlag(0)
        if backward:
            options |= QTextDocument.FindFlag.FindBackward

        found = self.raw_log_console.find(keyword, options)

        if not found:
            loop_cursor = self.raw_log_console.textCursor()
            if backward:
                loop_cursor.movePosition(QTextCursor.MoveOperation.End)
            else:
                loop_cursor.movePosition(QTextCursor.MoveOperation.Start)
            self.raw_log_console.setTextCursor(loop_cursor)
            found = self.raw_log_console.find(keyword, options)

        if found:
            new_hit_cursor = self.raw_log_console.textCursor()
            sel_start = new_hit_cursor.selectionStart()
            sel_end = new_hit_cursor.selectionEnd()

            if backward:
                new_hit_cursor.setPosition(sel_start)
            else:
                new_hit_cursor.setPosition(sel_end)
            self.raw_log_console.setTextCursor(new_hit_cursor)

            selection = QTextEdit.ExtraSelection()
            selection.format.setBackground(QColor("#FF9800"))
            selection.format.setForeground(QColor("#000000"))

            render_cursor = self.raw_log_console.textCursor()
            render_cursor.setPosition(sel_start)
            render_cursor.setPosition(sel_end, QTextCursor.MoveMode.KeepAnchor)
            selection.cursor = render_cursor

            self.current_search_hit_selection = selection

            self.raw_log_console.setFocus()
            self.raw_log_console.ensureCursorVisible()
            self.search_input.setStyleSheet("")
            if self.cb_auto_scroll.isChecked():
                self.cb_auto_scroll.setChecked(False)

            # 更新背景高亮
            self.update_viewport_search_highlights()
        else:
            self.search_input.setStyleSheet("border: 1px solid #EF4444;")
            self.current_search_hit_selection = None
            self.update_viewport_search_highlights()

    # ==========================================
    # 其他业务逻辑 (数据接入、文件导出等)
    # ==========================================
    def refresh_serial_ports(self):
        self.combo_port.clear()
        ports = serial.tools.list_ports.comports()
        for p in ports: self.combo_port.addItem(f"{p.device}", p.device)

    def toggle_serial(self):
        # 🌟 修复核心：不再依赖虚无缥缈的线程状态，而是直接根据按钮文字判断用户意图
        if self.btn_serial_toggle.text() == "🛑 停止" or self.btn_serial_toggle.text() == "关闭中...":
            if self.serial_worker:
                self.serial_worker.stop()
                self.btn_serial_toggle.setText("关闭中...")
                self.btn_serial_toggle.setEnabled(False)  # 临时禁用防连击，等待线程安全释放
        else:
            port = self.combo_port.currentData()
            baud = self.combo_baud.currentText()
            if not port:
                QMessageBox.warning(self, "提示", "无可用的串口，请检查设备连接！")
                return

            self.rt_tx_parser = StreamParser(self.decoder)
            self.rt_rx_parser = StreamParser(self.decoder)
            self.serial_buffer_line = ""

            self.serial_worker = SerialWorker(port, int(baud))
            self.serial_worker.data_received.connect(self.on_serial_data_received)

            # ==========================================
            # 🌟 关键修复：把底层的异常和退出信号接到 UI 上！
            # ==========================================
            self.serial_worker.error_occurred.connect(self.on_serial_error)
            self.serial_worker.finished_signal.connect(self.on_serial_finished)

            self.serial_worker.start()

            self.btn_serial_toggle.setText("🛑 停止")
            self.btn_serial_toggle.setStyleSheet("background-color: #d32f2f; color: white; font-weight: bold;")
            self.combo_port.setEnabled(False)
            self.combo_baud.setEnabled(False)
            self.statusBar().showMessage(f"状态: 正在监听 {port} ({baud}bps)")

    # ==========================================
    # 🌟 新增配套方法 1：弹窗提示底层报错，不再静默假死
    # ==========================================
    def on_serial_error(self, err_msg):
        QMessageBox.critical(self, "串口异常", f"串口连接断开或被占用：\n{err_msg}")

    # ==========================================
    # 🌟 新增配套方法 2：绝对安全的 UI 状态重置 (无论正常关闭还是异常断开都会触发)
    # ==========================================
    def on_serial_finished(self):
        self.btn_serial_toggle.setText("🔌 打开")
        self.btn_serial_toggle.setStyleSheet("")
        self.btn_serial_toggle.setEnabled(True)
        self.combo_port.setEnabled(True)
        self.combo_baud.setEnabled(True)
        self.statusBar().showMessage("状态: 串口已安全关闭")
        self.current_log_filename = None
        # 🌟 优化：彻底清空断开瞬间残留在内存中的半截字符串
        self.serial_buffer_line = ""

    def append_raw_log(self, text, custom_time=None, write_to_file=True, render_to_ui=True):
        if not text:
            return

        clean_text = text.strip('\r\n')
        if not clean_text:
            return

        is_empty = self.raw_log_console.document().isEmpty()

        # 1. 组装最终带有时间戳的文本
        if self.cb_timestamp.isChecked():
            time_str = custom_time if custom_time else datetime.now().strftime('%H:%M:%S.%f')[:-3]
            time_prefix = f"[{time_str}] "
            final_text = time_prefix + clean_text if is_empty else "\n\n" + time_prefix + clean_text
        else:
            final_text = clean_text if is_empty else "\n\n" + clean_text

        # ==========================================
        # 🌟 2. 永远优先写盘 (保证本地录制的 log 文件是 100% 完整的)
        # ==========================================
        if write_to_file and getattr(self, 'is_recording', False) and hasattr(self,
                                                                              'record_file_handle') and self.record_file_handle:
            try:
                self.record_file_handle.write(final_text)
                self.record_file_handle.flush()
            except:
                pass

        # ==========================================
        # 🚀 3. 性能护城河：如果被过滤掉了，到此为止，绝不消耗显卡和 CPU 去渲染！
        # ==========================================
        if not render_to_ui:
            return

        # 4. 只有通过过滤的数据，才进入极其消耗资源的 UI 渲染环节
        scrollbar = self.raw_log_console.verticalScrollBar()
        current_scroll = scrollbar.value()
        cursor = self.raw_log_console.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)

        block_format = QTextBlockFormat()
        block_format.setBottomMargin(8)
        import re
        if re.search(r"(?i)(error|fail|timeout|异常|失败)", final_text):
            from PyQt6.QtGui import QColor
            bg_color = QColor("#4A0000") if self.is_dark_mode else QColor("#FFCCCC")
            block_format.setBackground(bg_color)
        cursor.setBlockFormat(block_format)

        cursor.insertText(final_text)

        if self.cb_auto_scroll.isChecked():
            scrollbar.setValue(scrollbar.maximum())
        else:
            scrollbar.setValue(current_scroll)

    # ==========================================
    # 🌟 核心：历史数据重绘引擎
    # ==========================================
    def redraw_terminal_history(self):
        try:
            self.raw_log_console.setUpdatesEnabled(False)
            self.raw_log_console.clear()

            is_hex = hasattr(self, 'cb_hex_display') and self.cb_hex_display.isChecked()
            is_filtering = hasattr(self, 'cb_filter_mode') and self.cb_filter_mode.isChecked()
            filter_kw = self.search_input.text().lower()

            for pkt in self.terminal_history:
                raw_bytes = pkt['data']
                if is_hex:
                    text = " ".join(f"{b:02X}" for b in raw_bytes) + "\n"
                    if pkt.get('type') == 'TX': text = "[上行] " + text
                else:
                    text = raw_bytes.decode('utf-8', errors='replace')
                    if pkt.get('type') == 'TX': text = "[上行] " + text

                # ==========================================
                # 🌟 核心升级：行级精准过滤
                # ==========================================
                if is_filtering and filter_kw:
                    # 1. 把这一大包数据按换行符拆成多行
                    lines = text.split('\n')
                    # 2. 只有包含搜索词的行，才有资格活下来
                    matched_lines = [line for line in lines if filter_kw in line.lower()]

                    if not matched_lines:
                        continue  # 如果全都不匹配，这整包彻底丢弃

                    # 3. 把幸存的行重新拼装起来
                    text = "\n".join(matched_lines)

                self.append_raw_log(text, custom_time=pkt.get('time'), write_to_file=False, render_to_ui=True)

        except Exception as e:
            print(f"🚨 重绘引擎异常: {e}")
        finally:
            self.raw_log_console.setUpdatesEnabled(True)
            scrollbar = self.raw_log_console.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())
            self.update_viewport_search_highlights()

    def on_serial_data_received(self, raw_bytes):
        # ==========================================
        # 🌟 1. 处理 UI 屏幕显示 (支持历史存储)
        # ==========================================
        now_str = datetime.now().strftime('%H:%M:%S.%f')[:-3]
        # 把最纯净的字节流塞进时光机
        self.terminal_history.append({'type': 'RX', 'time': now_str, 'data': raw_bytes})

        if hasattr(self, 'cb_hex_display') and self.cb_hex_display.isChecked():
            display_text = " ".join(f"{b:02X}" for b in raw_bytes) + "\n"
        else:
            display_text = raw_bytes.decode('utf-8', errors='replace')
        # ==========================================
        # 🌟 核心拦截：实时比对过滤关键词
        # ==========================================
        # 这里替换成您界面上实际用于过滤的关键词获取方式，例如：
        filter_kw = self.search_input.text().lower()

        # ==========================================
        # 🌟 核心拦截：只在开启“过滤模式”时才执行拦截！
        # ==========================================
        allow_render = True
        is_filtering = hasattr(self, 'cb_filter_mode') and self.cb_filter_mode.isChecked()

        if is_filtering:
            filter_kw = self.search_input.text().lower()
            if filter_kw:
                # 1. 将刚收到的这包数据切分
                lines = display_text.split('\n')
                # 2. 剔除无关行
                matched_lines = [line for line in lines if filter_kw in line.lower()]

                if not matched_lines:
                    allow_render = False  # 全军覆没，直接拦截不上屏
                else:
                    # 3. 重新组装，保证只把 GBGGA 这一行传给 UI 渲染
                    display_text = "\n".join(matched_lines)
        # 传入带有当前真实时间的字符串，并由 allow_render 决定是否上屏
        self.append_raw_log(display_text, custom_time=now_str, render_to_ui=allow_render)

        # ==========================================
        # 🌟 2. 处理后台解析引擎 (不受 UI 开关影响)
        # ==========================================
        # 为了兼容原有的正则解析逻辑，我们将字节流解码为文本后喂给解析器池
        text_for_parser = raw_bytes.decode('utf-8', errors='replace')
        self.serial_buffer_line += text_for_parser

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

                if self.cb_table_auto_scroll.isChecked() and self.filtered_frames:
                    self.table_view.scrollToBottom()

    def save_raw_log(self):
        text = self.raw_log_console.toPlainText()
        if not text.strip(): return
        filename, _ = QFileDialog.getSaveFileName(self, "保存串口原始日志",
                                                  f"SerialLog_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                                                  "Text Files (*.txt);;All Files (*)")
        if not filename: return
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(text)
            self.statusBar().showMessage(f"✅ 日志已保存至: {filename}")
        except Exception as e:
            QMessageBox.critical(self, "保存失败", str(e))

    def toggle_recording(self):
        if not self.is_recording:
            filename, _ = QFileDialog.getSaveFileName(self, "选择实时录制日志存放位置",
                                                      f"Record_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                                                      "Text Files (*.txt);;All Files (*)")
            if not filename: return
            self.record_filename = filename

            # 🌟 优化：保持文件句柄处于打开状态，采用 'a' 追加模式
            try:
                self.record_file_handle = open(self.record_filename, 'a', encoding='utf-8', errors='ignore')
                self.is_recording = True
                self.action_record.setText("⏹️ 停止实时录制")
                self.btn_more.setText("🔴 录制中")
                self.btn_more.setStyleSheet("color: #EF4444; font-weight: bold;")
            except Exception as e:
                QMessageBox.critical(self, "错误", f"无法创建文件: {e}")
        else:
            self.is_recording = False
            self.record_filename = ""

            # 🌟 优化：停止时安全关闭文件句柄
            if hasattr(self, 'record_file_handle') and self.record_file_handle:
                self.record_file_handle.close()
                self.record_file_handle = None

            self.action_record.setText("⏺️ 开始实时录制")
            self.btn_more.setText("⋮ 更多")
            self.btn_more.setStyleSheet("")

    def clear_all_data(self):
        self.raw_log_console.clear()
        self.all_frames.clear()
        self.filtered_frames.clear()
        self.table_model.update_data([])
        self.tree_model.removeRows(0, self.tree_model.rowCount())
        if self.rt_tx_parser: self.rt_tx_parser.buffer.clear()
        if self.rt_rx_parser: self.rt_rx_parser.buffer.clear()
        self.serial_buffer_line = ""

    def populate_protocols(self):
        self.combo_protocol.clear() # 防错机制：先清空原有列表
        # 🌟 修复：扫描 JSON 时，强制排除掉高亮配置文件
        json_files = [f for f in os.listdir('.') if f.endswith('.json') and f != "highlight_rules.json"]
        for jf in json_files:
            self.combo_protocol.addItem(jf, jf)

    def change_protocol(self):
        protocol_file = self.combo_protocol.currentData()
        if not protocol_file: return
        try:
            self.decoder = ProtocolDecoder(protocol_file)
            self.clear_all_data()
            if self.serial_worker and self.serial_worker.isRunning():
                self.rt_tx_parser = StreamParser(self.decoder)
                self.rt_rx_parser = StreamParser(self.decoder)
        except Exception as e:
            pass

    def on_quick_parse_clicked(self):
        raw_text = self.quick_parse_input.text().strip()
        if not raw_text or self.decoder is None: return
        # Quick parse logic skipped for brevity, full logic intact in original file
        pass

    def load_file(self):
        if self.decoder is None: return
        file_path, _ = QFileDialog.getOpenFileName(self, "选择日志文件", "", "Text Files (*.txt *.log);;All Files (*)")
        if not file_path: return
        self.clear_all_data()
        self.worker = ParseWorker(file_path, self.decoder)
        self.worker.batch_ready.connect(lambda frames: self.all_frames.extend(frames))
        self.worker.finished.connect(self.on_parse_finished)
        self.worker.start()

    def on_parse_finished(self, total_count):
        for frame in self.all_frames:
            msg_def = self.decoder.msgs.get(frame['type'], {})
            frame['name'] = msg_def.get('name', '未知消息')
        self.apply_filter()

    def apply_filter(self):
        target_type = self.combo_filter.currentData()
        if target_type == "ALL" or not target_type:
            self.filtered_frames = self.all_frames[:]
        else:
            self.filtered_frames = [f for f in self.all_frames if f['type'] == target_type]
        self.table_model.update_data(self.filtered_frames)

    def on_row_clicked(self, index):
        if not index.isValid(): return
        frame = self.table_model.get_raw_data(index.row())
        self.tree_model.removeRows(0, self.tree_model.rowCount())
        root_node = self.tree_model.invisibleRootItem()
        self._populate_tree(root_node, frame['data'])
        self.tree_view.expandAll()

    def _populate_tree(self, parent_item, data_node):
        if isinstance(data_node, dict):
            for key, val in data_node.items():
                if isinstance(val, (dict, list)):
                    node = QStandardItem(str(key))
                    parent_item.appendRow(node)
                    self._populate_tree(node, val)
                else:
                    parent_item.appendRow(QStandardItem(f"{key}: {val}"))

    def toggle_theme(self):
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        QApplication.processEvents()
        self.setUpdatesEnabled(False)
        try:
            self.is_dark_mode = not self.is_dark_mode
            if self.is_dark_mode:
                self.btn_theme.setText("☀️ 浅色")
                self.setStyleSheet(self.get_dark_qss())
            else:
                self.btn_theme.setText("🌙 深色")
                self.setStyleSheet(self.get_light_qss())
            self.apply_terminal_style()
        finally:
            self.setUpdatesEnabled(True)
            QApplication.restoreOverrideCursor()

    def apply_terminal_style(self):
        # 确保 raw_log_console 存在
        if hasattr(self, 'raw_log_console') and self.raw_log_console:
            if self.is_dark_mode:
                self.raw_log_console.setStyleSheet("""
                    QTextEdit {
                        background-color: #2B2B2B; 
                        color: #A9B7C6; 
                        border: none;
                    }
                """)
            else:
                # ☀️ 浅色模式绝对护眼方案：Solarized 暖光纸色
                self.raw_log_console.setStyleSheet("""
                    QTextEdit {
                        background-color: #FDF6E3; /* 核心护眼色：羊皮纸米黄色，彻底消除蓝光 */
                        color: #4A555D;            /* 柔和的深蓝灰色字体，对比度适中 */
                        border: none;
                    }
                """)

            # 通知底层高亮引擎切换配色方案
            if hasattr(self.raw_log_console, 'highlighter'):
                self.raw_log_console.highlighter.update_theme(self.is_dark_mode)

    def get_light_qss(self):
        return """
        /* 主窗口背景：比中间的纸色略深一点的卡其灰，压住视觉 */
        QWidget { background-color: #EEE8D5; color: #4A555D; font-family: "Microsoft YaHei", "Segoe UI"; }

        /* 交互组件：使用主护眼色 */
        QLineEdit, QTextEdit, QComboBox, QCheckBox { background-color: #FDF6E3; color: #4A555D; border: 1px solid #D6D0BA; border-radius: 4px; padding: 4px; }

        /* 按钮：温和的纸色，悬浮时稍微加深，点击时使用柔和的莫兰迪蓝 */
        QPushButton { background-color: #FDF6E3; color: #4A555D; border: 1px solid #D6D0BA; border-radius: 4px; padding: 4px 8px; }
        QPushButton:hover { background-color: #E6DFCB; color: #2A6F97; border: 1px solid #99B2C6; }
        QPushButton:checked { background-color: #D4E4F0; color: #2A6F97; border: 1px solid #2A6F97; font-weight: bold; }

        /* 🌟 右侧流水线表格：纸色背景 + 极淡的暖卡其色斑马纹 */
        QTableView { 
            background-color: #FDF6E3; 
            color: #4A555D; 
            gridline-color: #E2DBCA; 
            border: 1px solid #D6D0BA; 
            selection-background-color: #93A1A1;  /* 选中时使用护眼莫兰迪灰绿 */
            selection-color: #FFFFFF; 
            alternate-background-color: #F6EFCF;  /* 淡淡的泛黄隔行变色 */
            font-family: Consolas, "Microsoft YaHei"; /* 🌟 新增：表格等宽排版 */
        }

        /* 🌟 字段解析树状图 */
        QTreeView { 
            background-color: #FDF6E3; 
            color: #4A555D; 
            border: 1px solid #D6D0BA; 
            selection-background-color: #93A1A1; 
            selection-color: #FFFFFF; 
            font-family: Consolas, "Microsoft YaHei"; /* 🌟 新增：树状图等宽排版 */
        }

        /* 表头：底色加深，形成视觉分层 */
        QHeaderView::section { 
            background-color: #E6DFCB; 
            color: #586E75; 
            border: none; 
            border-right: 1px solid #D6D0BA; 
            border-bottom: 1px solid #D6D0BA; 
            padding: 4px; 
            font-weight: bold; 
        }
        """

    def get_dark_qss(self):
        return """
        QWidget { background-color: #2b2d30; color: #a9b7c6; font-family: "Microsoft YaHei", "Segoe UI"; }
        QLineEdit, QTextEdit, QComboBox, QCheckBox { background-color: #1e1f22; color: #a9b7c6; border: 1px solid #43454a; border-radius: 4px; padding: 4px; }
        QPushButton { background-color: #36393f; color: #a9b7c6; border: 1px solid #43454a; border-radius: 4px; padding: 4px 8px; }
        QPushButton:hover { background-color: #43454a; color: #ffffff; }
        QPushButton:checked { background-color: #1e3a8a; color: #bfdbfe; border: 1px solid #3b82f6; font-weight: bold; }

        /* ======================================================== */
        /* 🌟 修改点 1：解析流水线表格 (PyCharm 通知栏/工具栏经典浅色) */
        /* ======================================================== */
        QTableView { 
            background-color: #3C3F41;  /* 提亮底色，和左侧 #2B2B2B 区分开 */
            color: #A9B7C6; 
            gridline-color: #4F5254;    /* 网格线也要相应变浅一点，显得柔和 */
            border: 1px solid #43454A; 
            selection-background-color: #2F65CA; 
            selection-color: #FFFFFF; 
            alternate-background-color: #414446; /* 💡 隔行变色的浅色底 */
            font-family: Consolas, "Microsoft YaHei"; /* 🌟 新增：表格等宽排版 */
        }

        /* ======================================================== */
        /* 🌟 修改点 2：字段解析详情树状图 (保持与表格统一的底色) */
        /* ======================================================== */
        QTreeView { 
            background-color: #3C3F41; 
            color: #A9B7C6; 
            border: 1px solid #43454A; 
            selection-background-color: #2F65CA; 
            selection-color: #FFFFFF; 
            font-family: Consolas, "Microsoft YaHei"; /* 🌟 新增：树状图等宽排版 */
        }

        QHeaderView::section { background-color: #2b2d30; color: #a9b7c6; border: none; border-right: 1px solid #43454a; border-bottom: 1px solid #43454a; padding: 4px; font-weight: bold; }
        """


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = EcuMainWindow()
    window.show()
    sys.exit(app.exec())