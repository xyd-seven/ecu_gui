import sys
import os
import json
import struct
import re
import binascii
import csv

from datetime import datetime

# 导入 PyQt6 核心组件
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QPushButton, QFileDialog, QTableView, QTreeView, QComboBox,
                             QLabel, QProgressBar, QSplitter, QMessageBox, QHeaderView, QAbstractItemView, QLineEdit,
                             )
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QAbstractTableModel
from PyQt6.QtGui import QStandardItemModel, QStandardItem, QFont


# ==========================================
# 核心业务层 (Model): 解析引擎 (完全继承之前的逻辑)
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
                dt = datetime.utcfromtimestamp(timestamp)
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
                result[desc] = int(is_set)  # 0或1
            except:
                continue
        return result

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

        # ====== 新增：支持将任意长度的十六进制转换为十进制显示 ======
        elif f_type == 'HEX2DEC':
            hex_str = binascii.hexlify(chunk).decode('ascii')
            # 转换为十进制后，将其转为字符串格式，防止 UI 显示科学计数法
            val = str(int(hex_str, 16))

        # ====== 新增：UTC 绝对秒转北京时间字符串 ======
        elif f_type == 'TIMESTAMP_BJ':
            import datetime as dt_mod  # 【核心修复】：使用别名导入，绝对不干扰全局的 struct 和 datetime！
            # 1. 先按 4 字节无符号整数解包出秒数
            seconds = struct.unpack('>I', chunk)[0]
            try:
                # 2. 从 UTC 时间戳加上 8 小时偏移量，格式化为易读的字符串
                dt = dt_mod.datetime.fromtimestamp(seconds, dt_mod.timezone.utc) + dt_mod.timedelta(hours=8)
                val = dt.strftime('%Y-%m-%d %H:%M:%S')
            except Exception:
                val = str(seconds)  # 万一转换失败，兜底显示原始数字

        # ====== 喵走协议专属：经纬度算法 ======
        elif f_type == 'MZ_LATLNG':
            raw_val = struct.unpack('>I', chunk)[0]
            # 公式：Value = (度*60 + 分) * 30000 => Decimal = Value / 30000 / 60
            val = round(raw_val / 1800000.0, 6)

        # ====== 喵走协议专属：不定长 ASCII 字符串 ======
        elif f_type == 'ASCII_STR':
            try:
                # 过滤掉末尾可能的空字符
                val = chunk.decode('ascii', errors='ignore').strip('\x00')
            except Exception:
                val = str(chunk)

        # 【支持 BITFIELD_U2】
        elif f_type.startswith('BITFIELD_'):
            if f_type == 'BITFIELD_U4':
                fmt, width = '>I', 32
            elif f_type == 'BITFIELD_U2':
                fmt, width = '>H', 16
            else:  # BITFIELD_U1
                fmt, width = '>B', 8

            int_val = struct.unpack(fmt, chunk)[0]
            mapping = field_info.get('mapping')
            if mapping is None and 'mapping_ref' in field_info:
                mapping = self.common_mappings.get(field_info['mapping_ref'], {})
            val = self.parse_bitfield(int_val, mapping or {}, width)

        if isinstance(val, (int, float)) and 'BITFIELD' not in f_type and 'segments' not in field_info:
            if 'time' in field_info.get('name', '').lower() and field_info.get('unit') is None:
                val = self.format_time(val)
            else:
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
                        # 新增兜底：其他所有比例（包含 0.00001 等）最多只保留 6 位小数
                        val = round(val, 6)
                if 'offset' in field_info: val = val + field_info['offset']
                if 'unit' in field_info: val = f"{val}{field_info['unit']}"
        return val

    def decode_body(self, msg_type_hex, body_bytes):
        msg_def = self.msgs.get(msg_type_hex)
        if not msg_def:
            return {"raw_body": binascii.hexlify(body_bytes).decode('ascii'), "_note": "未定义的消息类型"}
        result = {}
        cursor = 0
        try:
            for field in msg_def['fields']:
                f_name = field['name']
                f_type = field['type']
                length = 1
                if f_type in ['U1', 'BITFIELD_U1', 'I1']:
                    length = 1
                elif f_type in ['U2', 'I2', 'BITFIELD_U2']:
                    length = 2
                # ====== 修改：增加复合类型占 4 字节 ======
                elif f_type in ['U4', 'I4', 'BITFIELD_U4', 'TIMESTAMP_BJ', 'MZ_LATLNG']:
                    length = 4
                elif f_type in ['BCD', 'BYTES', 'HEX2DEC']:
                    length = field.get('length', 1)
                # ====== 喵走协议专属：不定长字符长度推断 ======
                elif f_type == 'ASCII_STR':
                    length = field.get('length', -1)
                    if length == -1:
                        length = len(body_bytes) - cursor  # 占满剩余所有长度

                if cursor + length > len(body_bytes):
                    result[f_name] = "<Truncated>"
                    break

                chunk = body_bytes[cursor: cursor + length]
                val = self.read_field(f_type, chunk, field)

                if 'segments' in field and isinstance(val, int):
                    for seg in field['segments']:
                        seg_name = seg['name']
                        mask = seg.get('mask', 0xFF)
                        shift = seg.get('shift', 0)
                        seg_val = (val & mask) >> shift

                        if 'scale' in seg:
                            seg_val = seg_val * seg['scale']
                            scale = seg['scale']
                            if abs(scale - 0.000001) < 1e-9:
                                seg_val = round(seg_val, 6)
                            elif abs(scale - 0.1) < 1e-9:
                                seg_val = round(seg_val, 1)
                            elif abs(scale - 0.01) < 1e-9:
                                seg_val = round(seg_val, 2)
                            else:
                                seg_val = round(seg_val, 6)  # 新增兜底
                        if 'offset' in seg: seg_val = seg_val + seg['offset']
                        if 'mapping' in seg: seg_val = seg['mapping'].get(str(int(seg_val)), seg_val)
                        if 'unit' in seg: seg_val = f"{seg_val}{seg['unit']}"
                        result[seg_name] = seg_val
                else:
                    result[f_name] = val
                cursor += length

            if msg_def.get('is_loop') and 'sub_struct' in msg_def:
                count_field = msg_def.get('loop_count_field')
                loop_count = 0
                if count_field and count_field in result:
                    try:
                        loop_count = int(result[count_field])
                    except:
                        pass
                item_list = []
                sub_fields = msg_def['sub_struct']
                for i in range(loop_count):
                    item = {}
                    for sub_f in sub_fields:
                        sf_name = sub_f['name']
                        sf_type = sub_f['type']
                        slen = 1
                        if sf_type in ['U1', 'BITFIELD_U1', 'I1']:
                            slen = 1
                        elif sf_type in ['U2', 'I2', 'BITFIELD_U2']:
                            slen = 2
                        elif sf_type in ['U4', 'I4', 'BITFIELD_U4', 'TIMESTAMP_BJ', 'MZ_LATLNG']:
                            slen = 4
                        elif sf_type in ['BCD', 'BYTES', 'HEX2DEC']:
                            slen = sub_f.get('length', 1)
                        elif sf_type == 'ASCII_STR':
                            slen = sub_f.get('length', -1)
                            if slen == -1: slen = len(body_bytes) - cursor

                        if cursor + slen > len(body_bytes): break
                        chunk = body_bytes[cursor: cursor + slen]
                        val = self.read_field(sf_type, chunk, sub_f)

                        if 'segments' in sub_f and isinstance(val, int):
                            for seg in sub_f['segments']:
                                seg_name = seg['name']
                                mask = seg.get('mask', 0xFF)
                                shift = seg.get('shift', 0)
                                seg_val = (val & mask) >> shift
                                if 'scale' in seg:
                                    seg_val = seg_val * seg['scale']
                                    scale = seg['scale']
                                    if abs(scale - 0.000001) < 1e-9:
                                        seg_val = round(seg_val, 6)
                                    elif abs(scale - 0.1) < 1e-9:
                                        seg_val = round(seg_val, 1)
                                    elif abs(scale - 0.01) < 1e-9:
                                        seg_val = round(seg_val, 2)
                                    else:
                                        seg_val = round(seg_val, 6)  # 新增兜底
                                if 'offset' in seg: seg_val = seg_val + seg['offset']
                                if 'mapping' in seg: seg_val = seg['mapping'].get(str(int(seg_val)), seg_val)
                                if 'unit' in seg: seg_val = f"{seg_val}{seg['unit']}"
                                item[seg_name] = seg_val
                        else:
                            item[sf_name] = val
                        cursor += slen
                    if item: item_list.append(item)
                result['point_list'] = item_list

            # ====== 尾部字段（如云煤网 0x09 结尾的 IMEI） ======
            if 'tail_fields' in msg_def:
                for tail_f in msg_def['tail_fields']:
                    t_type = tail_f.get('type')

                    # 动态计算尾部字段长度
                    if t_type in ['U1', 'I1', 'BITFIELD_U1']:
                        tlen = 1
                    elif t_type in ['U2', 'I2', 'BITFIELD_U2']:
                        tlen = 2
                    elif t_type in ['U4', 'I4', 'BITFIELD_U4', 'TIMESTAMP_BJ', 'MZ_LATLNG']:
                        tlen = 4
                    elif t_type in ['BCD', 'BYTES', 'HEX2DEC']:
                        tlen = tail_f.get('length', 1)
                    elif t_type == 'ASCII_STR':
                        tlen = tail_f.get('length', -1)
                        if tlen == -1: tlen = len(body_bytes) - cursor
                    else:
                        tlen = 1

                    # 安全读取并追加到外层的 result 字典中
                    if cursor + tlen <= len(body_bytes):
                        chunk = body_bytes[cursor: cursor + tlen]
                        val = self.read_field(t_type, chunk, tail_f)
                        result[tail_f['name']] = val
                        cursor += tlen
            # =========================================================================
        except Exception as e:
            result['_error'] = f"解析异常: {str(e)}"
        return result


class StreamParser:
    def __init__(self, decoder):
        self.decoder = decoder
        self.buffer = bytearray()
        self.SYNC_HEADER = bytes.fromhex(self.decoder.config.get('sync_header', '4244'))

        # ====== 动态读取包头配置，兼容多种协议 ======
        self.header_size = self.decoder.config.get('header_size', 8)
        self.len_offset = self.decoder.config.get('len_offset', 6)
        self.checksum_size = self.decoder.config.get('checksum_size', 2)

        # 兼容喵走：长度包含了整个包
        self.len_includes_all = self.decoder.config.get('len_includes_all', False)
        # 动态获取命令码偏移量 (喵走 AAAA 为 5，其他默认为 2)
        default_msg_offset = 5 if self.SYNC_HEADER.hex().upper() == 'AAAA' else 2
        self.msg_type_offset = self.decoder.config.get('msg_type_offset', default_msg_offset)

    def feed(self, raw_text):
        import re, struct
        spaced_text = re.sub(r'[^0-9a-fA-F]', ' ', raw_text)
        chunks = spaced_text.split()
        sync_hex = self.SYNC_HEADER.hex().lower()

        for chunk in chunks:
            # ====== 【核心修复】：移除严苛的长度限制，全面兼容带空格的 Hex 报文 ======
            if len(chunk) % 2 != 0:
                chunk = chunk[:-1]  # 保护机制：自动丢弃奇数位残片，绝不让底层半字节错位
            if not chunk:
                continue
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
            if head_idx > 0:
                self.buffer = self.buffer[head_idx:]

            # 动态判断包头是否完整
            if len(self.buffer) < self.header_size:
                break

            # 动态获取数据包体的长度
            body_len = struct.unpack('>H', self.buffer[self.len_offset: self.len_offset + 2])[0]

            # 兼容不同协议对“长度”的定义
            if self.len_includes_all:
                total_len = body_len
            else:
                total_len = self.header_size + body_len + self.checksum_size

            if len(self.buffer) < total_len:
                break

            frame_bytes = self.buffer[:total_len]
            parsed_frame = self.process_frame(frame_bytes)
            if parsed_frame:
                frames.append(parsed_frame)
            self.buffer = self.buffer[total_len:]

        return frames

    def process_frame(self, data):
        import struct

        # 防止越界
        if self.msg_type_offset >= len(data):
            return None

        msg_type = data[self.msg_type_offset]
        msg_type_hex = f"0x{msg_type:02X}"

        # 动态判断是否包含 seq (旧协议有2字节序号，喵走协议有1字节，其他占位)
        if self.header_size == 8:
            seq = struct.unpack('>H', data[3:5])[0]
        elif self.header_size == 10:
            seq = data[6]  # 喵走协议流水号
        else:
            seq = "N/A"

            # 根据动态 header_size 和 checksum_size 截取真正的 body
        if self.checksum_size > 0:
            body = data[self.header_size: -self.checksum_size]
        else:
            body = data[self.header_size:]

        decoded_data = self.decoder.decode_body(msg_type_hex, body)

        return {"type": msg_type_hex, "seq": seq, "data": decoded_data}


# ==========================================
# 线程层 (Controller): 防止大文件卡死界面
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
            parser = StreamParser(self.decoder)
            count = 0
            batch = []
            with open(self.filename, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    frames = parser.feed(line)
                    if frames:
                        batch.extend(frames)
                        count += len(frames)
                        # 每积累 200 条更新一次 UI，提升性能
                        if len(batch) >= 200:
                            self.batch_ready.emit(batch)
                            self.progress.emit(count)
                            batch = []
            # 发送剩余的帧
            if batch:
                self.batch_ready.emit(batch)
                self.progress.emit(count)
            self.finished.emit(count)
        except Exception as e:
            self.error.emit(str(e))


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
        self._data = new_data
        self.endResetModel()

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

            if col == 0: return str(frame['seq'])
            if col == 1: return str(f_data.get('time', 'N/A'))
            if col == 2: return frame['type']
            if col == 3: return self.get_msg_name(frame['type'])
            if col == 4:
                # 生成摘要：提取告警、电压、电量等直观信息
                summary = []

                if 'alarm_bits' in f_data:
                    active_alarms = []
                    for alarm_name, is_active in f_data['alarm_bits'].items():
                        if is_active == 1:
                            active_alarms.append(alarm_name)
                    if active_alarms:
                        summary.append(f"🚨告警: {'/'.join(active_alarms)}")

                if 'voltage' in f_data:
                    summary.append(f"V:{f_data['voltage']}")

                lat_val = f_data.get('lat', f_data.get('pt1_lat'))
                total_pts = 0
                if lat_val is not None:
                    total_pts = 1
                if 'point_list' in f_data:
                    total_pts += len(f_data['point_list'])

                if frame['type'] == '0x52':
                    summary.append(f"共包含 {total_pts} 个定位点")

                if 'health' in f_data:
                    summary.append(f"健康度:{f_data['health']}%")

                return ", ".join(summary) if summary else "无摘要"

    def get_msg_name(self, hex_type):
        return "详情见下"

    def get_raw_data(self, row):
        return self._data[row]


class EcuMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("多协议解析工具 (GUI版)")
        self.resize(1000, 700)

        self.all_frames = []
        self.filtered_frames = []
        self.decoder = None  # 先置空，稍后由 UI 触发加载

        self.init_ui()

    def init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)

        # --- 新增：顶部快速解析栏 ---
        self.quick_parse_layout = QHBoxLayout()

        self.quick_parse_input = QLineEdit()
        self.quick_parse_input.setPlaceholderText("在此粘贴单条或多条原始 Hex 报文 (例如: 42 44 51... 或 AAAA 01...)")
        self.quick_parse_input.setClearButtonEnabled(True)

        self.quick_parse_btn = QPushButton("🚀 快速解析")
        self.quick_parse_btn.setFixedWidth(100)

        self.quick_parse_layout.addWidget(self.quick_parse_input)
        self.quick_parse_layout.addWidget(self.quick_parse_btn)

        main_layout.addLayout(self.quick_parse_layout)

        # 绑定事件
        self.quick_parse_btn.clicked.connect(self.on_quick_parse_clicked)
        self.quick_parse_input.returnPressed.connect(self.on_quick_parse_clicked)
        # ---------------------------

        # 1. 顶部控制栏
        control_layout = QHBoxLayout()

        self.combo_protocol = QComboBox()
        self.populate_protocols()  # 扫描本地 json 文件
        self.combo_protocol.currentIndexChanged.connect(self.change_protocol)

        control_layout.addWidget(QLabel("📜 协议格式:"))
        control_layout.addWidget(self.combo_protocol)

        self.btn_load = QPushButton("📂 打开日志文件 (.txt)")
        self.btn_load.clicked.connect(self.load_file)

        self.combo_filter = QComboBox()
        self.combo_filter.addItem("显示所有类型", "ALL")
        self.combo_filter.currentIndexChanged.connect(self.apply_filter)

        self.btn_export = QPushButton("💾 导出当前表格为 CSV")
        self.btn_export.clicked.connect(self.export_csv)
        self.btn_export.setEnabled(False)

        self.lbl_status = QLabel("状态: 等待载入文件...")

        control_layout.addWidget(self.btn_load)
        control_layout.addWidget(QLabel("类型筛选:"))
        control_layout.addWidget(self.combo_filter)
        control_layout.addWidget(self.btn_export)
        control_layout.addStretch()
        control_layout.addWidget(self.lbl_status)

        main_layout.addLayout(control_layout)

        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        main_layout.addWidget(self.progress_bar)

        # 2. 上下分栏设计 (Splitter)
        splitter = QSplitter(Qt.Orientation.Vertical)

        # 上半部分：数据表格
        self.table_view = QTableView()
        self.table_model = FrameTableModel()
        self.table_model.get_msg_name = lambda t: self.decoder.msgs.get(t, {}).get('name',
                                                                                   '未知') if self.decoder else '未知'
        self.table_view.setModel(self.table_model)
        self.table_view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table_view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table_view.horizontalHeader().setStretchLastSection(True)
        self.table_view.clicked.connect(self.on_row_clicked)
        splitter.addWidget(self.table_view)

        # 下半部分：JSON 树状图
        self.tree_view = QTreeView()
        self.tree_model = QStandardItemModel()
        self.tree_model.setHorizontalHeaderLabels(["字段结构解析详情"])
        self.tree_view.setModel(self.tree_model)
        self.tree_view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        splitter.addWidget(self.tree_view)

        # 设置初始上下比例 6:4
        splitter.setSizes([400, 300])
        main_layout.addWidget(splitter)

        # ✅ 在所有 UI 控件都初始化完毕后，再触发一次协议加载
        self.change_protocol()

    def populate_protocols(self):
        json_files = [f for f in os.listdir('.') if f.endswith('.json')]

        if not json_files:
            QMessageBox.warning(self, "警告", "当前目录下没有找到任何 .json 协议文件！")
            return

        for jf in json_files:
            self.combo_protocol.addItem(jf, jf)

    def change_protocol(self):
        protocol_file = self.combo_protocol.currentData()
        if not protocol_file:
            return

        try:
            self.decoder = ProtocolDecoder(protocol_file)

            if hasattr(self, 'parser'):
                del self.parser

            self.all_frames.clear()
            self.filtered_frames.clear()
            self.table_model.update_data([])
            self.tree_model.removeRows(0, self.tree_model.rowCount())
            self.combo_filter.blockSignals(True)
            self.combo_filter.clear()
            self.combo_filter.addItem("显示所有类型", "ALL")
            self.combo_filter.blockSignals(False)

            self.lbl_status.setText(f"✅ 已切换协议为: {protocol_file}")

        except Exception as e:
            QMessageBox.critical(self, "协议加载失败", f"无法加载 {protocol_file}，请检查 JSON 格式！\n{str(e)}")

    def on_quick_parse_clicked(self):
        import traceback

        try:
            raw_text = self.quick_parse_input.text().strip()
            if not raw_text:
                return

            if self.decoder is None:
                QMessageBox.warning(self, "警告", "底层协议配置未加载！\n请检查左上角是否已选择 .json 协议文件。")
                return

            if not hasattr(self, 'parser') or getattr(self, 'parser') is None:
                self.parser = StreamParser(self.decoder)

            parsed_frames = self.parser.feed(raw_text)

            if not parsed_frames:
                QMessageBox.warning(self, "解析失败",
                                    "未能识别出有效的协议帧。\n请检查数据是否包含正确的包头及长度配置。")
                return

            # ====== 修复：将数据添加到内存，并同步更新全部过滤逻辑 ======
            for frame in parsed_frames:
                msg_def = self.decoder.msgs.get(frame['type'], {})
                frame['name'] = msg_def.get('name', '未知消息')
                frame['seq'] = "手动"  # 标记为手动快速解析
                self.all_frames.append(frame)

            # 更新下拉框选项
            current_filter = self.combo_filter.currentData()
            self.combo_filter.blockSignals(True)
            self.combo_filter.clear()
            self.combo_filter.addItem("显示所有类型", "ALL")
            types = set(f['type'] for f in self.all_frames)
            for t in sorted(types):
                name = self.decoder.msgs.get(t, {}).get('name', 'Unknown')
                self.combo_filter.addItem(f"{t} - {name}", t)
            idx = self.combo_filter.findData(current_filter)
            if idx >= 0:
                self.combo_filter.setCurrentIndex(idx)
            self.combo_filter.blockSignals(False)

            # 执行过滤并刷新表格模型
            self.apply_filter()

            # 滚动到底部并选中最新行
            last_row_index = len(self.filtered_frames) - 1
            if last_row_index >= 0:
                model_index = self.table_model.index(last_row_index, 0)
                self.table_view.scrollToBottom()
                self.table_view.setCurrentIndex(model_index)
                self.on_row_clicked(model_index)

            self.lbl_status.setText("⚡ 快速解析成功！已追加至列表。")
            self.quick_parse_input.clear()

        except Exception as e:
            error_msg = traceback.format_exc()
            QMessageBox.critical(self, "程序崩溃拦截", f"底层解析抛出异常：\n\n{error_msg}")

    def load_file(self):
        if self.decoder is None:
            QMessageBox.warning(self, "警告", "底层协议配置未加载！")
            return

        file_path, _ = QFileDialog.getOpenFileName(self, "选择日志文件", "", "Text Files (*.txt *.log);;All Files (*)")
        if not file_path:
            return

        self.all_frames.clear()
        self.filtered_frames.clear()
        self.table_model.update_data([])
        self.tree_model.removeRows(0, self.tree_model.rowCount())

        self.combo_filter.blockSignals(True)
        self.combo_filter.clear()
        self.combo_filter.addItem("显示所有类型", "ALL")
        self.combo_filter.blockSignals(False)

        self.btn_load.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(0)  # 跑马灯模式
        self.lbl_status.setText("正在极速解析中...")

        self.worker = ParseWorker(file_path, self.decoder)
        self.worker.batch_ready.connect(self.on_batch_ready)
        self.worker.progress.connect(self.on_progress)
        self.worker.finished.connect(self.on_parse_finished)
        self.worker.error.connect(self.on_parse_error)
        self.worker.start()

    def on_batch_ready(self, frames):
        self.all_frames.extend(frames)

    def on_progress(self, count):
        self.lbl_status.setText(f"已解析 {count} 条数据...")

    def on_parse_finished(self, total_count):
        self.btn_load.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.lbl_status.setText(f"解析完成！共 {total_count} 条有效帧。")
        self.btn_export.setEnabled(True)

        # 追加 name
        for frame in self.all_frames:
            msg_def = self.decoder.msgs.get(frame['type'], {})
            frame['name'] = msg_def.get('name', '未知消息')

        # 更新下拉框选项
        types = set(f['type'] for f in self.all_frames)
        self.combo_filter.blockSignals(True)
        for t in sorted(types):
            name = self.decoder.msgs.get(t, {}).get('name', 'Unknown')
            self.combo_filter.addItem(f"{t} - {name}", t)
        self.combo_filter.blockSignals(False)

        self.apply_filter()

    def on_parse_error(self, err_msg):
        self.btn_load.setEnabled(True)
        self.progress_bar.setVisible(False)
        QMessageBox.warning(self, "解析出错", err_msg)

    def apply_filter(self):
        if not self.all_frames: return
        target_type = self.combo_filter.currentData()

        if target_type == "ALL" or not target_type:
            self.filtered_frames = self.all_frames[:]
        else:
            self.filtered_frames = [f for f in self.all_frames if f['type'] == target_type]

        self.table_model.update_data(self.filtered_frames)
        self.lbl_status.setText(f"当前视图: {len(self.filtered_frames)} 条记录")
        self.tree_model.removeRows(0, self.tree_model.rowCount())

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

            if 'time' in keys:
                keys.remove('time')
                keys.insert(0, 'time')

            if 'pkg_count' in keys:
                rtk_fields = ["Bit00_03_RTK状态", "Bit04_超速指示", "Bit05_静态位置"]
                extracted = []
                for f in rtk_fields:
                    if f in keys:
                        keys.remove(f)
                        extracted.append(f)
                if extracted:
                    pkg_idx = keys.index('pkg_count')
                    for f in reversed(extracted):
                        keys.insert(pkg_idx, f)

            for key in keys:
                val = data_node[key]
                if isinstance(val, (dict, list)):
                    node = QStandardItem(str(key))
                    node.setForeground(Qt.GlobalColor.darkBlue)
                    parent_item.appendRow(node)
                    self._populate_tree(node, val)
                else:
                    item = QStandardItem(f"{key}: {val}")
                    parent_item.appendRow(item)

        elif isinstance(data_node, list):
            for i, item in enumerate(data_node):
                if isinstance(item, (dict, list)):
                    node = QStandardItem(f"[{i}]")
                    node.setForeground(Qt.GlobalColor.darkRed)
                    parent_item.appendRow(node)
                    self._populate_tree(node, item)
                else:
                    child = QStandardItem(f"[{i}]: {item}")
                    parent_item.appendRow(child)

    def export_csv(self):
        if not self.filtered_frames: return

        filename, _ = QFileDialog.getSaveFileName(self, "保存 CSV 文件",
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
            os.system(f"start {filename}")
        except Exception as e:
            QMessageBox.critical(self, "导出失败", str(e))


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = EcuMainWindow()
    window.show()
    sys.exit(app.exec())