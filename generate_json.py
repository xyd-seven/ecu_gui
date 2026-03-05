import json
import os

# ==========================================
# 1. 基础映射与 Segments 定义
# ==========================================

# 状态位定义
raw_status_bits = {
    "0": "电门(ACC)开启", "1": "防盗开启", "2": "后轮锁开启", "3": "后座锁开启",
    "4": "照明灯开启", "5": "电池仓开启", "6": "后轮转动", "7": "车辆移动",
    "8": "定位方式(1:GPS 0:基站)", "9": "电池接入", "10": "头盔在位", "11": "头盔锁开关(1:开)",
    "14": "电门逻辑状态", "15": "重力感应(1:超载)",
    "16": "边撑状态(1:不在位)", "17": "头盔需换电池", "18": "头盔锁逻辑(1:上锁)", "19": "相机已连接",
    "20": "惯导SDK激活", "23": "保留Bit23"
}

alarm_bits_map = {
    "0": "震动告警", "1": "外部电池移除", "2": "位移告警", "3": "温度告警",
    "4": "自动落锁提示", "5": "头盔离位", "6": "头盔在位", "7": "电量告警",
    "8": "头盔锁超时", "9": "外部电池接入", "10": "ACC接通", "11": "ACC断开",
    "12": "移动告警", "13": "后座锁关闭", "14": "后座锁打开", "15": "移出围栏"
}

# 属性字节分段
attribute_segments = [
    {"name": "sat_count", "mask": 0x0F, "shift": 0, "scale": 3, "desc": "卫星数"},
    {"name": "direction", "mask": 0x70, "shift": 4, "desc": "方向值"},
    {"name": "acc_state", "mask": 0x80, "shift": 7, "mapping": {"0": "关", "1": "开"}, "desc": "ACC"}
]

# 通用状态位(含合并项)
status_segments = []
for bit, desc in raw_status_bits.items():
    bit_idx = int(bit)
    status_segments.append({
        "name": f"Bit{bit_idx:02d}_{desc.split('(')[0]}",
        "mask": 1 << bit_idx, "shift": bit_idx, "mapping": {"0": 0, "1": 1}, "desc": desc
    })

status_segments.append({
    "name": "Bit12_13_头盔佩戴状态", "mask": 0x3000, "shift": 12,
    "mapping": {"0": "未检测到锁", "1": "佩戴头盔", "2": "没有佩戴", "3": "异常"}, "desc": "头盔佩戴"
})

status_segments.append({
    "name": "Bit21_22_天线状态", "mask": 0x600000, "shift": 21,
    "mapping": {"0": "不支持", "1": "正常", "2": "短路", "3": "开路"}, "desc": "天线状态"
})
status_segments.sort(key=lambda x: x['shift'])

# 0x52 RTK状态分段
track_segments = [
    {"name": "Bit00_03_RTK状态", "mask": 0x0F, "shift": 0, "mapping": {
        "0": "无效/不可用", "1": "SPS模式定位", "2": "差分定位模式", "3": "RSV", "4": "RTK固定解定位",
        "5": "RTK浮点解定位"}},
    {"name": "Bit04_超速指示", "mask": 0x10, "shift": 4, "mapping": {"0": 0, "1": 1}},
    {"name": "Bit05_静态位置", "mask": 0x20, "shift": 5, "mapping": {"0": 0, "1": 1}}
]

# ==========================================
# 2. 抽取公共头部 (前34字节复用，适用于 0x51~0x71)
# ==========================================
common_header_fields = [
    {"name": "time", "type": "U4", "desc": "UTC时间"},
    {"name": "signal", "type": "I2", "desc": "信号强度(dBm)"},
    {"name": "temp", "type": "I1", "desc": "温度"},
    {"name": "fault_1", "type": "U1", "desc": "头盔锁故障1"},
    {"name": "status_raw", "type": "U4", "desc": "通用状态", "segments": status_segments},
    {"name": "voltage", "type": "U2", "scale": 0.1, "unit": "V", "desc": "外接电压"},
    {"name": "fault_2", "type": "U1", "desc": "头盔锁故障2"},
    {"name": "ver", "type": "U1", "desc": "协议版本"},
    {"name": "battery_pct", "type": "U1", "desc": "电量百分比"},
    {"name": "reserved", "type": "U1", "desc": "保留"},
    {"name": "imei", "type": "BCD", "length": 8, "desc": "IMEI"},
    {"name": "imsi", "type": "BCD", "length": 8, "desc": "IMSI"}
]

# ==========================================
# 3. 协议消息定义
# ==========================================
protocol_data = {
    "config": {
        "sync_header": "4244", "byte_order": "big", "skip_checksum_verification": True,
        "comment": "v1.59 (找回 0x08 平台通用应答，修复重构遗漏)"
    },
    "common_mappings": {
        "alarm_bits_map": alarm_bits_map
    },
    "messages": {

        # --- 单独定义的 0x08 平台通用应答 ---
        "0x08": {
            "name": "平台通用应答",
            "fields": [
                {"name": "time", "type": "U4", "desc": "UTC时间"},
                {"name": "signal", "type": "U2", "desc": "信号强度"},
                {"name": "temp", "type": "U1", "desc": "温度"},
                {"name": "fault_1", "type": "U1", "desc": "头盔锁故障1"},
                {"name": "status_raw", "type": "U4", "desc": "通用状态", "segments": status_segments},
                {"name": "voltage", "type": "U2", "scale": 0.1, "unit": "V", "desc": "外接电压"},
                {"name": "fault_2", "type": "U1", "desc": "头盔锁故障2"},
                {"name": "reserved", "type": "U1", "desc": "保留"},
                {"name": "ack_msg_type", "type": "U1", "desc": "应答的消息类别"},
                {"name": "ack_mid", "type": "U2", "desc": "应答的MID"},
                {"name": "imei", "type": "BCD", "length": 8, "desc": "IMEI"},
                {"name": "error_code", "type": "U1", "desc": "错误码"}
            ]
        },

        "0x51": {
            "name": "告警上报",
            "fields": common_header_fields + [
                {"name": "alarm_bits", "type": "BITFIELD_U2", "desc": "告警标志", "mapping_ref": "alarm_bits_map"},
                {"name": "sat_valid", "type": "U1", "desc": "卫星有效位(Bit0)"},
                {"name": "acc_raw", "type": "U1", "desc": "ACC状态",
                 "segments": [{"name": "acc_state", "mask": 1, "shift": 0, "mapping": {"0": "断开", "1": "接通"}}]},
                {"name": "pt_time", "type": "U4", "desc": "告警发生时间"},
                {"name": "lat", "type": "I4", "scale": 0.000001, "desc": "纬度"},
                {"name": "lng", "type": "I4", "scale": 0.000001, "desc": "经度"},
                {"name": "speed", "type": "U1", "desc": "速度"},
                {"name": "dir_sat_raw", "type": "U1", "desc": "方向和卫星", "segments": [
                    {"name": "sat_count", "mask": 0x0F, "shift": 0, "scale": 3, "desc": "卫星数"},
                    {"name": "direction", "mask": 0x70, "shift": 4, "desc": "方向值"}
                ]}
            ]
        },

        "0x52": {
            "name": "卫星位置消息",
            "is_loop": True, "loop_count_field": "pkg_count",
            "fields": common_header_fields + [
                {"name": "track_info_raw", "type": "U1", "desc": "追踪与RTK状态", "segments": track_segments},
                {"name": "pkg_count", "type": "U1", "desc": "信息组数N"},
                {"name": "pt1_time", "type": "U4", "desc": "第1点时间"},
                {"name": "pt1_lat", "type": "I4", "scale": 0.000001, "desc": "第1点纬度"},
                {"name": "pt1_lng", "type": "I4", "scale": 0.000001, "desc": "第1点经度"},
                {"name": "pt1_speed_raw", "type": "U1", "desc": "第1点速度"},
                {"name": "pt1_attr_raw", "type": "U1", "desc": "第1点属性", "segments": attribute_segments}
            ],
            "sub_struct": [
                {"name": "diff_time", "type": "U2", "desc": "时间差值(s)"},
                {"name": "diff_lat", "type": "I2", "scale": 0.000001, "desc": "纬度差值"},
                {"name": "diff_lng", "type": "I2", "scale": 0.000001, "desc": "经度差值"},
                {"name": "pt_speed_raw", "type": "U1", "desc": "速度"},
                {"name": "pt_attr_raw", "type": "U1", "desc": "属性", "segments": attribute_segments}
            ]
        },

        "0x53": {
            "name": "基站位置消息",
            "fields": common_header_fields + [
                {"name": "cn_value", "type": "U1", "desc": "载噪比CN"},
                {"name": "hdop", "type": "U1", "desc": "HDOP水平精度"}
            ]
        },

        "0x54": {
            "name": "实时追踪消息",
            "fields": common_header_fields + [
                {"name": "sat_valid", "type": "U1", "desc": "卫星有效位"},
                {"name": "acc_motion_raw", "type": "U1", "desc": "ACC及动静状态", "segments": [
                    {"name": "is_motion", "mask": 1, "shift": 0, "mapping": {"0": "静", "1": "动"}, "desc": "动静状态"},
                    {"name": "acc_state", "mask": 2, "shift": 1, "mapping": {"0": "断开", "1": "接通"},
                     "desc": "ACC状态"}
                ]},
                {"name": "pt_time", "type": "U4", "desc": "点时间"},
                {"name": "lat", "type": "I4", "scale": 0.000001, "desc": "纬度"},
                {"name": "lng", "type": "I4", "scale": 0.000001, "desc": "经度"},
                {"name": "speed", "type": "U1", "desc": "速度"},
                {"name": "dir_sat_raw", "type": "U1", "desc": "方向和卫星", "segments": [
                    {"name": "sat_count", "mask": 0x0F, "shift": 0, "scale": 3, "desc": "卫星数"},
                    {"name": "direction", "mask": 0x70, "shift": 4, "desc": "方向值"}
                ]}
            ]
        },

        "0x55": {
            "name": "查询位置消息",
            "fields": common_header_fields + [
                {"name": "sat_valid", "type": "U1", "desc": "卫星有效位"},
                {"name": "acc_motion_raw", "type": "U1", "desc": "ACC及动静状态", "segments": [
                    {"name": "is_motion", "mask": 1, "shift": 0, "mapping": {"0": "静", "1": "动"}, "desc": "动静状态"},
                    {"name": "acc_state", "mask": 2, "shift": 1, "mapping": {"0": "断开", "1": "接通"},
                     "desc": "ACC状态"}
                ]},
                {"name": "pt_time", "type": "U4", "desc": "点时间"},
                {"name": "lat", "type": "I4", "scale": 0.000001, "desc": "纬度"},
                {"name": "lng", "type": "I4", "scale": 0.000001, "desc": "经度"},
                {"name": "speed", "type": "U1", "desc": "速度"},
                {"name": "dir_sat_raw", "type": "U1", "desc": "方向和卫星", "segments": [
                    {"name": "sat_count", "mask": 0x0F, "shift": 0, "scale": 3, "desc": "卫星数"},
                    {"name": "direction", "mask": 0x70, "shift": 4, "desc": "方向值"}
                ]}
            ]
        },

        "0x5A": {
            "name": "状态消息",
            "fields": common_header_fields + [
                {"name": "reserved1", "type": "U2", "desc": "保留"},
                {"name": "reserved2", "type": "U4", "desc": "保留"}
            ]
        },

        "0x5E": {
            "name": "心跳/链路保持",
            "fields": [
                {"name": "time", "type": "U4", "desc": "UTC时间"},
                {"name": "imei", "type": "BCD", "length": 8, "desc": "终端IMEI"}
            ]
        },

        "0x60": {
            "name": "车辆角度消息",
            "fields": common_header_fields + [
                {"name": "angle_status_raw", "type": "U1", "desc": "角度状态", "segments": [
                    {"name": "angle_valid", "mask": 1, "shift": 0, "mapping": {"0": "无效", "1": "有效"},
                     "desc": "角度有效指示"},
                    {"name": "fall_alarm", "mask": 2, "shift": 1, "mapping": {"0": "无倾倒", "1": "车辆倾倒"},
                     "desc": "倾倒告警"}
                ]},
                {"name": "roll_angle", "type": "U2", "scale": 0.01, "unit": "°", "desc": "车辆倾斜角度"},
                {"name": "pitch_angle", "type": "U2", "scale": 0.01, "unit": "°", "desc": "车辆俯仰角度"},
                {"name": "yaw_angle", "type": "U2", "scale": 0.01, "unit": "°", "desc": "车辆航向角度"}
            ]
        },

        "0x68": {
            "name": "硬件配置信息",
            "fields": common_header_fields + [
                {"name": "res2", "type": "U2", "desc": "保留"},
                {"name": "res3", "type": "U4", "desc": "保留"},
                {"name": "hw_ver", "type": "BYTES", "length": 20, "desc": "硬件版本(Hex)"},
                {"name": "cam", "type": "U1", "desc": "支持摄像"}
            ]
        },

        "0x6C": {
            "name": "BMS信息上报",
            "fields": common_header_fields + [
                {"name": "bms_conn", "type": "U1", "desc": "BMS连接"},
                {"name": "bms_sn", "type": "BYTES", "length": 40, "desc": "BMS SN"},
                {"name": "bms_sw", "type": "U4", "desc": "BMS软件版"},
                {"name": "bms_hw", "type": "U2", "desc": "BMS硬件版"},
                {"name": "health", "type": "U1", "desc": "健康度"},
                {"name": "out_st", "type": "U1", "desc": "输出状态"},
                {"name": "in_temp", "type": "U2", "scale": 0.1, "unit": "C", "desc": "内温"},
                {"name": "tot_vol", "type": "U4", "unit": "mV", "desc": "总压"},
                {"name": "cur", "type": "U4", "unit": "mA", "desc": "电流"},
                {"name": "cap_rel", "type": "U1", "desc": "相对容量"},
                {"name": "cap_abs", "type": "U1", "desc": "绝对容量"},
                {"name": "rem_cap", "type": "U4", "unit": "mAh", "desc": "剩余容量"},
                {"name": "full_cap", "type": "U4", "unit": "mAh", "desc": "满电容量"},
                {"name": "cyc", "type": "U4", "desc": "循环次"},
                {"name": "st_info", "type": "BYTES", "length": 16, "desc": "状态信息"}
            ]
        },

        "0x6D": {
            "name": "蓝牙扫描周边车辆消息",
            "fields": common_header_fields + [
                {"name": "mac_addr", "type": "BCD", "length": 8, "desc": "周边车辆蓝牙MAC"}
            ]
        },

        "0x6E": {
            "name": "状态请求消息",
            "fields": common_header_fields + [
                {"name": "check_park_req", "type": "U1", "segments": [{"name": "req_status", "mask": 1, "shift": 0,
                                                                       "mapping": {"0": "默认",
                                                                                   "1": "请求检查是否在停车区"}}]},
                {"name": "reserved_bytes", "type": "BYTES", "length": 7, "desc": "保留"}
            ]
        },

        "0x6F": {
            "name": "定位模块搜星模式消息",
            "fields": common_header_fields + [
                {"name": "gps_mode", "type": "U1", "mapping": {"0": "北斗+GPS", "1": "单北斗"}, "desc": "搜星模式"},
                {"name": "reserved_u4", "type": "U4", "desc": "保留"}
            ]
        },

        "0x70": {
            "name": "定位模块安装轴向消息",
            "fields": common_header_fields + [
                {"name": "axis_front", "type": "I1", "desc": "前向轴关系"},
                {"name": "axis_right", "type": "I1", "desc": "右向轴关系"},
                {"name": "axis_down", "type": "I1", "desc": "下向轴关系"},
                {"name": "reserved_u4", "type": "U4", "desc": "保留"}
            ]
        },

        "0x71": {
            "name": "相机参数消息(武吉02)",
            "fields": common_header_fields + [
                {"name": "cam_status_raw", "type": "U1", "segments": [
                    {"name": "cam_param_status", "mask": 1, "shift": 0, "mapping": {"0": "无效", "1": "有效"}}]},
                {"name": "func_switch", "type": "U1", "desc": "功能开关"},
                {"name": "led_mode", "type": "U1", "mapping": {"0": "禁止补光", "1": "强制补光", "2": "自动补光"},
                 "desc": "LED补光灯模式"},
                {"name": "similarity_thresh", "type": "U1", "scale": 0.01, "desc": "相似度阈值"},
                {"name": "line_type", "type": "U1",
                 "mapping": {"1": "空", "2": "绿T", "3": "蓝黄线", "4": "白蓝线", "5": "白红线"}, "desc": "标志线类型"},
                {"name": "angle_thresh", "type": "U1", "unit": "°", "desc": "角度阈值θ"},
                {"name": "reserved_u2", "type": "BYTES", "length": 2, "desc": "预留"}
            ]
        }

    }
}

try:
    print("正在生成 protocol.json ...")
    with open('protocol.json', 'w', encoding='utf-8-sig') as f:
        json.dump(protocol_data, f, indent=2, ensure_ascii=False)
    print("生成成功！protocol.json 已更新。")
    print("- 找回了 0x08 (平台通用应答) 的独立结构配置。")
except Exception as e:
    print(f"生成失败: {e}")

input("按回车键结束...")