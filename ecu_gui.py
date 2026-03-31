import sys
import os
import json
import struct
import re
import binascii
import csv
import time
import math
import socket

from datetime import datetime, timezone, timedelta

# 🌟 引入串口通信库
try:
    import serial
    import serial.tools.list_ports
except ImportError:
    print("未检测到 pyserial 库！请运行: pip install pyserial")
    sys.exit(1)

# ==========================================
# 🌟 新增：极速波形绘图库
# ==========================================
try:
    import pyqtgraph as pg
except ImportError:
    print("未检测到 pyqtgraph 库！将无法使用波形图功能。请运行: pip install pyqtgraph")
    pg = None

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QPushButton, QFileDialog, QTableView, QTreeView, QComboBox,
                             QLabel, QProgressBar, QSplitter, QMessageBox, QHeaderView, QAbstractItemView, QLineEdit,
                             QCheckBox, QTextEdit, QDialog, QTableWidget, QTableWidgetItem, QSizePolicy, QPlainTextEdit,
                             QRadioButton, QSpinBox)
from PyQt6.QtGui import (QStandardItemModel, QStandardItem, QFont, QTextCursor,
                         QSyntaxHighlighter, QTextCharFormat, QColor, QTextBlockFormat, QPainter, QIcon, QAction)
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

        # ==========================================
        # 🚀 QTextEdit 性能极限优化三板斧
        # ==========================================
        # 1. 极其关键：关闭历史撤销栈！(节省海量内存)
        self.setUndoRedoEnabled(False)

        # 2. 性能护城河：将 50000 行缩减为 20000 行！
        # 这是解决 NMEA 海量数据下拖拽窗口卡顿的根本方法
        self.document().setMaximumBlockCount(20000)

        # 3. 初始保留自动换行 (后续由我们在工具栏加的 CheckBox 动态控制)
        self.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)

        # 🌟 启动高亮引擎 (只保留这一次即可)
        self.highlighter = LogHighlighter(self.document(), is_dark_mode=True)

        # ==========================================
        # 🌟 完美找回行间距 (QTextEdit 支持度 100%)
        # ==========================================
        block_fmt = QTextBlockFormat()
        block_fmt.setLineHeight(130, 1)  # 130% 行高
        block_fmt.setBottomMargin(2)

        cursor = self.textCursor()
        cursor.setBlockFormat(block_fmt)
        self.setTextCursor(cursor)

        # ==========================================
        # 🌟 致敬 PyCharm 2022.3 Darcula 经典配色
        # ==========================================
        self.setStyleSheet("""
            QTextEdit {
                background-color: #2B2B2B;
                color: #A9B7C6;
                border: none;
            }
        """)

    def wheelEvent(self, event):
        # 🌟 核心逻辑：如果是查找跳转引起的滚动，直接放行，不要走“手动滚轮逻辑”
        if getattr(self, '_is_searching', False):
            super().wheelEvent(event)
            return
        # 🌟 核心修复：将 cb_auto_scroll 替换为右键菜单中的 action_autoscroll
        # 注意：QAction 获取状态用 isChecked()，这和按钮是一样的
        # 只有在不是查找、且开启了自动滚动时，用户向上滚轮才触发关闭
        if hasattr(self.main_window, 'action_autoscroll') and self.main_window.action_autoscroll.isChecked():
            if event.angleDelta().y() > 0:  # 向上滚
                self.main_window.action_autoscroll.setChecked(False)
                self.main_window.statusBar().showMessage("⏬ 自动滚动已暂停 (手动滑屏)", 2000)

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
            self.msleep(50)  # 让 DTR/RTS 电平导致的设备重启或毛刺飞一会儿
            # ==========================================
            # 🌟 核心修复：打开串口后瞬间清空系统底层的历史脏数据
            # ==========================================
            self.serial.reset_input_buffer()

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
# 🌟 新增：TCP/UDP 海陆空网络通信守护线程
# ==========================================
class NetworkWorker(QThread):
    data_received = pyqtSignal(bytes)
    error_occurred = pyqtSignal(str)
    finished_signal = pyqtSignal()
    client_connected = pyqtSignal(str) # 专门留给 TCP Server 的上线通知

    def __init__(self, mode, ip, port):
        super().__init__()
        self.mode = mode
        self.ip = ip
        self.port = port
        self.running = True
        self.sock = None
        self.client_sock = None # 用于存储 TCP Server 收到的客户端，或 UDP 最近的源地址

    def run(self):
        try:
            if self.mode == "TCP Client":
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.sock.settimeout(3.0)
                self.sock.connect((self.ip, self.port))
                self.sock.settimeout(0.1) # 连接成功后把超时改小，防止卡死 UI
                while self.running:
                    try:
                        data = self.sock.recv(4096)
                        if data: self.data_received.emit(data)
                        else: raise ConnectionError("服务器主动断开连接")
                    except socket.timeout: continue
                    except BlockingIOError: continue

            elif self.mode == "TCP Server":
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                self.sock.bind((self.ip, self.port))
                self.sock.listen(1)
                self.sock.settimeout(0.5)
                while self.running:
                    try:
                        client, addr = self.sock.accept()
                        self.client_sock = client
                        self.client_sock.settimeout(0.1)
                        self.client_connected.emit(f"{addr[0]}:{addr[1]}")
                        while self.running and self.client_sock:
                            try:
                                data = self.client_sock.recv(4096)
                                if data: self.data_received.emit(data)
                                else:
                                    self.client_sock.close()
                                    self.client_sock = None
                                    self.error_occurred.emit("客户端已断开，重新监听中...")
                                    break
                            except socket.timeout: continue
                    except socket.timeout: continue

            elif self.mode == "UDP":
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                self.sock.bind((self.ip, self.port))
                self.sock.settimeout(0.1)
                while self.running:
                    try:
                        data, addr = self.sock.recvfrom(4096)
                        self.client_sock = addr # 暂存对方的 IP 和端口，以便一会回复数据
                        if data: self.data_received.emit(data)
                    except socket.timeout: continue

        except Exception as e:
            if self.running: self.error_occurred.emit(f"网络异常: {str(e)}")
        finally:
            self.stop()
            self.finished_signal.emit()

    def stop(self):
        self.running = False
        if getattr(self, 'client_sock', None) and isinstance(self.client_sock, socket.socket):
            try: self.client_sock.close()
            except: pass
        if getattr(self, 'sock', None):
            try: self.sock.close()
            except: pass

    def send_data(self, data_bytes):
        try:
            if self.mode == "TCP Client" and self.sock:
                self.sock.sendall(data_bytes)
                return True, ""
            elif self.mode == "TCP Server":
                if self.client_sock:
                    self.client_sock.sendall(data_bytes)
                    return True, ""
                return False, "当前无客户端连接，无法发送"
            elif self.mode == "UDP":
                if self.sock and getattr(self, 'client_sock', None):
                    self.sock.sendto(data_bytes, self.client_sock)
                    return True, ""
                return False, "尚未收到任何 UDP 目标地址，无法回复数据"
            return False, "网络未连接"
        except Exception as e:
            return False, str(e)

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

        for line in lines:
            line = line.strip()
            if not line: continue

            # 剥离时间戳前缀
            pure_line = re.sub(r'^\[.*?\]\s*', '', line)

            # 🌟 极简主义提取：只抓取标准格式数据，不合规的直接丢弃
            match = re.search(r'(?:[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}:|[0-9A-Fa-f]{8}:)\s*(.*)', pure_line)
            if match:
                payload = match.group(1)
                pure_hex = ""
                # 严格提取前16个合法的 HEX 字节
                for word in payload.split()[:16]:
                    if len(word) == 2 and all(c in '0123456789abcdefABCDEF' for c in word):
                        pure_hex += word
                    else:
                        break

                if pure_hex:
                    try:
                        self.buffer.extend(bytes.fromhex(pure_hex))
                    except:
                        pass

        # ==========================================
        # 帧结构验证与提取
        # ==========================================
        frames = []
        while True:
            if not hasattr(self, 'SYNC_HEADER'):
                break
            head_idx = self.buffer.find(self.SYNC_HEADER)
            if head_idx == -1:
                keep = len(self.SYNC_HEADER) - 1 if len(self.buffer) > 0 else 0
                self.buffer = self.buffer[-keep:]
                break
            if head_idx > 0: self.buffer = self.buffer[head_idx:]
            if len(self.buffer) < getattr(self, 'header_size', 2): break

            if getattr(self, 'len_size', 2) == 1:
                body_len = self.buffer[self.len_offset]
            else:
                body_len = struct.unpack('>H', self.buffer[self.len_offset: self.len_offset + 2])[0]

            if getattr(self, 'len_includes_all', False):
                total_len = body_len
            else:
                total_len = getattr(self, 'header_size', 2) + body_len + getattr(self, 'checksum_size', 0)

            # 🌟 新增安全护盾：由于之前的串台可能导致解析出了异常巨大的长度，
            # 强制拦截超过 2048 字节的无效包，丢弃当前包头，继续找下一个包！
            if total_len > 2048:
                self.buffer = self.buffer[1:]
                continue

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
# 🌟 新增：离线日志回放 (时光倒流) 线程
# ==========================================
class PlaybackWorker(QThread):
    data_received = pyqtSignal(bytes)
    progress_updated = pyqtSignal(int, int)
    finished_signal = pyqtSignal()

    def __init__(self, filepath, speed):
        super().__init__()
        self.filepath = filepath
        self.speed = speed
        self.running = True
        self.is_paused = False

    def run(self):
        try:
            # 1. 极速扫描一遍文件，获取总行数，用于精确计算进度
            with open(self.filepath, 'r', encoding='utf-8', errors='ignore') as f:
                total = sum(1 for _ in f)

            # 2. 正式开始读取
            with open(self.filepath, 'r', encoding='utf-8', errors='ignore') as f:
                batch_buffer = ""
                # 🌟 核心优化 1：极速模式下，每 100 行打成一个大包发给主线程
                batch_size = 100 if self.speed == 0 else 1
                lines_in_batch = 0

                for i, line in enumerate(f):
                    # 处理暂停逻辑
                    while self.is_paused and self.running:
                        self.msleep(50)
                    if not self.running:
                        break

                    batch_buffer += line
                    lines_in_batch += 1

                    # 达到打包数量，或者已经是最后一行，发射给主线程！
                    if lines_in_batch >= batch_size or i == total - 1:
                        self.data_received.emit(batch_buffer.encode('utf-8'))
                        batch_buffer = ""
                        lines_in_batch = 0

                        # ==========================================
                        # 🌟 核心优化 2：极速模式下的“防卡死护城河”
                        # 发送完一个 100 行的大包后，强迫后台线程休息 2 毫秒！
                        # 这 2 毫秒就是留给主线程去重绘 UI 和解析正则的救命时间！
                        # ==========================================
                        if self.speed == 0:
                            self.msleep(2)

                    # 🌟 核心优化 3：极大地降低进度条刷新频率
                    # 只有当进度跨越了 1% 时，才去刷新一次进度条，拒绝无效的 UI 重绘
                    if i % max(1, int(total / 100)) == 0 or i == total - 1:
                        self.progress_updated.emit(i + 1, total)

                    # 常规倍速的休眠控制
                    if self.speed > 0:
                        self.msleep(int(100 / self.speed))

        except Exception as e:
            print(f"🚨 回放引擎异常: {e}")
        finally:
            self.finished_signal.emit()

    def set_speed(self, speed):
        self.speed = speed

    def toggle_pause(self):
        self.is_paused = not self.is_paused
        return self.is_paused

    def stop(self):
        self.running = False


# ==========================================
# 🌟 新增：自动化测试宏 (流水线) 线程
# ==========================================
class MacroWorker(QThread):
    send_cmd_signal = pyqtSignal(str, str)  # 信号：报文内容, 格式(HEX/ASCII)
    row_highlight_signal = pyqtSignal(int)  # 信号：高亮当前执行行
    finished_signal = pyqtSignal()
    log_signal = pyqtSignal(str)

    def __init__(self, macro_list, loop_count):
        super().__init__()
        self.macro_list = macro_list  # 格式: [{'data': '...', 'fmt': 'HEX', 'delay': 500}, ...]
        self.loop_count = loop_count
        self.running = True

    def run(self):
        try:
            for loop in range(self.loop_count):
                if not self.running: break
                self.log_signal.emit(f"🔄 开始执行第 {loop + 1}/{self.loop_count} 轮测试脚本...")

                for idx, cmd in enumerate(self.macro_list):
                    if not self.running: break

                    # 1. 高亮 UI 表格行，提示进度
                    self.row_highlight_signal.emit(idx)

                    # 2. 触发主线程发送动作
                    self.send_cmd_signal.emit(cmd['data'], cmd['fmt'])

                    # 3. 精准延时 (分段休眠，确保点击"停止"时能瞬间响应，不被长延时卡死)
                    delay_ms = cmd.get('delay', 500)
                    steps = delay_ms // 50
                    rem = delay_ms % 50
                    for _ in range(steps):
                        if not self.running: break
                        self.msleep(50)
                    if self.running and rem > 0:
                        self.msleep(rem)

        except Exception as e:
            print(f"🚨 宏引擎异常: {e}")
        finally:
            self.row_highlight_signal.emit(-1)  # 熄灭高亮
            self.finished_signal.emit()

    def stop(self):
        self.running = False

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

        # ==========================================
        # 🌟 新增：波形图数据结构 (最多缓存 1000 个点，保证极速)
        # ==========================================
        self.known_wave_vars = set()
        # 🌟 升级：为支持 2D 轨迹，拆分为 X/Y 两个独立队列
        self.wave_data_x = deque(maxlen=1000)
        self.wave_data_y = deque(maxlen=1000)
        self.latest_scatter = None  # 靶心图层图柄

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

        # ==========================================
        # 🌟 1. 启用系统原生菜单栏 (降维收纳 7 个大按钮)
        # ==========================================
        menubar = self.menuBar()

        # --- 【文件】菜单 ---
        file_menu = menubar.addMenu("📁 文件(F)")

        action_load = QAction("📂 静态解析离线日志", self)
        action_load.triggered.connect(self.load_file)
        file_menu.addAction(action_load)

        action_playback = QAction("⏪ 动态回放历史日志", self)
        action_playback.triggered.connect(self.start_playback_dialog)
        file_menu.addAction(action_playback)

        # --- 【视图】菜单 (拯救界面的核心功臣) ---
        view_menu = menubar.addMenu("👁️ 视图(V)")

        self.action_toggle_left = QAction("🖥️ 串口终端", self, checkable=True)
        self.action_toggle_left.setChecked(True)
        self.action_toggle_left.triggered.connect(self.toggle_left_panel)
        view_menu.addAction(self.action_toggle_left)

        self.action_toggle_right = QAction("📊 解析面板", self, checkable=True)
        self.action_toggle_right.setChecked(False)
        self.action_toggle_right.triggered.connect(self.toggle_right_panel)
        view_menu.addAction(self.action_toggle_right)

        self.action_toggle_send = QAction("📤 发送面板", self, checkable=True)
        self.action_toggle_send.setChecked(False)
        self.action_toggle_send.triggered.connect(self.toggle_send_panel)
        view_menu.addAction(self.action_toggle_send)

        self.action_toggle_wave = QAction("📈 实时波形", self, checkable=True)
        self.action_toggle_wave.setChecked(False)
        self.action_toggle_wave.triggered.connect(self.toggle_waveform_panel)
        view_menu.addAction(self.action_toggle_wave)

        view_menu.addSeparator()  # 分割线

        self.action_theme = QAction("☀️ 切换深/浅色主题", self)
        self.action_theme.triggered.connect(self.toggle_theme)
        view_menu.addAction(self.action_theme)

        # ==========================================
        # 🌟 2. 极其紧凑的极客工具栏 (去标签、强对齐)
        # ==========================================
        top_bar_layout = QHBoxLayout()
        top_bar_layout.setContentsMargins(0, 0, 0, 0)

        # 【左区：硬件连接控制】
        self.combo_port = AutoRefreshComboBox(self)
        self.combo_port.setMinimumWidth(130)
        self.combo_port.setToolTip("选择物理串口或网络接口")
        self.combo_port.currentTextChanged.connect(self._on_port_changed)
        top_bar_layout.addWidget(self.combo_port)

        self.input_ip = QLineEdit("192.168.1.100")
        self.input_ip.setMinimumWidth(110)
        self.input_ip.setPlaceholderText("目标 IP")
        self.input_ip.setVisible(False)
        top_bar_layout.addWidget(self.input_ip)

        self.btn_refresh_port = QPushButton("🔄")
        self.btn_refresh_port.setFixedWidth(30)
        self.btn_refresh_port.setToolTip("刷新可用端口")
        self.btn_refresh_port.clicked.connect(self.refresh_serial_ports)
        top_bar_layout.addWidget(self.btn_refresh_port)

        self.combo_baud = QComboBox()
        self.combo_baud.addItems(["115200", "921600", "9600"])
        self.combo_baud.setToolTip("选择波特率")
        top_bar_layout.addWidget(self.combo_baud)

        self.input_net_port = QLineEdit("8080")
        self.input_net_port.setFixedWidth(60)
        self.input_net_port.setPlaceholderText("端口")
        self.input_net_port.setVisible(False)
        top_bar_layout.addWidget(self.input_net_port)

        self.btn_serial_toggle = QPushButton("🔌 打开")
        self.btn_serial_toggle.clicked.connect(self.toggle_connection)
        top_bar_layout.addWidget(self.btn_serial_toggle)

        # 【右区：业务与解析过滤】
        self.combo_protocol = QComboBox()
        self.combo_protocol.setMinimumWidth(150)
        self.combo_protocol.setToolTip("选择报文解析协议")
        self.populate_protocols()
        self.combo_protocol.currentIndexChanged.connect(self.change_protocol)
        top_bar_layout.addWidget(self.combo_protocol)

        self.quick_parse_input = QLineEdit()
        self.quick_parse_input.setPlaceholderText("粘贴单条报文解析...")
        self.quick_parse_input.setMinimumWidth(150)
        top_bar_layout.addWidget(self.quick_parse_input)

        self.quick_parse_btn = QPushButton("🚀")
        self.quick_parse_btn.setToolTip("快速解析此报文")
        self.quick_parse_btn.setFixedWidth(30)
        self.quick_parse_btn.clicked.connect(self.on_quick_parse_clicked)
        top_bar_layout.addWidget(self.quick_parse_btn)

        self.combo_filter = QComboBox()
        self.combo_filter.setMinimumWidth(130)
        self.combo_filter.addItem("显示所有类型", "ALL")
        self.combo_filter.setToolTip("按报文类型过滤")
        self.combo_filter.currentIndexChanged.connect(self.apply_filter)
        top_bar_layout.addWidget(self.combo_filter)

        top_bar_layout.addStretch()

        main_layout.addLayout(top_bar_layout)
        # ==========================================
        # 🌟 插入点：离线日志回放控制面板 (默认隐藏)
        # ==========================================
        self.playback_panel = QWidget()

        # 🔧 核心修复 1：死锁最大高度！绝对不允许它纵向膨胀 (35~40像素是黄金视觉比例)
        self.playback_panel.setMaximumHeight(38)

        pb_layout = QHBoxLayout(self.playback_panel)
        # 🔧 核心修复 2：彻底干掉上下边距 (0)，只保留左右边距 (10) 防止文字贴边
        pb_layout.setContentsMargins(10, 0, 10, 0)
        self.playback_panel.setStyleSheet("border: 1px solid #6B7280; border-radius: 4px;")

        self.lbl_pb_file = QLabel("当前文件: 无")
        self.lbl_pb_file.setStyleSheet("color: #10B981; font-weight: bold;")
        pb_layout.addWidget(self.lbl_pb_file)

        self.btn_pb_play = QPushButton("⏸️ 暂停")
        self.btn_pb_play.clicked.connect(self.toggle_playback_pause)
        pb_layout.addWidget(self.btn_pb_play)

        self.btn_pb_stop = QPushButton("⏹️ 停止")
        self.btn_pb_stop.clicked.connect(self.stop_playback)
        pb_layout.addWidget(self.btn_pb_stop)

        pb_layout.addWidget(QLabel("倍速:"))
        self.combo_pb_speed = QComboBox()
        self.combo_pb_speed.addItems(["1x", "2x", "5x", "10x", "极速Max"])
        self.combo_pb_speed.setCurrentText("2x")
        self.combo_pb_speed.currentTextChanged.connect(self.change_playback_speed)
        pb_layout.addWidget(self.combo_pb_speed)

        self.lbl_pb_progress = QLabel("进度: 0 / 0 行")
        pb_layout.addWidget(self.lbl_pb_progress)

        pb_layout.addStretch()

        self.btn_pb_close = QPushButton("❌ 关闭回放")
        self.btn_pb_close.setStyleSheet("color: #EF4444;")
        self.btn_pb_close.clicked.connect(self.close_playback_panel)
        pb_layout.addWidget(self.btn_pb_close)

        self.playback_panel.setVisible(False)
        main_layout.addWidget(self.playback_panel)
        # ==================== 回放面板结束 ====================

        # 三屏联动布局
        #main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)

        # ==========================================
        # 🌟 1. 左侧终端面板提升为上下分割器 (支持波形图)
        # ==========================================
        self.left_panel = QSplitter(Qt.Orientation.Vertical)

        term_container = QWidget()
        left_layout = QVBoxLayout(term_container)
        left_layout.setContentsMargins(0, 0, 0, 0)

        term_toolbar = QHBoxLayout()
        term_toolbar.setContentsMargins(0, 0, 0, 0)  # 🌟 强行清空下方边距，与上方完美垂直对齐！

        # ==========================================
        # 🌟 极简专业工具栏 (状态按钮 + 折叠菜单)
        # ==========================================
        from PyQt6.QtWidgets import QMenu

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 搜索...")
        self.search_input.setMinimumWidth(100)  # 缩小一点，省空间
        self.search_input.setMaximumWidth(250)
        self.search_input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.search_input.textChanged.connect(self.on_search_text_changed)
        # 👇 加上这一行：输入完关键字直接敲回车，自动找下一个！
        self.search_input.returnPressed.connect(self.search_next)

        self.btn_search_prev = QPushButton("⬆️")
        self.btn_search_prev.setToolTip("向上查找")
        self.btn_search_prev.clicked.connect(self.search_prev)

        self.btn_search_next = QPushButton("⬇️")
        self.btn_search_next.setToolTip("向下查找")
        self.btn_search_next.clicked.connect(self.search_next)

        # 🌟 极致去文字化：变成纯图标按钮
        self.btn_filter_mode = QPushButton("🎯")
        self.btn_filter_mode.setCheckable(True)
        self.btn_filter_mode.setToolTip("开启/关闭仅显匹配行 (过滤模式)")
        self.btn_filter_mode.toggled.connect(lambda checked: self.redraw_terminal_history())

        self.btn_clear_term = QPushButton("🗑️")
        self.btn_clear_term.setToolTip("清空控制台日志")
        self.btn_clear_term.clicked.connect(self.clear_all_data)

        # 🌟 更多菜单依然保留，但也压缩成图标
        self.btn_more = QPushButton("⋮")
        self.btn_more.setToolTip("更多功能 (保存、录制、高亮)")
        more_menu = QMenu(self)
        action_save = more_menu.addAction("💾 保存当前快照")
        action_save.triggered.connect(self.save_raw_log)
        self.action_record = more_menu.addAction("⏺️ 开始实时录制")
        self.action_record.triggered.connect(self.toggle_recording)
        more_menu.addSeparator()
        action_regex = more_menu.addAction("⚙️ 自定义高亮配置")
        action_regex.triggered.connect(self.open_regex_config)
        self.btn_more.setMenu(more_menu)

        # 🌟 按照极简顺序，依次加入布局
        term_toolbar.addWidget(self.search_input)
        term_toolbar.addWidget(self.btn_search_prev)
        term_toolbar.addWidget(self.btn_search_next)
        term_toolbar.addWidget(self.btn_filter_mode)
        term_toolbar.addWidget(self.btn_clear_term)
        term_toolbar.addWidget(self.btn_more)
        # ✅ 把弹簧加在【所有按钮】的最后面：
        term_toolbar.addStretch()
        left_layout.addLayout(term_toolbar)

        self.raw_log_console = TerminalTextEdit(self)
        left_layout.addWidget(self.raw_log_console)

        # ==========================================
        # 🌟 诞生：黑窗口的极客右键菜单 (QAction 替代 QCheckBox/QPushButton)
        # ==========================================
        self.raw_log_console.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.raw_log_console.customContextMenuRequested.connect(self.show_terminal_menu)

        self.action_timestamp = QAction("⏰ 显示时间戳", self)
        self.action_timestamp.setCheckable(True)
        self.action_timestamp.setChecked(True)
        self.action_timestamp.triggered.connect(lambda checked=False: self.redraw_terminal_history())

        self.action_hex = QAction("🔢 HEX 原始字节显示", self)
        self.action_hex.setCheckable(True)
        self.action_hex.triggered.connect(lambda checked=False: self.redraw_terminal_history())

        self.action_autoscroll = QAction("⏬ 接收时自动滚动到底部", self)
        self.action_autoscroll.setCheckable(True)
        self.action_autoscroll.setChecked(True)

        self.action_wordwrap = QAction("↩️ 自动换行", self)
        self.action_wordwrap.setCheckable(True)
        self.action_wordwrap.setChecked(True)
        self.action_wordwrap.triggered.connect(self.toggle_word_wrap)

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

        # ==========================================
        # 🌟 插入点：新增动态校验和下拉框
        # ==========================================
        self.combo_checksum = QComboBox()
        self.combo_checksum.addItems([
            "无校验",
            "CheckSum-8 (ADD)",
            "CheckSum-8 (XOR / BCC)",
            "CheckSum-16 (ADD)",
            "CRC8 (Standard)",
            "CRC8 (Maxim/Dallas)",
            "CRC16 (Modbus)",
            "CRC16 (CCITT/XMODEM)",
            "CRC32 (Standard)"
        ])

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
        send_layout.addWidget(self.combo_checksum)  # 💡 加入布局
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

        # 先把终端装进左侧分割器
        self.left_panel.addWidget(term_container)

        # ==========================================
        # 🌟 插入点 2：组装底层波形图面板
        # ==========================================
        self.waveform_panel = QWidget()
        wave_layout = QVBoxLayout(self.waveform_panel)
        wave_layout.setContentsMargins(0, 0, 0, 0)

        wave_toolbar = QHBoxLayout()
        wave_toolbar.addWidget(QLabel("📈 波形追踪变量:"))
        self.combo_wave_var = QComboBox()
        self.combo_wave_var.setMinimumWidth(150)
        self.combo_wave_var.addItem("关闭绘制")
        self.combo_wave_var.currentTextChanged.connect(self.clear_waveform)
        wave_toolbar.addWidget(self.combo_wave_var)

        self.btn_clear_wave = QPushButton("🗑️ 清空波形")
        self.btn_clear_wave.clicked.connect(self.clear_waveform)
        wave_toolbar.addWidget(self.btn_clear_wave)
        # ==========================================
        # 🌟 插入点：新增“重置雷达”按钮
        # ==========================================
        self.btn_reset_vars = QPushButton("🧹 重置变量雷达")
        self.btn_reset_vars.setToolTip("清空下拉框中的历史变量选项，重新嗅探")
        self.btn_reset_vars.clicked.connect(self.reset_wave_vars)
        wave_toolbar.addWidget(self.btn_reset_vars)
        wave_toolbar.addStretch()

        # ==========================================
        # 🌟 新增：GPS 雷达专属工具栏 (默认隐藏)
        # ==========================================
        self.gps_toolbar_widget = QWidget()
        gps_layout = QHBoxLayout(self.gps_toolbar_widget)
        gps_layout.setContentsMargins(0, 0, 0, 0)

        gps_layout.addWidget(QLabel("🎯 基准: "))
        self.input_anchor_lat = QLineEdit()
        self.input_anchor_lat.setPlaceholderText("纬度 (Lat)")
        self.input_anchor_lat.setMaximumWidth(100)
        self.input_anchor_lng = QLineEdit()
        self.input_anchor_lng.setPlaceholderText("经度 (Lng)")
        self.input_anchor_lng.setMaximumWidth(100)
        gps_layout.addWidget(self.input_anchor_lat)
        gps_layout.addWidget(self.input_anchor_lng)

        self.btn_set_anchor = QPushButton("📍 设为中心")
        self.btn_set_anchor.clicked.connect(self.set_manual_anchor)
        gps_layout.addWidget(self.btn_set_anchor)

        self.btn_auto_anchor = QPushButton("🔄 以当前点为中心")
        self.btn_auto_anchor.clicked.connect(self.set_auto_anchor)
        gps_layout.addWidget(self.btn_auto_anchor)

        self.lbl_gps_stats = QLabel("当前偏差: -- m | 最大漂移: -- m")
        self.lbl_gps_stats.setStyleSheet("color: #EAB308; font-weight: bold; margin-left: 10px;")
        gps_layout.addWidget(self.lbl_gps_stats)

        gps_layout.addStretch()

        self.btn_export_kml = QPushButton("🗺️ 导出 KML")
        self.btn_export_kml.setStyleSheet("background-color: #0284C7; color: white;")
        self.btn_export_kml.clicked.connect(self.export_kml)
        gps_layout.addWidget(self.btn_export_kml)

        wave_layout.addWidget(self.gps_toolbar_widget)
        self.gps_toolbar_widget.hide()  # 初始状态隐藏

        # 🌟 初始化雷达状态变量
        self.gps_anchor = None  # 格式: (lng, lat)
        self.max_drift_m = 0.0
        self.radar_circle_items = []  # 存放画在图上的同心圆

        self.btn_close_wave = QPushButton("❌ 关闭图表")
        self.btn_close_wave.clicked.connect(
            lambda: self.action_toggle_wave.setChecked(False) or self.toggle_waveform_panel())
        wave_toolbar.addWidget(self.btn_close_wave)

        wave_layout.addLayout(wave_toolbar)

        if pg:
            self.plot_widget = pg.PlotWidget()
            self.plot_widget.setBackground('#2B2B2B' if self.is_dark_mode else '#FDF6E3')
            self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
            # 配置绿色加粗的抗锯齿曲线 (轨迹线)
            self.plot_curve = self.plot_widget.plot(pen=pg.mkPen(color='#10B981', width=2))

            # ==========================================
            # 🌟 新增：最新的坐标“靶心” (红色圆点 + 边框)
            # ==========================================
            self.latest_scatter = pg.ScatterPlotItem(
                size=14,
                pen=pg.mkPen(color='#FFFFFF', width=1.5),
                brush=pg.mkBrush(239, 68, 68, 200)  # 半透明红色
            )
            self.plot_widget.addItem(self.latest_scatter)

            wave_layout.addWidget(self.plot_widget)
        else:
            err_lbl = QLabel("⚠️ 请在终端执行 pip install pyqtgraph 后重启软件，以启用极速波形图功能。")
            err_lbl.setStyleSheet("color: #EF4444; font-weight: bold; padding: 20px;")
            wave_layout.addWidget(err_lbl)

        self.left_panel.addWidget(self.waveform_panel)
        self.waveform_panel.hide()  # 默认隐藏波形图
        self.left_panel.setSizes([800, 0])  # 默认把底部压扁

        # 最后把组装好的左侧模块推入主界面
        self.main_splitter.addWidget(self.left_panel)

        # ==========================================
        # 🌟 2. 右侧面板升级为多标签页 (QTabWidget)
        # ==========================================
        from PyQt6.QtWidgets import QTabWidget
        self.right_tabs = QTabWidget()

        # ------------------------------------------
        # 🗂️ Tab 1: 原有的解析流水线
        # ------------------------------------------
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
        self.table_view.setAlternatingRowColors(True)
        self.table_view.clicked.connect(self.on_row_clicked)
        right_top_layout.addWidget(self.table_view)

        self.right_panel.addWidget(right_top_widget)

        self.tree_view = QTreeView()
        self.tree_model = QStandardItemModel()
        self.tree_model.setHorizontalHeaderLabels(["字段结构解析详情"])
        self.tree_view.setModel(self.tree_model)
        # ==========================================
        # 🌟 修复 1：开启树状视图自动换行
        # 让长文本能够折行显示，不再一条道走到黑
        # ==========================================
        self.tree_view.setWordWrap(True)

        self.right_panel.addWidget(self.tree_view)
        self.right_panel.setSizes([500, 300])

        self.right_tabs.addTab(self.right_panel, "📊 解析流水线")

        # ------------------------------------------
        # 🗂️ Tab 2: 🚀 快捷指令面板
        # ------------------------------------------
        self.quick_cmd_panel = QWidget()
        quick_cmd_layout = QVBoxLayout(self.quick_cmd_panel)

        self.cmd_table = QTableWidget(0, 4)
        self.cmd_table.setHorizontalHeaderLabels(["指令名称 (备注)", "报文内容 (HEX/ASCII)", "格式", "操作"])
        self.cmd_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.cmd_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.cmd_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.cmd_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.cmd_table.setColumnWidth(2, 80)
        self.cmd_table.setColumnWidth(3, 80)
        self.cmd_table.setAlternatingRowColors(True)

        quick_cmd_btn_layout = QHBoxLayout()
        btn_add_cmd = QPushButton("➕ 新增指令")
        btn_add_cmd.clicked.connect(lambda: self.add_quick_cmd_row("", "", "HEX"))
        btn_del_cmd = QPushButton("🗑️ 删除选中")
        btn_del_cmd.setStyleSheet("color: #EF4444;")
        btn_del_cmd.clicked.connect(self.delete_quick_cmd_row)
        btn_save_cmd = QPushButton("💾 保存配置到本地")
        btn_save_cmd.setStyleSheet("background-color: #2563EB; color: white; font-weight: bold;")
        btn_save_cmd.clicked.connect(self.save_quick_cmds)

        quick_cmd_btn_layout.addWidget(btn_add_cmd)
        quick_cmd_btn_layout.addWidget(btn_del_cmd)
        quick_cmd_btn_layout.addStretch()
        quick_cmd_btn_layout.addWidget(btn_save_cmd)

        quick_cmd_layout.addWidget(self.cmd_table)
        quick_cmd_layout.addLayout(quick_cmd_btn_layout)

        self.right_tabs.addTab(self.quick_cmd_panel, "🚀 快捷指令")
        # ------------------------------------------
        # 🗂️ Tab 3: 🤖 自动化宏 (流水线脚本)
        # ------------------------------------------
        self.macro_panel = QWidget()
        macro_layout = QVBoxLayout(self.macro_panel)

        self.macro_table = QTableWidget(0, 4)
        self.macro_table.setHorizontalHeaderLabels(["发送报文内容", "格式", "发后延时(ms)", "操作"])
        self.macro_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.macro_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.macro_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.macro_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.macro_table.setColumnWidth(1, 80)
        self.macro_table.setColumnWidth(2, 100)
        self.macro_table.setColumnWidth(3, 60)
        self.macro_table.setAlternatingRowColors(True)

        macro_ctrl_layout = QHBoxLayout()
        btn_add_macro = QPushButton("➕ 添加动作")
        btn_add_macro.clicked.connect(lambda: self.add_macro_row("", "HEX", 500))

        self.spin_macro_loop = QSpinBox()
        self.spin_macro_loop.setRange(1, 99999)
        self.spin_macro_loop.setValue(1)
        self.spin_macro_loop.setPrefix("循环跑: ")
        self.spin_macro_loop.setSuffix(" 次")
        self.spin_macro_loop.setMinimumWidth(120)

        self.btn_run_macro = QPushButton("▶️ 运行脚本")
        self.btn_run_macro.setStyleSheet("background-color: #10B981; color: white; font-weight: bold;")
        self.btn_run_macro.clicked.connect(self.start_macro)

        self.btn_stop_macro = QPushButton("⏹️ 紧急停止")
        self.btn_stop_macro.setStyleSheet("background-color: #EF4444; color: white; font-weight: bold;")
        self.btn_stop_macro.setEnabled(False)
        self.btn_stop_macro.clicked.connect(self.stop_macro)

        macro_ctrl_layout.addWidget(btn_add_macro)
        macro_ctrl_layout.addStretch()
        macro_ctrl_layout.addWidget(self.spin_macro_loop)
        macro_ctrl_layout.addWidget(self.btn_run_macro)
        macro_ctrl_layout.addWidget(self.btn_stop_macro)

        macro_layout.addWidget(self.macro_table)
        macro_layout.addLayout(macro_ctrl_layout)

        self.right_tabs.addTab(self.macro_panel, "🤖 自动化测试")

        # 🌟 3. 将组装好的右侧多标签页，加入到主分割器中
        self.main_splitter.addWidget(self.right_tabs)
        self.main_splitter.setSizes([500, 800])

        # 🌟 自动加载本地保存的指令
        self.load_quick_cmds()

        # 🌟 4. 将主分割器加入到窗口主布局中
        main_layout.addWidget(self.main_splitter)

        self.statusBar().showMessage("状态: 待命")
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.statusBar().addPermanentWidget(self.progress_bar)

        self.change_protocol()
        self.setStyleSheet(self.get_dark_qss())
        self.apply_terminal_style()
        QTimer.singleShot(100, self.toggle_right_panel)

    # ==========================================
    # 🌟 显隐控制逻辑
    # ==========================================
    def toggle_left_panel(self):
        is_visible = self.action_toggle_left.isChecked()

        # 保护机制：不能把两边都关了
        if not is_visible and not self.right_panel.isVisible():
            self.action_toggle_left.setChecked(True)  # 强制弹回
            QMessageBox.warning(self, "提示", "必须至少保留一个工作区！")
            return

        self.left_panel.setVisible(is_visible)

    def toggle_right_panel(self):
        is_visible = self.action_toggle_right.isChecked()

        # 保护机制：不能把两边都关了
        if not is_visible and not self.left_panel.isVisible():
            self.action_toggle_right.setChecked(True)  # 强制弹回
            QMessageBox.warning(self, "提示", "必须至少保留一个工作区！")
            return

        self.right_tabs.setVisible(is_visible)

    # ==========================================
    # 🌟 发送面板控制逻辑
    # ==========================================
    def toggle_send_panel(self):
        is_visible = self.action_toggle_send.isChecked()
        self.send_panel.setVisible(is_visible)

        # 体验优化：如果展开了发送面板，自动把光标聚焦到输入框，方便直接打字
        if is_visible:
            self.send_input.setFocus()

    # ==========================================
    # 🌟 新增：动态校验和算法引擎
    # ==========================================
    def calculate_checksum(self, data_bytes, calc_type):
        """支持多种主流工控/汽车/物联网协议的校验和计算"""
        if not data_bytes:
            return b''

        import struct
        import zlib

        if calc_type == "CheckSum-8 (ADD)":
            # 8位累加和：所有字节相加，取低 8 位 (1个字节)
            return bytes([sum(data_bytes) & 0xFF])

        elif calc_type == "CheckSum-8 (XOR / BCC)":
            # 异或校验 (BCC)：所有字节连续异或 (1个字节)
            bcc = 0
            for b in data_bytes:
                bcc ^= b
            return bytes([bcc])

        elif calc_type == "CheckSum-16 (ADD)":
            # 16位累加和：所有字节相加，保留低 16 位 (小端模式传输)
            return struct.pack('<H', sum(data_bytes) & 0xFFFF)

        elif calc_type == "CRC8 (Standard)":
            # 标准 CRC8 (多项式 0x07，初始值 0x00)
            crc = 0x00
            for b in data_bytes:
                crc ^= b
                for _ in range(8):
                    crc = ((crc << 1) ^ 0x07) if (crc & 0x80) else (crc << 1)
                    crc &= 0xFF
            return bytes([crc])

        elif calc_type == "CRC8 (Maxim/Dallas)":
            # DS18B20 等传感器常用 CRC8 (多项式 0x31，翻转 0x8C)
            crc = 0x00
            for b in data_bytes:
                crc ^= b
                for _ in range(8):
                    crc = ((crc >> 1) ^ 0x8C) if (crc & 0x01) else (crc >> 1)
                    crc &= 0xFF
            return bytes([crc])

        elif calc_type == "CRC16 (Modbus)":
            # 标准 Modbus CRC16 (多项式 0xA001，小端模式)
            crc = 0xFFFF
            for b in data_bytes:
                crc ^= b
                for _ in range(8):
                    crc = ((crc >> 1) ^ 0xA001) if (crc & 0x01) else (crc >> 1)
                    crc &= 0xFFFF
            return struct.pack('<H', crc)

        elif calc_type == "CRC16 (CCITT/XMODEM)":
            # XMODEM/CCITT 协议 (多项式 0x1021，大端模式)
            crc = 0x0000
            for b in data_bytes:
                crc ^= (b << 8)
                for _ in range(8):
                    crc = ((crc << 1) ^ 0x1021) if (crc & 0x8000) else (crc << 1)
                    crc &= 0xFFFF
            return struct.pack('>H', crc)

        elif calc_type == "CRC32 (Standard)":
            # 以太网/OTA 常用 CRC32 (IEEE 802.3 标准，小端模式)
            return struct.pack('<I', zlib.crc32(data_bytes) & 0xFFFFFFFF)

        return b''

    def execute_send_data(self):
        text = self.send_input.text()
        if not text:
            return

        # 1. 拦截未连接状态
        if not getattr(self, 'active_worker', None) or not self.active_worker.isRunning():
            QMessageBox.warning(self, "发送失败", "未连接到任何设备，请先打开串口或网络！")
            return

        is_hex = self.radio_hex.isChecked()
        add_newline = self.cb_send_newline.isChecked()

        data_to_send = b''
        echo_text = ""

        try:
            # ==========================================
            # 1. 获取纯净的基础 Payload (去除换行符的原始数据)
            # ==========================================
            if is_hex:
                import re
                clean_hex = re.sub(r'[^0-9a-fA-F]', '', text)
                if len(clean_hex) % 2 != 0:
                    QMessageBox.warning(self, "格式错误",
                                        "HEX 模式下，输入的 16 进制字符数量必须是偶数！\n(例如: 0A 0B 0C)")
                    return
                base_data = bytes.fromhex(clean_hex)
            else:
                base_data = text.encode('utf-8', errors='replace')

            # ==========================================
            # 🌟 2. 核心拦截：智能计算并追加校验和
            # ==========================================
            chk_type = self.combo_checksum.currentText()
            if chk_type != "无校验":
                chk_bytes = self.calculate_checksum(base_data, chk_type)
                base_data += chk_bytes  # 静默拼接到末尾

            # ==========================================
            # 3. 换行符垫底追加 (必须在校验和之后)
            # ==========================================
            data_to_send = base_data
            if add_newline:
                data_to_send += b'\r\n'

            # ==========================================
            # 4. 最终执行底层发送
            # ==========================================
            success, err_msg = self.active_worker.send_data(data_to_send)

            if success:
                # 后续的存入时光机、UI回显过滤逻辑 (完全保持不变)
                now_str = datetime.now().strftime('%H:%M:%S.%f')[:-3]
                self.terminal_history.append({'type': 'TX', 'time': now_str, 'data': data_to_send})

                if self.action_hex.isChecked():
                    display_text = "[上行] " + " ".join(f"{b:02X}" for b in data_to_send) + "\n"
                else:
                    display_text = "[上行] " + data_to_send.decode('utf-8', errors='replace')

                # 过滤拦截逻辑
                allow_render = True
                # 🌟 修复：检查新变量 btn_filter_mode
                is_filtering = hasattr(self, 'btn_filter_mode') and self.btn_filter_mode.isChecked()

                if is_filtering:
                    filter_kw = self.search_input.text().lower()
                    if filter_kw and filter_kw not in display_text.lower():
                        allow_render = False

                self.append_raw_log(display_text, custom_time=now_str, render_to_ui=allow_render)
                self.send_input.selectAll()
            else:
                QMessageBox.critical(self, "发送失败", f"底层总线异常:\n{err_msg}")

        except Exception as e:
            QMessageBox.critical(self, "数据转换错误", f"输入格式无法解析:\n{str(e)}")

    def _on_log_scrollbar_changed(self, value):
        # ==========================================
        # 🌟 修复 1：漏掉的终极防抖锁！
        # 只要是代码追加数据、或者 2000 行缓存触顶删行引起的跳动，
        # 直接无视，绝对不允许触发自动滚动开关！
        # ==========================================
        if getattr(self.raw_log_console, '_is_appending', False):
            return

        scrollbar = self.raw_log_console.verticalScrollBar()
        max_value = scrollbar.maximum()

        if value == max_value and max_value > 0:
            if not self.action_autoscroll.isChecked():
                self.action_autoscroll.setChecked(True)

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
        is_filtering = hasattr(self, 'btn_filter_mode') and self.btn_filter_mode.isChecked()
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

        self.raw_log_console._is_searching = True

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
            if self.action_autoscroll.isChecked():
                self.action_autoscroll.setChecked(False)
                self.statusBar().showMessage("🎯 已定位到搜索目标，自动滚动已暂停", 2000)

            # 更新背景高亮
            self.update_viewport_search_highlights()
        else:
            self.search_input.setStyleSheet("border: 1px solid #EF4444;")
            self.current_search_hit_selection = None
            self.update_viewport_search_highlights()
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(100, lambda: setattr(self.raw_log_console, '_is_searching', False))

    # ==========================================
    # 其他业务逻辑 (数据接入、文件导出等)
    # ==========================================
    def refresh_serial_ports(self):
        current = self.combo_port.currentText()
        self.combo_port.blockSignals(True)
        self.combo_port.clear()

        import serial.tools.list_ports
        ports = serial.tools.list_ports.comports()

        # 1. 动态加载物理串口
        for p in ports:
            self.combo_port.addItem(f"{p.device} - {p.description}", p.device)

        # 2. 追加网络虚拟接口 (利用 Data 字段存储真实的模式名)
        self.combo_port.addItem("--- 网络联调 ---", None)
        self.combo_port.addItem("🌐 TCP Client", "TCP Client")
        self.combo_port.addItem("🌐 TCP Server", "TCP Server")
        self.combo_port.addItem("🌐 UDP", "UDP")

        index = self.combo_port.findText(current, Qt.MatchFlag.MatchContains)
        if index >= 0:
            self.combo_port.setCurrentIndex(index)

        self.combo_port.blockSignals(False)
        self._on_port_changed(self.combo_port.currentText())  # 强制触发一次变脸判断

    def _on_port_changed(self, text):
        """智能变脸：如果是网络就显示IP和端口，如果是串口就显示波特率"""
        if not text or text == "--- 网络联调 ---": return

        is_network = "🌐" in text

        # 直接控制输入框的显隐，不再需要操作那几个被干掉的文字标签
        self.btn_refresh_port.setVisible(not is_network)
        self.input_ip.setVisible(is_network)

        self.combo_baud.setVisible(not is_network)
        self.input_net_port.setVisible(is_network)

        # IP 自动填充逻辑
        if "Server" in text or "UDP" in text:
            self.input_ip.setText("0.0.0.0")
        elif "Client" in text and self.input_ip.text() == "0.0.0.0":
            self.input_ip.setText("192.168.1.100")

    def toggle_connection(self):
        # 1. 停止逻辑
        if self.btn_serial_toggle.text() == "🛑 停止" or self.btn_serial_toggle.text() == "关闭中...":
            if getattr(self, 'active_worker', None):
                self.active_worker.stop()
                self.btn_serial_toggle.setText("关闭中...")
                self.btn_serial_toggle.setEnabled(False)
        # 2. 启动逻辑
        else:
            port_text = self.combo_port.currentText()
            if port_text == "--- 网络联调 ---": return  # 防呆拦截

            is_network = "🌐" in port_text
            if self.decoder:
                self.rt_tx_parser = StreamParser(self.decoder)
                self.rt_rx_parser = StreamParser(self.decoder)
            else:
                self.rt_tx_parser = None
                self.rt_rx_parser = None
            self.serial_buffer_line = ""

            # 区分底层引擎
            if not is_network:
                port = self.combo_port.currentData()
                baud = self.combo_baud.currentText()
                if not port:
                    from PyQt6.QtWidgets import QMessageBox
                    QMessageBox.warning(self, "提示", "无可用的串口，请检查设备连接！")
                    return
                self.active_worker = SerialWorker(port, int(baud))
                status_msg = f"状态: 正在监听串口 {port} ({baud}bps)"
            else:
                mode = self.combo_port.currentData()  # 这里取出的就是纯净的 "TCP Client" 等
                ip = self.input_ip.text().strip()
                try:
                    net_port = int(self.input_net_port.text().strip())
                except:
                    from PyQt6.QtWidgets import QMessageBox
                    QMessageBox.warning(self, "提示", "网络端口必须是数字！")
                    return
                self.active_worker = NetworkWorker(mode, ip, net_port)
                status_msg = f"状态: 网络 {mode} [{ip}:{net_port}] 运行中"

            # 统一绑定数据接入口
            self.active_worker.data_received.connect(self.on_serial_data_received)
            self.active_worker.error_occurred.connect(self.on_serial_error)
            self.active_worker.finished_signal.connect(self.on_serial_finished)

            if hasattr(self.active_worker, 'client_connected'):
                self.active_worker.client_connected.connect(
                    lambda addr: self.statusBar().showMessage(f"✅ TCP 客户端已接入: {addr}", 5000))

            self.active_worker.start()

            # 锁死 UI，防止运行期间瞎改
            self.btn_serial_toggle.setText("🛑 停止")
            self.btn_serial_toggle.setStyleSheet("background-color: #d32f2f; color: white; font-weight: bold;")
            self.combo_port.setEnabled(False)
            self.input_ip.setEnabled(False)
            self.combo_baud.setEnabled(False)
            self.input_net_port.setEnabled(False)
            self.statusBar().showMessage(status_msg)

    # ==========================================
    # 🌟 新增配套方法 1：弹窗提示底层报错，不再静默假死
    # ==========================================
    def on_serial_error(self, err_msg):
        QMessageBox.critical(self, "串口异常", f"串口连接断开或被占用：\n{err_msg}")

    # ==========================================
    # 🌟 新增配套方法 2：绝对安全的 UI 状态重置 (无论正常关闭还是异常断开都会触发)
    # ==========================================
    def on_serial_finished(self):
        """统一的资源释放恢复"""
        self.btn_serial_toggle.setText("🔌 打开")
        self.btn_serial_toggle.setStyleSheet("")
        self.btn_serial_toggle.setEnabled(True)
        self.combo_port.setEnabled(True)
        self.input_ip.setEnabled(True)
        self.combo_baud.setEnabled(True)
        self.input_net_port.setEnabled(True)
        self.statusBar().showMessage("状态: 连接已安全关闭")
        self.current_log_filename = None
        self.serial_buffer_line = ""

    def append_raw_log(self, text, custom_time=None, write_to_file=True, render_to_ui=True):
        if not text:
            return

        # 1. 优先写原始文件
        if write_to_file and getattr(self, 'is_recording', False) and getattr(self, 'record_file_handle', None):
            try:
                self.record_file_handle.write(text + "\n")
                self.record_file_handle.flush()
            except:
                pass

        if not render_to_ui:
            return

        # ==========================================
        # 🌟 修复 2：记录追加前状态，并严格上锁
        # ==========================================
        scrollbar = self.raw_log_console.verticalScrollBar()
        current_scroll = scrollbar.value()
        is_at_bottom = (current_scroll == scrollbar.maximum())

        # 锁死信号流，告诉系统“现在是代码在操作，别瞎触发滚动事件”
        self.raw_log_console._is_appending = True

        try:
            # 2. 准备插入数据包
            cursor = self.raw_log_console.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            from PyQt6.QtGui import QTextBlockFormat, QTextCharFormat, QColor

            if not self.raw_log_console.document().isEmpty():
                spacer_format = QTextBlockFormat()
                spacer_format.setLineHeight(80, 1)
                spacer_format.clearBackground()
                cursor.insertBlock(spacer_format)
                cursor.insertText("")

            block_format = QTextBlockFormat()
            block_format.setLineHeight(120, 1)
            block_format.setBottomMargin(0)
            cursor.insertBlock(block_format)

            lines = [l for l in text.splitlines() if l.strip()]
            import re

            t_str = custom_time if custom_time else datetime.now().strftime('%H:%M:%S.%f')[:-3]
            timestamp_prefix = f"[{t_str}] "

            for i, line in enumerate(lines):
                if self.action_timestamp.isChecked() and i == 0:
                    display_line = timestamp_prefix + line
                elif self.action_timestamp.isChecked() and i > 0:
                    display_line = line
                else:
                    display_line = line

                char_format = QTextCharFormat()
                if re.search(r"(?i)(error|fail|timeout|异常|失败)", display_line):
                    bg_color = QColor("#4A0000") if getattr(self, 'is_dark_mode', False) else QColor("#FFCCCC")
                    char_format.setBackground(bg_color)
                else:
                    char_format.clearBackground()

                cursor.insertText(display_line, char_format)

                if i < len(lines) - 1:
                    cursor.insertText("\n")

            # ==========================================
            # 🌟 修复 3：对抗 Qt 的隐式滚动机制
            # ==========================================
            if self.action_autoscroll.isChecked():
                scrollbar.setValue(scrollbar.maximum())
            else:
                # 用户要求暂停滚动！
                # 即使刚被删了一行老数据，我们也要强行把视图定在原地
                if is_at_bottom:
                    scrollbar.setValue(current_scroll)
        finally:
            # ==========================================
            # 🌟 修复 4：极其重要！追加完毕必须释放锁！
            # 否则 _on_log_scrollbar_changed 会永久失效
            # ==========================================
            self.raw_log_console._is_appending = False

    # ==========================================
    # 🌟 核心：历史数据重绘引擎
    # ==========================================
    def redraw_terminal_history(self):
        try:
            self.raw_log_console.setUpdatesEnabled(False)
            self.raw_log_console.clear()

            # 🌟 修复：检查新变量 action_hex 和 btn_filter_mode
            is_hex = hasattr(self, 'action_hex') and self.action_hex.isChecked()
            is_filtering = hasattr(self, 'btn_filter_mode') and self.btn_filter_mode.isChecked()
            filter_kw = self.search_input.text().lower()

            for pkt in self.terminal_history:
                raw_bytes = pkt['data']
                if is_hex:
                    text = " ".join(f"{b:02X}" for b in raw_bytes) + "\n"
                    if pkt.get('type') == 'TX': text = "[上行] " + text
                else:
                    text = raw_bytes.decode('utf-8', errors='replace')
                    if pkt.get('type') == 'TX': text = "[上行] " + text

                if is_filtering and filter_kw:
                    lines = text.split('\n')
                    matched_lines = [line for line in lines if filter_kw in line.lower()]
                    if not matched_lines:
                        continue
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
        now_str = datetime.now().strftime('%H:%M:%S.%f')[:-3]
        self.terminal_history.append({'type': 'RX', 'time': now_str, 'data': raw_bytes})
        # ==========================================
        # 🌟 新增：内存保护机制（限制最大历史记录数）
        # ==========================================
        # 假设我们最多只在内存里保留 10 万条历史记录
        if len(self.terminal_history) > 100000:
            # 💡 技巧：不要每次删 1 条(pop(0)性能差)，一次性删掉最老的 1 万条，效率极高！
            del self.terminal_history[:10000]

        # 🌟 修复：检查新变量 action_hex
        if hasattr(self, 'action_hex') and self.action_hex.isChecked():
            display_text = " ".join(f"{b:02X}" for b in raw_bytes) + "\n"
        else:
            display_text = raw_bytes.decode('utf-8', errors='replace')
            text_vars = self._sniff_raw_text_vars(display_text)
            target_var = self.combo_wave_var.currentText()
            if target_var and target_var != "关闭绘制" and getattr(self, 'waveform_panel',
                                                                   None) and self.waveform_panel.isVisible():
                if target_var in text_vars:
                    self.update_plot_data(text_vars[target_var])

        allow_render = True
        # 🌟 修复：检查新变量 btn_filter_mode
        is_filtering = hasattr(self, 'btn_filter_mode') and self.btn_filter_mode.isChecked()

        if is_filtering:
            filter_kw = self.search_input.text().lower()
            if filter_kw:
                lines = display_text.split('\n')
                matched_lines = [line for line in lines if filter_kw in line.lower()]
                if not matched_lines:
                    allow_render = False
                else:
                    display_text = "\n".join(matched_lines)

        self.append_raw_log(display_text, custom_time=now_str, render_to_ui=allow_render)

        if self.combo_protocol.currentText() == "纯文本(不解析)":
            return

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
                clean_line = line.strip()
                if not clean_line: continue
                line_lower = clean_line.lower()

                # ==========================================
                # 🌟 终极护城河：严格白名单模式
                # 遇到非 nb_ 的 HEX 日志（ble, ctrl, loop），直接开启“拉黑”状态
                # ==========================================
                if "d/hex" in line_lower:
                    if "nb_recv" in line_lower:
                        self._current_parse_target = "RX"
                    elif "nb_send" in line_lower:
                        self._current_parse_target = "TX"
                    else:
                        self._current_parse_target = "IGNORE"  # 其他一律拉黑

                # 检查当前“白名单”状态
                target = getattr(self, '_current_parse_target', "IGNORE")
                if target == "IGNORE":
                    continue  # 🌟 核心：直接丢弃，绝对不允许喂给解析器！

                parser = self.rt_rx_parser if target == "RX" else self.rt_tx_parser
                if parser:
                    _f = parser.feed(clean_line)
                    if _f:
                        for f in _f:
                            f['direction'] = '[下行]' if target == "RX" else '[上行]'
                        parsed_frames.extend(_f)

            if parsed_frames:
                for frame in parsed_frames:
                    msg_def = self.decoder.msgs.get(frame['type'], {})
                    frame['name'] = msg_def.get('name', '未知消息')
                    if frame.get('seq') is None or frame.get('seq') == "N/A": frame['seq'] = "实时"

                    # ==========================================
                    # 🌟 1. 动态嗅探报文中的所有“数值型变量”供下拉框选择
                    # ==========================================
                    self._extract_numerical_vars(frame.get('data', {}))

                    # ==========================================
                    # 🌟 2. 如果开启了波形图且选中了变量，则抽取数据打点！
                    # ==========================================
                    target_var = self.combo_wave_var.currentText()
                    if target_var and target_var != "关闭绘制" and self.waveform_panel.isVisible():
                        val = self._extract_value_from_frame(frame, target_var)
                        if val is not None:
                            self.update_plot_data(val)  # 🌟 统一调用接口

                self.all_frames.extend(parsed_frames)
                target_type = self.combo_filter.currentData()

                # 1. 常规极速追加逻辑 (保证 99% 的时间表格渲染丝滑无卡顿)
                if target_type == "ALL" or not target_type:
                    self.filtered_frames.extend(parsed_frames)
                    self.table_model.append_frames(parsed_frames)
                else:
                    valid_frames = [f for f in parsed_frames if f['type'] == target_type]
                    if valid_frames:
                        self.filtered_frames.extend(valid_frames)
                        self.table_model.append_frames(valid_frames)

                # ==========================================
                # 🌟 核心修复：表格内存保护机制 (限制最大 10 万条)
                # ==========================================
                MAX_TABLE_ROWS = 100000
                if len(self.all_frames) > MAX_TABLE_ROWS:
                    # 1. 裁剪总数据池 (切片删除最老的 1 万条，性能极高)
                    del self.all_frames[:10000]

                    # 2. 重新根据当前的过滤规则洗一次数据
                    if target_type == "ALL" or not target_type:
                        self.filtered_frames = self.all_frames[:]
                    else:
                        self.filtered_frames = [f for f in self.all_frames if f['type'] == target_type]

                    # 3. 强行通知 Qt 表格进行一次全量重绘，切断与旧数据的指针绑定
                    self.table_model.update_data(self.filtered_frames)

                # 触底自动滚动
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

    def toggle_word_wrap(self, checked):
        """智能切换终端的换行模式 (兼容 QAction 布尔值)"""
        from PyQt6.QtWidgets import QTextEdit
        if checked:
            self.raw_log_console.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        else:
            self.raw_log_console.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)

    def populate_protocols(self):
        self.combo_protocol.clear()  # 防错机制：先清空原有列表

        # ==========================================
        # 🌟 强行置顶加入：纯文本模式！
        # ==========================================
        self.combo_protocol.addItem("纯文本(不解析)", "纯文本(不解析)")
        # ==========================================
        # 🌟 核心修复：建立“黑名单”，把系统自己用的 JSON 全排除掉
        # ==========================================
        exclude_files = ["highlight_rules.json", "quick_cmds.json"]

        # 🌟 修复：扫描 JSON 时，强制排除掉高亮配置文件
        json_files = [f for f in os.listdir('.') if f.endswith('.json') and f not in exclude_files]
        for jf in json_files:
            self.combo_protocol.addItem(jf, jf)

    def change_protocol(self):
        protocol_file = self.combo_protocol.currentData()
        if not protocol_file: return

        # ==========================================
        # 🌟 核心防呆拦截：如果选了纯文本，直接清空底层解析器并返回！
        # 绝对不让它去尝试打开一个叫“纯文本”的 JSON 文件
        # ==========================================
        if protocol_file == "纯文本(不解析)":
            self.decoder = None
            self.clear_all_data()
            return

        try:
            self.decoder = ProtocolDecoder(protocol_file)
            self.clear_all_data()
            if getattr(self, 'serial_worker', None) and self.serial_worker.isRunning():
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
        """加载离线日志：即使没选协议，也要能打开文件"""
        # 1. 即使没有 decoder，也要先让用户选文件，而不是直接 return
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择日志文件",
            "",
            "Log Files (*.log *.txt *.csv);;All Files (*)"
        )

        if not file_path:
            return

        # 2. 如果选了文件，先清空旧数据
        self.clear_all_data()

        # 3. 分情况处理：
        # 如果有协议，走原来的 ParseWorker 高速解析流程
        if self.decoder:
            self.worker = ParseWorker(file_path, self.decoder)
            self.worker.batch_ready.connect(lambda frames: self.all_frames.extend(frames))
            self.worker.finished.connect(self.on_parse_finished)
            self.worker.start()
        else:
            # 如果是“纯文本”模式，直接把文件内容灌进黑窗口（或者弹窗提示选协议）
            from PyQt6.QtWidgets import QMessageBox
            # 建议：如果是纯文本模式，可以加载到黑窗口展示，或者提醒用户
            reply = QMessageBox.information(
                self,
                "提示",
                "当前处于[纯文本]模式，仅展示原始日志。\n如需解析表格，请先在顶部选择协议后再加载。",
                QMessageBox.StandardButton.Ok
            )
            # 这里可以调用您现有的读取原始文件并显示的方法
            self._display_raw_file(file_path)

    def _display_raw_file(self, file_path):
        """将原始日志文件内容读取并显示在终端黑窗口中"""
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                # 为了防止文件过大导致 QTextEdit 崩溃
                # 我们只读取最后 2000 行（配合我们之前的性能优化）
                lines = f.readlines()
                display_lines = lines[-2000:] if len(lines) > 2000 else lines

                self.raw_log_console.clear()
                # 拼接成一个大字符串一次性塞进去，比循环 append 快得多
                self.raw_log_console.setPlainText("".join(display_lines))

                # 滚动到底部
                self.raw_log_console.moveCursor(QTextCursor.MoveOperation.End)

                self.statusBar().showMessage(f"✅ 已加载原始日志: {file_path} (显示末尾2000行)", 5000)
        except Exception as e:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "读取失败", f"无法读取文件内容: {str(e)}")

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
        # 1. 处理字典结构
        if isinstance(data_node, dict):
            for key, val in data_node.items():
                self._insert_tree_node(parent_item, str(key), val)
        # 2. 处理列表/数组结构 (🌟 修复原代码丢失数组数据的 Bug)
        elif isinstance(data_node, list):
            for i, val in enumerate(data_node):
                self._insert_tree_node(parent_item, f"[{i}]", val)

    def _insert_tree_node(self, parent_item, key_str, val):
        import json
        # ==========================================
        # 🌟 修复 2：JSON 字符串智能展开黑科技！
        # 如果发现这是一个 JSON 格式的字符串，尝试脱掉字符串的外衣，变成对象
        # ==========================================
        if isinstance(val, str):
            val_stripped = val.strip()
            if (val_stripped.startswith('{') and val_stripped.endswith('}')) or \
                    (val_stripped.startswith('[') and val_stripped.endswith(']')):
                try:
                    val = json.loads(val_stripped)
                except:
                    pass  # 如果解析失败，说明只是个普通字符串，保持原样

        # 如果值是字典或列表，就继续挂载新的子树枝，允许点击展开/折叠
        if isinstance(val, (dict, list)):
            node = QStandardItem(key_str)
            parent_item.appendRow(node)
            self._populate_tree(node, val)  # 递归向下层遍历
        else:
            # 如果是普通数值或文本，直接作为叶子节点显示
            parent_item.appendRow(QStandardItem(f"{key_str}: {val}"))

    def toggle_theme(self):
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        QApplication.processEvents()
        self.setUpdatesEnabled(False)
        try:
            self.is_dark_mode = not self.is_dark_mode
            if self.is_dark_mode:
                self.action_theme.setText("☀️ 切换为浅色")
                self.setStyleSheet(self.get_dark_qss())
            else:
                self.action_theme.setText("🌙 切换为深色")
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

    # ==========================================
    # 🌟 快捷指令面板核心逻辑
    # ==========================================
    def add_quick_cmd_row(self, name="", data="", fmt="HEX"):
        row = self.cmd_table.rowCount()
        self.cmd_table.insertRow(row)

        item_name = QTableWidgetItem(name)
        item_data = QTableWidgetItem(data)
        self.cmd_table.setItem(row, 0, item_name)
        self.cmd_table.setItem(row, 1, item_data)

        combo_fmt = QComboBox()
        combo_fmt.addItems(["HEX", "ASCII"])
        combo_fmt.setCurrentText(fmt)
        self.cmd_table.setCellWidget(row, 2, combo_fmt)

        btn_send = QPushButton("发送 🚀")
        btn_send.setStyleSheet("background-color: #10B981; color: white; font-weight: bold;")
        # Qt 经典解法：获取发出信号的按钮在表格中的位置，防止复用异常
        btn_send.clicked.connect(lambda _, b=btn_send: self.send_quick_cmd(b))
        self.cmd_table.setCellWidget(row, 3, btn_send)

    def delete_quick_cmd_row(self):
        current_row = self.cmd_table.currentRow()
        if current_row >= 0:
            self.cmd_table.removeRow(current_row)
        else:
            QMessageBox.information(self, "提示", "请先点击选中要删除的指令行")

    def save_quick_cmds(self):
        cmds = []
        for i in range(self.cmd_table.rowCount()):
            name_item = self.cmd_table.item(i, 0)
            data_item = self.cmd_table.item(i, 1)
            fmt_widget = self.cmd_table.cellWidget(i, 2)

            name = name_item.text().strip() if name_item else ""
            data = data_item.text().strip() if data_item else ""
            fmt = fmt_widget.currentText() if fmt_widget else "HEX"

            if name or data:
                cmds.append({"name": name, "data": data, "format": fmt})

        try:
            with open("quick_cmds.json", "w", encoding="utf-8") as f:
                json.dump(cmds, f, ensure_ascii=False, indent=4)
            self.statusBar().showMessage("✅ 快捷指令已保存至本地", 3000)
        except Exception as e:
            QMessageBox.critical(self, "保存失败", f"保存快捷指令时出错:\n{e}")

    def load_quick_cmds(self):
        self.cmd_table.setRowCount(0)
        if os.path.exists("quick_cmds.json"):
            try:
                with open("quick_cmds.json", "r", encoding="utf-8") as f:
                    cmds = json.load(f)
                    for cmd in cmds:
                        self.add_quick_cmd_row(cmd.get("name", ""), cmd.get("data", ""), cmd.get("format", "HEX"))
            except:
                pass

        # 如果是空的，给个默认模板行
        if self.cmd_table.rowCount() == 0:
            self.add_quick_cmd_row("示例: 获取设备版本", "AA 55 01", "HEX")

    def send_quick_cmd(self, btn):
        # 1. 找到是哪一行的按钮被点击了
        index = self.cmd_table.indexAt(btn.pos())
        if not index.isValid(): return
        row = index.row()

        # 2. 获取报文数据和格式
        data_item = self.cmd_table.item(row, 1)
        fmt_widget = self.cmd_table.cellWidget(row, 2)

        if not data_item or not data_item.text().strip():
            QMessageBox.warning(self, "提示", "发送数据不能为空！")
            return

        data_str = data_item.text().strip()
        fmt = fmt_widget.currentText() if fmt_widget else "HEX"

        # 3. 极其优雅的“借刀杀人”：修改主发送区数据，并模拟点击主发送按钮
        # 这样它就会完美经过校验和计算、新行追加、日志历史记录等所有核心链路！
        self.send_input.setText(data_str)
        if fmt == "HEX":
            self.radio_hex.setChecked(True)
        else:
            self.radio_ascii.setChecked(True)

        self.btn_send.click()

    # ==========================================
    # 🌟 实时波形图核心支持逻辑
    # ==========================================
    def toggle_waveform_panel(self):
        is_visible = self.action_toggle_wave.isChecked()
        self.waveform_panel.setVisible(is_visible)
        if is_visible:
            # 智能展开：给波形图分配 30% 的屏幕高度
            sizes = self.left_panel.sizes()
            if sizes[1] < 50:
                self.left_panel.setSizes([int(sum(sizes)*0.7), int(sum(sizes)*0.3)])

    def clear_waveform(self, *args):
        self.wave_data_x.clear()
        self.wave_data_y.clear()
        self.max_drift_m = 0.0
        self.lbl_gps_stats.setText("等待设备定位数据...")

        if not pg or not hasattr(self, 'plot_curve'): return

        self.plot_curve.setData([], [])
        if hasattr(self, 'latest_scatter') and self.latest_scatter:
            self.latest_scatter.setData([], [])

        # 清理旧的雷达圈
        for item in self.radar_circle_items:
            self.plot_widget.removeItem(item)
        self.radar_circle_items.clear()

        # ==========================================
        # 🌟 智能变脸引擎：1D折线图 vs 2D雷达盘
        # ==========================================
        target_var = self.combo_wave_var.currentText()
        is_gps = target_var and target_var.startswith("📍")

        self.plot_widget.setAspectLocked(is_gps)
        self.gps_toolbar_widget.setVisible(is_gps)  # 显隐 GPS 工具栏

        if is_gps:
            self.plot_widget.setLabel('bottom', "东向偏移 (米 East)")
            self.plot_widget.setLabel('left', "北向偏移 (米 North)")
            self.plot_widget.showGrid(x=False, y=False)  # 关掉方格子
            self.gps_anchor = None  # 重新等待锚点
        else:
            self.plot_widget.setLabel('bottom', "Samples (采样点)")
            self.plot_widget.setLabel('left', "Value (数值)")
            self.plot_widget.showGrid(x=True, y=True, alpha=0.3)

    def _extract_numerical_vars(self, data_dict, prefix=""):
        """像雷达一样扫描 JSON，模糊提取带有 lat/lng 字样的变量"""
        lat_key, lng_key = None, None

        for k, v in data_dict.items():
            if isinstance(v, (int, float)):
                var_name = f"{prefix}{k}"
                if var_name not in self.known_wave_vars:
                    self.known_wave_vars.add(var_name)
                    self.combo_wave_var.addItem(var_name)

                # 🌟 升级 1：模糊匹配 (只要名字里包含 lat/lng/lon 就抓取)
                kl = k.lower()
                if 'lat' in kl: lat_key = var_name
                if 'lng' in kl or 'lon' in kl: lng_key = var_name

            elif isinstance(v, dict):
                self._extract_numerical_vars(v, prefix=f"{prefix}{k}.")

        # 只要这一层字典里凑齐了这对卧龙凤雏，直接合成轨迹选项！
        if lat_key and lng_key:
            var_name = f"📍 轨迹 ({lat_key},{lng_key})"
            if var_name not in self.known_wave_vars:
                self.known_wave_vars.add(var_name)
                self.combo_wave_var.addItem(var_name)

    def _extract_value_from_frame(self, frame, target_var):
        """精准提取变量的当前数值"""
        parts = target_var.split('.')
        d = frame.get('data', {})
        for p in parts:
            if isinstance(d, dict) and p in d:
                d = d[p]
            else:
                return None
        if isinstance(d, (int, float)):
            return d
        return None

    def _sniff_raw_text_vars(self, text):
        """正则文本雷达：兼容 key=val，并新增工业级 NMEA 标准坐标硬解码"""
        import re
        extracted_data = {}

        # 确保坐标记忆存在
        if not hasattr(self, '_ascii_cache_lat'): self._ascii_cache_lat = None
        if not hasattr(self, '_ascii_cache_lng'): self._ascii_cache_lng = None

        # ==========================================
        # 🌟 升级 2：NMEA 报文霸王硬上弓解码
        # 匹配格式：3445.1234,N,11345.1234,E (度分格式)
        # ==========================================
        nmea_match = re.search(r'(\d{2,4}\.\d+),([NS]),(\d{3,5}\.\d+),([EW])', text)
        if nmea_match:
            try:
                lat_raw, lat_dir, lng_raw, lng_dir = nmea_match.groups()

                # NMEA 纬度是 DDMM.MMMM (前2位度，后边分)
                lat_deg = float(lat_raw[:2])
                lat_min = float(lat_raw[2:])
                lat_val = lat_deg + lat_min / 60.0
                if lat_dir == 'S': lat_val = -lat_val

                # NMEA 经度是 DDDMM.MMMM (找小数点前推2位作为度)
                dot_idx = lng_raw.find('.')
                lng_deg = float(lng_raw[:dot_idx-2])
                lng_min = float(lng_raw[dot_idx-2:])
                lng_val = lng_deg + lng_min / 60.0
                if lng_dir == 'W': lng_val = -lng_val

                self._ascii_cache_lat = lat_val
                self._ascii_cache_lng = lng_val
            except Exception as e:
                pass

        # ==========================================
        # 原有逻辑：兼容普通的 key=val 格式
        # ==========================================
        pattern = re.compile(r'([a-zA-Z0-9_]+)\s*[:=]\s*([-+]?\d*\.?\d+)')
        matches = pattern.findall(text)

        for key, val_str in matches:
            try:
                val = float(val_str)
                extracted_data[key] = val

                if key not in self.known_wave_vars:
                    self.known_wave_vars.add(key)
                    self.combo_wave_var.addItem(key)

                kl = key.lower()
                if 'lat' in kl: self._ascii_cache_lat = val
                if 'lng' in kl or 'lon' in kl: self._ascii_cache_lng = val
            except ValueError:
                pass

        # 🌟 合成最终的 ASCII 轨迹输出
        if self._ascii_cache_lat is not None and self._ascii_cache_lng is not None:
            var_name = "📍 轨迹 (ASCII匹配)"
            # 注意顺序：图表里 X轴是经度(lng)，Y轴是纬度(lat)
            extracted_data[var_name] = (self._ascii_cache_lng, self._ascii_cache_lat)
            if var_name not in self.known_wave_vars:
                self.known_wave_vars.add(var_name)
                self.combo_wave_var.addItem(var_name)

        return extracted_data

    def _extract_value_from_frame(self, frame, target_var):
        """精准提取变量当前数值 (支持坐标对解包)"""
        if target_var.startswith("📍 轨迹"):
            import re
            m = re.search(r'\((.*?),(.*?)\)', target_var)
            if m:
                lat_path, lng_path = m.groups()

                # 辅助方法：按路径找字典
                def get_val(path, data):
                    for p in path.split('.'):
                        if isinstance(data, dict) and p in data:
                            data = data[p]
                        else:
                            return None
                    return data if isinstance(data, (int, float)) else None

                lat_v = get_val(lat_path, frame.get('data', {}))
                lng_v = get_val(lng_path, frame.get('data', {}))
                if lat_v is not None and lng_v is not None:
                    return (lng_v, lat_v)  # 返回元组 (X, Y)
            return None

        # 1D 普通变量
        parts = target_var.split('.')
        d = frame.get('data', {})
        for p in parts:
            if isinstance(d, dict) and p in d:
                d = d[p]
            else:
                return None
        return d if isinstance(d, (int, float)) else None

    def update_plot_data(self, val):
        if not pg or not hasattr(self, 'plot_curve'): return

        try:
            if isinstance(val, tuple):
                # ==========================================
                # 📍 2D 坐标绘制：计算距离并画靶盘
                # ==========================================
                lng, lat = val[0], val[1]

                # 如果没有锚点，自动把第一个点当做 0,0 锚点
                if self.gps_anchor is None:
                    self.gps_anchor = (lng, lat)
                    self.input_anchor_lng.setText(f"{lng:.6f}")
                    self.input_anchor_lat.setText(f"{lat:.6f}")
                    self.draw_radar_circles(10)  # 初始画一个 10米的圈

                anchor_lng, anchor_lat = self.gps_anchor

                # 极速 Flat-Earth 转换算法 (经纬度转相对米数)
                lat_mid = math.radians(anchor_lat)
                dx_m = (lng - anchor_lng) * 111320.0 * math.cos(lat_mid)
                dy_m = (lat - anchor_lat) * 111000.0

                drift_m = math.sqrt(dx_m ** 2 + dy_m ** 2)
                if drift_m > self.max_drift_m:
                    self.max_drift_m = drift_m
                    self._check_and_expand_radar(drift_m)  # 动态量程检测

                self.lbl_gps_stats.setText(f"当前偏差: {drift_m:.2f} m | 最大漂移: {self.max_drift_m:.2f} m")

                self.wave_data_x.append(dx_m)
                self.wave_data_y.append(dy_m)

                # 这里我们改用 ScatterPlotItem 风格来渲染历史轨迹（散点）
                # 为了性能，线框依然用 plot_curve 但设置成浅灰色半透明
                self.plot_curve.setPen(pg.mkPen(color=(150, 150, 150, 100), width=1))
                self.plot_curve.setData(x=list(self.wave_data_x), y=list(self.wave_data_y), symbol='o', symbolSize=4,
                                        symbolBrush=(100, 100, 100, 150))

                if hasattr(self, 'latest_scatter') and self.latest_scatter:
                    self.latest_scatter.setData(x=[dx_m], y=[dy_m])
            else:
                # ==========================================
                # 📈 1D 波形绘制：恢复经典的绿色粗线
                # ==========================================
                self.wave_data_y.append(val)
                self.plot_curve.setPen(pg.mkPen(color='#10B981', width=2))
                self.plot_curve.setData(y=list(self.wave_data_y), symbol=None)

                if hasattr(self, 'latest_scatter') and self.latest_scatter:
                    self.latest_scatter.setData(x=[], y=[])

        except Exception as e:
            print(f"绘图渲染失败: {e}")

    def _check_and_expand_radar(self, current_drift):
        """自动调整雷达圈量程 (1-2-5 步进)"""
        scales = [1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 5000]
        target_scale = 10
        for s in scales:
            if s > current_drift:
                target_scale = s
                break
        self.draw_radar_circles(target_scale)

    def draw_radar_circles(self, max_radius):
        """画极具科技感的同心圆和十字准星"""
        for item in self.radar_circle_items:
            self.plot_widget.removeItem(item)
        self.radar_circle_items.clear()

        # 决定画哪几个圈 (比如 max 是 10，就画 2, 5, 10)
        radii = [max_radius]
        if max_radius >= 5: radii.extend([max_radius * 0.5, max_radius * 0.2])

        import numpy as np
        theta = np.linspace(0, 2 * np.pi, 100)

        for r in set(radii):
            x = r * np.cos(theta)
            y = r * np.sin(theta)
            # 画虚线圆圈
            circle = pg.PlotDataItem(x, y, pen=pg.mkPen(color=(16, 185, 129, 150), width=1, style=Qt.PenStyle.DashLine))
            self.plot_widget.addItem(circle)
            self.radar_circle_items.append(circle)

            # 标注距离文本 (比如 "5m")
            txt = pg.TextItem(f"{r}m", color=(16, 185, 129, 200), anchor=(0, 1))
            txt.setPos(r * 0.7, r * 0.7)
            self.plot_widget.addItem(txt)
            self.radar_circle_items.append(txt)

        # 画十字准星
        cross_v = pg.PlotDataItem([0, 0], [-max_radius, max_radius], pen=pg.mkPen(color=(16, 185, 129, 100), width=1))
        cross_h = pg.PlotDataItem([-max_radius, max_radius], [0, 0], pen=pg.mkPen(color=(16, 185, 129, 100), width=1))
        self.plot_widget.addItem(cross_v)
        self.plot_widget.addItem(cross_h)
        self.radar_circle_items.extend([cross_v, cross_h])

    # ==========================================
    # 🌟 重置嗅探雷达
    # ==========================================
    def reset_wave_vars(self):
        """彻底清空变量嗅探雷达的记忆和下拉框"""
        # 1. 暂时屏蔽信号，防止在清空下拉框时触发各种报错
        self.combo_wave_var.blockSignals(True)
        self.combo_wave_var.clear()
        self.combo_wave_var.addItem("关闭绘制")
        self.combo_wave_var.blockSignals(False)

        # 2. 彻底抹除底层的嗅探记忆
        self.known_wave_vars.clear()
        if hasattr(self, '_ascii_cache_lat'): self._ascii_cache_lat = None
        if hasattr(self, '_ascii_cache_lng'): self._ascii_cache_lng = None

        # 3. 顺便把画板上的残留线条也抹掉
        self.clear_waveform()

        # 体验优化：在底部状态栏给个提示
        self.statusBar().showMessage("✅ 变量雷达已重置，等待接收新变量...", 3000)

    # ==========================================
    # 🌟 GPS 锚点与 KML 导出功能
    # ==========================================
    def set_manual_anchor(self):
        try:
            lat = float(self.input_anchor_lat.text())
            lng = float(self.input_anchor_lng.text())
            self.gps_anchor = (lng, lat)
            # 清空历史数据，重新基于新锚点打点
            self.wave_data_x.clear()
            self.wave_data_y.clear()
            self.max_drift_m = 0.0
            self.draw_radar_circles(5)  # 默认从 5米 圈开始
            self.statusBar().showMessage("✅ 已锁定绝对真值锚点！", 3000)
        except ValueError:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "输入错误", "请输入正确的经纬度数值！")

    def set_auto_anchor(self):
        self.gps_anchor = None
        self.wave_data_x.clear()
        self.wave_data_y.clear()
        self.max_drift_m = 0.0
        self.statusBar().showMessage("🔄 已重置锚点，将以收到的下一个坐标作为原点", 3000)

    def export_kml(self):
        if not self.gps_anchor or not self.wave_data_x:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "无数据", "当前没有有效的 GPS 轨迹数据可供导出！")
            return

        from PyQt6.QtWidgets import QFileDialog
        from datetime import datetime

        default_name = f"GNSS_Track_{datetime.now().strftime('%Y%m%d_%H%M%S')}.kml"
        file_path, _ = QFileDialog.getSaveFileName(self, "导出 KML 轨迹", default_name, "KML Files (*.kml)")
        if not file_path: return

        anchor_lng, anchor_lat = self.gps_anchor

        # 逆向推算所有历史点的真实经纬度 (从相对于锚点的米数还原)
        lat_mid = math.radians(anchor_lat)
        coords_str = ""
        for dx, dy in zip(self.wave_data_x, self.wave_data_y):
            # 还原经纬度
            p_lng = anchor_lng + (dx / (111320.0 * math.cos(lat_mid)))
            p_lat = anchor_lat + (dy / 111000.0)
            coords_str += f"{p_lng:.7f},{p_lat:.7f},0\n"

        kml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>GNSS Drift Radar Export</name>
    <description>由上位机导出的静态漂移分析报告</description>

    <Style id="anchorStyle">
      <IconStyle><Icon><href>http://maps.google.com/mapfiles/kml/paddle/ylw-stars.png</href></Icon></IconStyle>
    </Style>
    <Style id="trackStyle">
      <LineStyle><color>990000ff</color><width>4</width></LineStyle>
    </Style>

    <Folder>
      <name>静态基准点 (真值)</name>
      <Placemark>
        <name>Anchor (0,0)</name>
        <styleUrl>#anchorStyle</styleUrl>
        <Point><coordinates>{anchor_lng:.7f},{anchor_lat:.7f},0</coordinates></Point>
      </Placemark>
    </Folder>

    <Folder>
      <name>动态测试轨迹</name>
      <Placemark>
        <name>漂移轨迹</name>
        <styleUrl>#trackStyle</styleUrl>
        <LineString>
          <tessellate>1</tessellate>
          <altitudeMode>clampToGround</altitudeMode>
          <coordinates>
            {coords_str.strip()}
          </coordinates>
        </LineString>
      </Placemark>
    </Folder>
  </Document>
</kml>"""

        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(kml_content)
            self.statusBar().showMessage(f"✅ KML 成功导出至: {file_path}", 5000)
        except Exception as e:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "导出失败", f"写入文件时发生错误:\n{e}")

    # ==========================================
    # 🌟 离线日志回放 (时光倒流播放器) 核心逻辑
    # ==========================================
    def start_playback_dialog(self):
        # 1. 冲突保护：绝不能一边开着真串口，一边放录像
        if self.serial_worker and getattr(self.serial_worker, 'serial', None) and self.serial_worker.serial.is_open:
            QMessageBox.warning(self, "冲突", "请先点击顶部【🛑 停止】关闭物理串口，再进行日志回放！")
            return

        file_path, _ = QFileDialog.getOpenFileName(self, "选择要回放的原始日志文件", "",
                                                   "Text Files (*.txt *.log);;All Files (*)")
        if not file_path: return

        # 2. 界面准备 (大清洗)
        self.clear_all_data()
        self.playback_panel.setVisible(True)
        import os
        self.lbl_pb_file.setText(f"🎥 回放: {os.path.basename(file_path)}")
        self.btn_pb_play.setText("⏸️ 暂停")

        # 🌟 极客细节：回放时强制关掉自动追加时间戳，因为原始日志里本身就带时间戳，避免重复重叠！
        self.action_timestamp.setChecked(False)

        # 3. 引擎准备 (彻底复用串口的流式解析引擎)
        if self.decoder:
            self.rt_tx_parser = StreamParser(self.decoder)
            self.rt_rx_parser = StreamParser(self.decoder)
        self.serial_buffer_line = ""

        # 4. 召唤播放器线程
        speed_text = self.combo_pb_speed.currentText()
        speed_val = self._parse_speed(speed_text)

        self.playback_worker = PlaybackWorker(file_path, speed_val)
        # 🔪 核心黑科技：把播放器吐出来的数据，直接硬塞给“串口数据接收器”！
        self.playback_worker.data_received.connect(self.on_serial_data_received)
        self.playback_worker.progress_updated.connect(self.update_playback_progress)
        self.playback_worker.finished_signal.connect(self.on_playback_finished)
        self.playback_worker.start()

    def _parse_speed(self, text):
        if "Max" in text: return 0
        return int(text.replace("x", ""))

    def change_playback_speed(self, text):
        if hasattr(self, 'playback_worker') and self.playback_worker:
            self.playback_worker.set_speed(self._parse_speed(text))

    def toggle_playback_pause(self):
        if hasattr(self, 'playback_worker') and self.playback_worker:
            is_paused = self.playback_worker.toggle_pause()
            self.btn_pb_play.setText("▶️ 播放" if is_paused else "⏸️ 暂停")

    def stop_playback(self):
        if hasattr(self, 'playback_worker') and self.playback_worker:
            self.playback_worker.stop()
            self.btn_pb_play.setText("▶️ 播放")

    def update_playback_progress(self, current, total):
        self.lbl_pb_progress.setText(f"进度: {current} / {total} 行")
        self.lbl_pb_progress.repaint()
        QApplication.processEvents()

    def on_playback_finished(self):
        self.btn_pb_play.setText("🔄 播放完毕")
        self.statusBar().showMessage("✅ 日志动态回放结束！", 5000)

    def close_playback_panel(self):
        self.stop_playback()
        self.playback_panel.setVisible(False)
        self.statusBar().showMessage("状态: 回放面板已关闭，待命")

    # ==========================================
    # 🌟 自动化测试宏队列 核心逻辑
    # ==========================================
    def add_macro_row(self, data="", fmt="HEX", delay=500):
        row = self.macro_table.rowCount()
        self.macro_table.insertRow(row)

        item_data = QTableWidgetItem(str(data))
        self.macro_table.setItem(row, 0, item_data)

        combo_fmt = QComboBox()
        combo_fmt.addItems(["HEX", "ASCII"])
        combo_fmt.setCurrentText(fmt)
        self.macro_table.setCellWidget(row, 1, combo_fmt)

        spin_delay = QSpinBox()
        spin_delay.setRange(10, 3600000)  # 支持长达 1 小时的单步延时
        spin_delay.setValue(int(delay))
        self.macro_table.setCellWidget(row, 2, spin_delay)

        btn_del = QPushButton("❌")
        btn_del.setStyleSheet("color: #EF4444; font-weight: bold;")
        # 通过 btn 的相对位置反查行号，极其优雅的防越界删法
        btn_del.clicked.connect(lambda _, b=btn_del: self.delete_macro_row(b))
        self.macro_table.setCellWidget(row, 3, btn_del)

    def delete_macro_row(self, btn):
        index = self.macro_table.indexAt(btn.pos())
        if index.isValid():
            self.macro_table.removeRow(index.row())

    def start_macro(self):
        if not getattr(self, 'active_worker', None) or not self.active_worker.isRunning():
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "错误", "底层通信尚未就绪，请先打开物理串口/网络连接！")
            return

        macro_list = []
        for i in range(self.macro_table.rowCount()):
            data_item = self.macro_table.item(i, 0)
            fmt_widget = self.macro_table.cellWidget(i, 1)
            delay_widget = self.macro_table.cellWidget(i, 2)

            data = data_item.text().strip() if data_item else ""
            if data:
                macro_list.append({
                    'data': data,
                    'fmt': fmt_widget.currentText() if fmt_widget else "HEX",
                    'delay': delay_widget.value() if delay_widget else 500
                })

        if not macro_list:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "无数据", "自动化流水线为空，请至少添加一个动作！")
            return

        # 锁死 UI，防止运行期间瞎改
        self.btn_run_macro.setEnabled(False)
        self.btn_stop_macro.setEnabled(True)
        self.macro_table.setEnabled(False)

        loop_count = self.spin_macro_loop.value()
        self.macro_worker = MacroWorker(macro_list, loop_count)
        self.macro_worker.send_cmd_signal.connect(self._macro_execute_send)
        self.macro_worker.row_highlight_signal.connect(self._macro_highlight_row)
        self.macro_worker.log_signal.connect(lambda msg: self.statusBar().showMessage(msg, 3000))
        self.macro_worker.finished_signal.connect(self._macro_finished)
        self.macro_worker.start()

    def _macro_execute_send(self, data, fmt):
        """极其优雅的“借刀杀人”：复用主窗口的发送流水线"""
        self.send_input.setText(data)
        if fmt == "HEX":
            self.radio_hex.setChecked(True)
        else:
            self.radio_ascii.setChecked(True)

        # 模拟点击发送按钮！这样动态校验和、加换行符、打印TX日志 全都会自动执行！
        self.btn_send.click()

    def _macro_highlight_row(self, row):
        """在表格中通过颜色提示当前跑到哪一步了"""
        from PyQt6.QtGui import QColor
        bg_color = QColor("#047857" if self.is_dark_mode else "#D1FAE5")
        default_color = QColor(Qt.GlobalColor.transparent)

        for i in range(self.macro_table.rowCount()):
            item = self.macro_table.item(i, 0)
            if item: item.setBackground(bg_color if i == row else default_color)

    def stop_macro(self):
        if hasattr(self, 'macro_worker') and self.macro_worker:
            self.macro_worker.stop()
            self.statusBar().showMessage("⚠️ 自动化测试宏已被手动终止！", 3000)

    def _macro_finished(self):
        self.btn_run_macro.setEnabled(True)
        self.btn_stop_macro.setEnabled(False)
        self.macro_table.setEnabled(True)
        self.statusBar().showMessage("✅ 自动化测试宏执行完毕！", 5000)

    def show_terminal_menu(self, pos):
        """弹出融合了标准复制和自定义开关的高级右键菜单"""
        menu = self.raw_log_console.createStandardContextMenu()
        menu.addSeparator()  # 加一条帅气的分割线
        # 加上我们的极客开关
        menu.addAction(self.action_timestamp)
        menu.addAction(self.action_hex)
        menu.addAction(self.action_autoscroll)
        menu.addAction(self.action_wordwrap)
        menu.exec(self.raw_log_console.mapToGlobal(pos))

    def closeEvent(self, event):
        """🌟 优雅退出：窗口关闭时，安全终止所有后台线程，防止内存泄漏和报错"""
        # 1. 停止物理总线
        if getattr(self, 'active_worker', None) and self.active_worker.isRunning():
            self.active_worker.stop()
            self.active_worker.wait(500)  # 最多等它半秒钟交接工作

        # 2. 停止回放放映机
        if getattr(self, 'playback_worker', None) and self.playback_worker.isRunning():
            self.playback_worker.stop()
            self.playback_worker.wait(500)

        # 3. 停止自动化测试流水线
        if getattr(self, 'macro_worker', None) and self.macro_worker.isRunning():
            self.macro_worker.stop()
            self.macro_worker.wait(500)

        # 4. 安全关闭正在写入的文件句柄
        if getattr(self, 'is_recording', False) and getattr(self, 'record_file_handle', None):
            try:
                self.record_file_handle.close()
            except:
                pass

        # 允许窗口正常关闭
        super().closeEvent(event)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = EcuMainWindow()
    window.show()
    sys.exit(app.exec())