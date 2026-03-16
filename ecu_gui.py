import sys
import os
import json
import struct
import re
import binascii
import csv

# 🚀 优化 2：统一在顶部引入所有需要的时间库，避免函数内重复 import 造成性能损耗
from datetime import datetime, timezone, timedelta

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QPushButton, QFileDialog, QTableView, QTreeView, QComboBox,
                             QLabel, QProgressBar, QSplitter, QMessageBox, QHeaderView, QAbstractItemView, QLineEdit,
                             )
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QAbstractTableModel
from PyQt6.QtGui import QStandardItemModel, QStandardItem, QFont


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
                # 🚀 修复时区问题：在 UTC 时间基础上加上 8 小时 (北京时间)
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

    # 🚀 优化 1 核心：抽离统一的值处理函数（缩放、偏移、映射、单位追加）
    def _process_value(self, val, field_info):
        if isinstance(val, (int, float)):
            if 'scale' in field_info:
                val = val * field_info['scale']
                scale = field_info['scale']
                # 浮点数精度修正
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

            # 数字类型的字典映射
            if 'mapping' in field_info:
                val = field_info['mapping'].get(str(int(val)), val)

        # 字符串类型的字典映射 (兼容 "crc error" 等)
        elif isinstance(val, str) and 'mapping' in field_info:
            val = field_info['mapping'].get(val.strip(), val)

        # 追加单位
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
                # 🚀 优化 2：直接使用顶部导入的 timezone 和 timedelta，更快速
                dt = datetime.fromtimestamp(seconds, timezone.utc) + timedelta(hours=8)
                val = dt.strftime('%Y-%m-%d %H:%M:%S')
            except Exception:
                val = str(seconds)

        elif f_type == 'MZ_LATLNG':
            val = round(struct.unpack('>I', chunk)[0] / 1800000.0, 6)

        elif f_type == 'ASCII_STR':
            try:
                val = chunk.decode('ascii', errors='ignore').strip('\x00')
            except:
                val = str(chunk)

        elif f_type.startswith('BITFIELD_'):
            fmt, width = {
                'BITFIELD_U4': ('>I', 32),
                'BITFIELD_U2': ('>H', 16)
            }.get(f_type, ('>B', 8))

            int_val = struct.unpack(fmt, chunk)[0]
            mapping = field_info.get('mapping', self.common_mappings.get(field_info.get('mapping_ref'), {}))
            val = self.parse_bitfield(int_val, mapping, width)

        # 时间字段特殊格式化
        if isinstance(val, (int, float)) and 'BITFIELD' not in f_type and 'segments' not in field_info:
            if 'time' in field_info.get('name', '').lower() and field_info.get('unit') is None:
                val = self.format_time(val)

        return val

    def decode_body(self, msg_type_hex, body_bytes):
        msg_def = self.msgs.get(msg_type_hex)
        if not msg_def:
            return {"raw_body": binascii.hexlify(body_bytes).decode('ascii'), "_note": "未定义的消息类型"}
        result = {}
        cursor = 0
        try:
            # 内部闭包函数：统一处理块长度计算与数据截取
            def get_chunk(f_def, current_cursor):
                ft = f_def['type']
                length = {
                    'U1': 1, 'BITFIELD_U1': 1, 'I1': 1,
                    'U2': 2, 'I2': 2, 'BITFIELD_U2': 2,
                    'U4': 4, 'I4': 4, 'BITFIELD_U4': 4, 'TIMESTAMP_BJ': 4, 'MZ_LATLNG': 4
                }.get(ft, f_def.get('length', 1))

                if length == -1:
                    length = len(body_bytes) - current_cursor
                if current_cursor + length > len(body_bytes):
                    return None, length
                return body_bytes[current_cursor: current_cursor + length], length

            # 1. 解析主干字段
            for field in msg_def['fields']:
                chunk, length = get_chunk(field, cursor)
                if chunk is None:
                    result[field['name']] = "<Truncated>"
                    break

                val = self.read_field(field['type'], chunk, field)

                # 位域拆分 (Segments) 逻辑
                if 'segments' in field and isinstance(val, int):
                    for seg in field['segments']:
                        seg_val = (val & seg.get('mask', 0xFF)) >> seg.get('shift', 0)
                        # 🚀 优化 1：复用提取的值处理逻辑
                        result[seg['name']] = self._process_value(seg_val, seg)
                else:
                    # 🚀 优化 1：主字段复用值处理逻辑
                    result[field['name']] = self._process_value(val, field)
                cursor += length

            # 2. 解析循环体结构 (is_loop)
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

            # 3. 解析尾部字段 (tail_fields)
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
# 流解析器 (集成全新的“智能清洗预处理器”)
# ==========================================
# ==========================================
# 流解析器 (集成全新的“智能清洗预处理器”及服务器日志兼容)
# ==========================================
# ==========================================
# 流解析器 (集成全新的“智能清洗预处理器”及服务器日志兼容)
# ==========================================
# ==========================================
# 流解析器 (全天候防弹版：彻底杜绝日志干扰)
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
            if not line:
                continue

            # ====================================================
            # 🛡️ 强制黑名单：拦截蓝牙、本地控制器串口
            # ====================================================
            line_lower = line.lower()
            if "ble send" in line_lower or "ble recv" in line_lower or "ctrl send" in line_lower or "ctrl_recv" in line_lower:
                continue

            # ====================================================
            # 策略 1: 精准提取终端串口的 HexDump (EasyLogger 格式)
            # ====================================================
            match = re.search(r'(?:[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}:|[0-9A-Fa-f]{8}:)\s*(.*)', line)
            if match:
                payload = match.group(1)
                hex_part = re.split(r'\s{3,}', payload)[0]
                pure_hex = re.sub(r'[^0-9a-fA-F]', '', hex_part)
                if len(pure_hex) % 2 != 0:
                    pure_hex = pure_hex[:-1]
                if pure_hex:
                    try:
                        self.buffer.extend(bytes.fromhex(pure_hex))
                    except:
                        pass
                continue

            # ====================================================
            # 策略 2: 精准提取服务器导出的纯净日志 (长连续十六进制)
            # ====================================================
            found_server_log = False
            for word in line.split():
                word_clean = re.sub(r'[^0-9a-fA-F]', '', word)
                # 只有连续十六进制超过16位且包含包头，才认定为报文
                if word_clean.lower().startswith(sync_hex) and len(word_clean) >= self.header_size * 2:
                    if len(word_clean) % 2 != 0:
                        word_clean = word_clean[:-1]
                    try:
                        self.buffer.extend(bytes.fromhex(word_clean))
                        found_server_log = True
                    except:
                        pass
            if found_server_log:
                continue

            # ====================================================
            # 策略 3: 绝对屏蔽脏日志 (修复 4244 时间戳乱入 Bug)
            # ====================================================
            # 走到这里的行，如果它是以 D/PWR, I/nbio, V/CONFIG 这种格式开头
            # 说明它全是文字打印，即使里面有 [10:42:44]，也100%直接销毁！
            if re.match(r'^[A-Z]/[A-Za-z0-9_]+', line):
                continue

            # ====================================================
            # 策略 4: 手动粘贴兜底 (纯报文带空格粘贴)
            # ====================================================
            spaced_text = re.sub(r'[^0-9a-fA-F]', ' ', line)
            chunks = spaced_text.split()

            for chunk in chunks:
                if len(chunk) % 2 != 0:
                    chunk = chunk[:-1]
                if chunk:
                    try:
                        self.buffer.extend(bytes.fromhex(chunk))
                    except:
                        pass

        # === 核心切帧逻辑 ===
        frames = []
        while True:
            head_idx = self.buffer.find(self.SYNC_HEADER)
            if head_idx == -1:
                keep = len(self.SYNC_HEADER) - 1 if len(self.buffer) > 0 else 0
                self.buffer = self.buffer[-keep:]
                break
            if head_idx > 0:
                self.buffer = self.buffer[head_idx:]

            if len(self.buffer) < self.header_size:
                break

            if getattr(self, 'len_size', 2) == 1:
                body_len = self.buffer[self.len_offset]
            else:
                body_len = struct.unpack('>H', self.buffer[self.len_offset: self.len_offset + 2])[0]

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
        if self.msg_type_offset >= len(data):
            return None
        msg_type = data[self.msg_type_offset]
        msg_type_hex = f"0x{msg_type:02X}"

        if self.header_size == 8:
            seq = struct.unpack('>H', data[3:5])[0]
        elif self.header_size == 10:
            seq = data[6]
        else:
            seq = "N/A"

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
                # 为了支持跨行的预处理缓冲，在读文件时使用大块读取更稳妥
                # 但由于 feed 内部按行进行了强力拆分，逐行喂入同样可行且不会干扰 HexDump 解析
                for line in f:
                    frames = parser.feed(line)
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
                summary = []

                # 1. 提取通用告警 (如 0x51 报文)
                if 'alarm_bits' in f_data:
                    active_alarms = []
                    for alarm_name, is_active in f_data['alarm_bits'].items():
                        if is_active == 1:
                            active_alarms.append(alarm_name)
                    if active_alarms:
                        summary.append(f"🚨告警: {'/'.join(active_alarms)}")

                # ====================================================
                # 2. 针对 0x5C (控制器消息) 屏蔽电压，提取故障明细
                # ====================================================
                if frame['type'] == '0x5C':
                    faults = []
                    fault_keys = ["Bit0_堵转", "Bit1_转把", "Bit2_欠压", "Bit3_过压", "Bit4_刹车", "Bit5_霍尔"]
                    for fk in fault_keys:
                        val = f_data.get(fk)
                        if val and val not in ("正常", 0, "0"):
                            faults.append(str(val))

                    if faults:
                        summary.append(f"🛠️故障: {'/'.join(faults)}")
                    else:
                        summary.append("✅无故障")

                # ====================================================
                # 🌟 新增：针对 0x08 (平台通用应答) 显示对应指令名和执行结果
                # ====================================================
                elif frame['type'] == '0x08':
                    # 提取应答的指令 HEX 字符串 (例如 "2b")
                    ack_type = f_data.get('ack_msg_type')
                    if ack_type:
                        # 格式化为 "0x2B" 去字典里反查中文名
                        ack_type_hex = f"0x{str(ack_type).upper()}"
                        ack_name = self.get_msg_name(ack_type_hex)
                        summary.append(f"应答: {ack_name} ({ack_type_hex})")

                    # 提取执行结果错误码
                    err_code = f_data.get('error_code')
                    if err_code:
                        if "操作成功" not in str(err_code):
                            summary.append(f"❌ [{err_code}]")
                        else:
                            summary.append("✅ 成功")

                # 3. 其他常规消息依然显示外接电压
                else:
                    if 'voltage' in f_data:
                        summary.append(f"V:{f_data['voltage']}")

                # 4. 其他特殊信息的摘要 (GPS 定位点数、BMS 健康度等)
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
        self.setWindowTitle("多协议解析全能工作站 (GUI版)")
        self.resize(1000, 700)

        self.all_frames = []
        self.filtered_frames = []
        self.decoder = None

        self.init_ui()

    def init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)

        self.quick_parse_layout = QHBoxLayout()
        self.quick_parse_input = QLineEdit()
        self.quick_parse_input.setPlaceholderText("可直接粘贴包含了乱码、行号的嵌入式原始日志，系统将智能提取 Hex 数据！")
        self.quick_parse_input.setClearButtonEnabled(True)

        self.quick_parse_btn = QPushButton("🚀 快速解析")
        self.quick_parse_btn.setFixedWidth(100)

        self.quick_parse_layout.addWidget(self.quick_parse_input)
        self.quick_parse_layout.addWidget(self.quick_parse_btn)

        main_layout.addLayout(self.quick_parse_layout)

        self.quick_parse_btn.clicked.connect(self.on_quick_parse_clicked)
        self.quick_parse_input.returnPressed.connect(self.on_quick_parse_clicked)

        control_layout = QHBoxLayout()
        self.combo_protocol = QComboBox()
        self.populate_protocols()
        self.combo_protocol.currentIndexChanged.connect(self.change_protocol)

        control_layout.addWidget(QLabel("📜 协议格式:"))
        control_layout.addWidget(self.combo_protocol)

        self.btn_load = QPushButton("📂 打开日志文件 (.txt/.log)")
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

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        main_layout.addWidget(self.progress_bar)

        splitter = QSplitter(Qt.Orientation.Vertical)

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

        self.tree_view = QTreeView()
        self.tree_model = QStandardItemModel()
        self.tree_model.setHorizontalHeaderLabels(["字段结构解析详情"])
        self.tree_view.setModel(self.tree_model)
        self.tree_view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        splitter.addWidget(self.tree_view)

        splitter.setSizes([400, 300])
        main_layout.addWidget(splitter)

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

            for frame in parsed_frames:
                msg_def = self.decoder.msgs.get(frame['type'], {})
                frame['name'] = msg_def.get('name', '未知消息')
                frame['seq'] = "手动"
                self.all_frames.append(frame)

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

            self.apply_filter()

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
        self.progress_bar.setMaximum(0)
        self.lbl_status.setText("正在智能清洗和解析日志中...")

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
        self.lbl_status.setText(f"解析完成！共提取 {total_count} 条有效指令。")
        self.btn_export.setEnabled(True)

        for frame in self.all_frames:
            msg_def = self.decoder.msgs.get(frame['type'], {})
            frame['name'] = msg_def.get('name', '未知消息')

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