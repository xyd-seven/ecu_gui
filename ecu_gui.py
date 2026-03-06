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
                # 【支持 BITFIELD_U2 长度计算】
                elif f_type in ['U2', 'I2', 'BITFIELD_U2']:
                    length = 2
                elif f_type in ['U4', 'I4', 'BITFIELD_U4']:
                    length = 4
                elif f_type in ['BCD', 'BYTES']:
                    length = field.get('length', 1)

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
                        # 内部循环体同样支持 U2
                        elif sf_type in ['U2', 'I2', 'BITFIELD_U2']:
                            slen = 2
                        elif sf_type in ['U4', 'I4', 'BITFIELD_U4']:
                            slen = 4

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
                                if 'offset' in seg: seg_val = seg_val + seg['offset']
                                if 'mapping' in seg: seg_val = seg['mapping'].get(str(int(seg_val)), seg_val)
                                if 'unit' in seg: seg_val = f"{seg_val}{seg['unit']}"
                                item[seg_name] = seg_val
                        else:
                            item[sf_name] = val
                        cursor += slen
                    if item: item_list.append(item)
                result['point_list'] = item_list
        except Exception as e:
            result['_error'] = f"解析异常: {str(e)}"
        return result


class StreamParser:
    def __init__(self, decoder):
        self.decoder = decoder
        self.buffer = bytearray()
        self.SYNC_HEADER = bytes.fromhex(self.decoder.config.get('sync_header', '4244'))

    def feed(self, raw_text):
        spaced_text = re.sub(r'[^0-9a-fA-F]', ' ', raw_text)
        chunks = spaced_text.split()
        for chunk in chunks:
            if len(chunk) >= 12 or '4244' in chunk.lower():
                if len(chunk) % 2 != 0: chunk = chunk[:-1]
                try:
                    self.buffer.extend(bytes.fromhex(chunk))
                except:
                    pass

        frames = []
        while True:
            head_idx = self.buffer.find(self.SYNC_HEADER)
            if head_idx == -1:
                keep = 1 if len(self.buffer) > 0 else 0
                self.buffer = self.buffer[-keep:]
                break
            if head_idx > 0: self.buffer = self.buffer[head_idx:]
            if len(self.buffer) < 8: break

            body_len = struct.unpack('>H', self.buffer[6:8])[0]
            total_len = 8 + body_len + 2

            if len(self.buffer) < total_len: break

            frame_bytes = self.buffer[:total_len]
            parsed_frame = self.process_frame(frame_bytes)
            frames.append(parsed_frame)
            self.buffer = self.buffer[total_len:]
        return frames

    def process_frame(self, data):
        msg_type = data[2]
        msg_type_hex = f"0x{msg_type:02X}"
        seq = struct.unpack('>H', data[3:5])[0]
        body = data[8:-2]
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

                # 【新增逻辑】：智能提取并显示触发的告警内容
                if 'alarm_bits' in f_data:
                    active_alarms = []
                    # 遍历所有告警位，把值为 1 (触发) 的告警名字提取出来
                    for alarm_name, is_active in f_data['alarm_bits'].items():
                        if is_active == 1:
                            active_alarms.append(alarm_name)

                    if active_alarms:
                        # 用 🚨 图标标出，非常醒目
                        summary.append(f"🚨告警: {'/'.join(active_alarms)}")

                if 'voltage' in f_data:
                    summary.append(f"V:{f_data['voltage']}")

                # 计算总位置点数：基础点(如果有) + point_list里面的差分点数
                lat_val = f_data.get('lat', f_data.get('pt1_lat'))
                total_pts = 0
                if lat_val is not None:
                    total_pts = 1
                if 'point_list' in f_data:
                    total_pts += len(f_data['point_list'])

                # 针对 0x52 专门显示点数
                if frame['type'] == '0x52':
                    summary.append(f"共包含 {total_pts} 个定位点")

                if 'health' in f_data:
                    summary.append(f"健康度:{f_data['health']}%")

                return ", ".join(summary) if summary else "无摘要"

    def get_msg_name(self, hex_type):
        # 依赖外部注入的名字，这里简写处理
        return "详情见下"

    def get_raw_data(self, row):
        return self._data[row]


class EcuMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ECU 协议解析器 (GUI版)")
        self.resize(1000, 700)

        self.all_frames = []
        self.filtered_frames = []

        try:
            self.decoder = ProtocolDecoder('protocol.json')
        except Exception as e:
            QMessageBox.critical(self, "初始化错误", str(e))
            sys.exit(1)

        self.init_ui()

    def init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)

        # --- 新增：顶部快速解析栏 ---
        self.quick_parse_layout = QHBoxLayout()

        self.quick_parse_input = QLineEdit()
        self.quick_parse_input.setPlaceholderText("在此粘贴单条或多条原始 Hex 报文 (例如: 42 44 51...)")
        self.quick_parse_input.setClearButtonEnabled(True)  # 右侧自带一个小叉叉用来一键清空

        self.quick_parse_btn = QPushButton("🚀 快速解析")
        self.quick_parse_btn.setFixedWidth(100)  # 固定按钮宽度，让它看起来更精致

        # 将输入框和按钮加入水平布局
        self.quick_parse_layout.addWidget(self.quick_parse_input)
        self.quick_parse_layout.addWidget(self.quick_parse_btn)

        # 【注意】请将下面这行代码里的 main_layout 替换为您代码中实际的总垂直布局变量名！
        # 例如您原本可能是 self.main_layout.addWidget(self.table_view)
        # 那么就在那行前面加上：
        main_layout.addLayout(self.quick_parse_layout)

        # 绑定按钮点击事件
        self.quick_parse_btn.clicked.connect(self.on_quick_parse_clicked)
        # 绑定回车键事件（在输入框里敲回车也能直接解析）
        self.quick_parse_input.returnPressed.connect(self.on_quick_parse_clicked)
        # ---------------------------

        # 1. 顶部控制栏
        control_layout = QHBoxLayout()

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
        # 猴子补丁：注入获取名字的方法
        self.table_model.get_msg_name = lambda t: self.decoder.msgs.get(t, {}).get('name', '未知')
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

    def on_quick_parse_clicked(self):
        import traceback

        try:
            # 1. 获取输入框的原始文本
            raw_text = self.quick_parse_input.text().strip()
            if not raw_text:
                return

            # 2. 拿到解析器实例
            parser = getattr(self, 'parser', None)
            if parser is None:
                # 如果当前没有加载过日志，实例化一个临时的解析器
                parser = StreamParser(self.decoder)

            # 3. 核心修复：直接调用 feed() 方法，它会自动处理字符串！
            parsed_frames = parser.feed(raw_text)

            if not parsed_frames:
                QMessageBox.warning(self, "解析失败",
                                    "未能识别出有效的协议帧。\n请检查数据是否包含完整的 4244 包头及正确的长度。")
                return

            # 4. 更新表格模型
            self.table_model.layoutAboutToBeChanged.emit()

            for frame in parsed_frames:
                frame['seq'] = "手动"  # 给序列号打个标记
                self.table_model._data.append(frame)

            self.table_model.layoutChanged.emit()

            # 5. 滚动到底部并选中最新行
            last_row_index = len(self.table_model._data) - 1
            model_index = self.table_model.index(last_row_index, 0)
            self.table_view.scrollToBottom()
            self.table_view.setCurrentIndex(model_index)

            # 6. 联动下方的树状图展示详情
            if hasattr(self, 'on_table_clicked'):
                self.on_table_clicked(model_index)

        except Exception as e:
            error_msg = traceback.format_exc()
            QMessageBox.critical(self, "程序崩溃拦截", f"底层解析抛出异常：\n\n{error_msg}")

    def load_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "选择日志文件", "", "Text Files (*.txt *.log);;All Files (*)")
        if not file_path:
            return

        self.all_frames.clear()
        self.filtered_frames.clear()
        self.table_model.update_data([])
        self.tree_model.removeRows(0, self.tree_model.rowCount())

        self.combo_filter.clear()
        self.combo_filter.addItem("显示所有类型", "ALL")

        self.btn_load.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(0)  # 跑马灯模式
        self.lbl_status.setText("正在极速解析中...")

        # 启动后台解析线程
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

        # 更新下拉框选项
        types = set(f['type'] for f in self.all_frames)
        for t in sorted(types):
            name = self.decoder.msgs.get(t, {}).get('name', 'Unknown')
            self.combo_filter.addItem(f"{t} - {name}", t)

        # 初始显示全部
        self.apply_filter()

    def on_parse_error(self, err_msg):
        self.btn_load.setEnabled(True)
        self.progress_bar.setVisible(False)
        QMessageBox.warning(self, "解析出错", err_msg)

    def apply_filter(self):
        if not self.all_frames: return
        target_type = self.combo_filter.currentData()

        if target_type == "ALL":
            self.filtered_frames = self.all_frames
        else:
            self.filtered_frames = [f for f in self.all_frames if f['type'] == target_type]

        self.table_model.update_data(self.filtered_frames)
        self.lbl_status.setText(f"当前视图: {len(self.filtered_frames)} 条记录")
        self.tree_model.removeRows(0, self.tree_model.rowCount())

    def on_row_clicked(self, index):
        """点击表格某一行，在下方树中显示详细解析结果"""
        frame = self.table_model.get_raw_data(index.row())

        self.tree_model.removeRows(0, self.tree_model.rowCount())
        root_node = self.tree_model.invisibleRootItem()

        # 构建头部信息
        info = QStandardItem(f"[基本信息] Seq: {frame['seq']}, Type: {frame['type']}")
        info.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
        root_node.appendRow(info)

        # 递归展示 JSON 字典
        self._populate_tree(root_node, frame['data'])
        self.tree_view.expandAll()

    def _populate_tree(self, parent_item, data_node):
        if isinstance(data_node, dict):
            # 获取当前字典的所有键
            keys = list(data_node.keys())

            # ====== 新增：强制显示顺序干预逻辑 ======
            # 1. 强制把 'time' (时间) 移到绝对的第一行
            if 'time' in keys:
                keys.remove('time')
                keys.insert(0, 'time')

            # 2. 针对 0x52，把 RTK 状态及动静属性强制移到 'pkg_count' 之前
            if 'pkg_count' in keys:
                rtk_fields = ["Bit00_03_RTK状态", "Bit04_超速指示", "Bit05_静态位置"]

                # 先把这些 RTK 字段从当前顺序中抽出来
                extracted = []
                for f in rtk_fields:
                    if f in keys:
                        keys.remove(f)
                        extracted.append(f)

                # 找到 pkg_count 的位置，把抽出来的字段插到它前面
                if extracted:
                    pkg_idx = keys.index('pkg_count')
                    for f in reversed(extracted):  # 反向插入以保持它们之间的原有顺序
                        keys.insert(pkg_idx, f)
            # ========================================

            # 按照调整后的顺序添加到界面树状图中
            for key in keys:
                val = data_node[key]
                if isinstance(val, (dict, list)):
                    node = QStandardItem(str(key))
                    node.setForeground(Qt.GlobalColor.darkBlue)
                    parent_item.appendRow(node)
                    self._populate_tree(node, val)  # 递归处理
                else:
                    item = QStandardItem(f"{key}: {val}")
                    parent_item.appendRow(item)

        elif isinstance(data_node, list):
            # 列表逻辑保持不变
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
            os.system(f"start {filename}")  # 仅限 Windows
        except Exception as e:
            QMessageBox.critical(self, "导出失败", str(e))


if __name__ == "__main__":
    app = QApplication(sys.argv)
    # 强制设置现代化风格
    app.setStyle("Fusion")
    window = EcuMainWindow()
    window.show()
    sys.exit(app.exec())