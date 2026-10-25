import tkinter as tk
import time
from datetime import datetime
import os
import socket

# ---------- 参数设置 ----------
current_date = datetime.now().strftime('%Y%m%d')
file_path = f'D:/2025data/ch6/{current_date}_ch6.txt'

max_buffer = 100                   # 初始化读取100条记录
new_records_per_calc = 15          # 每新增15条数据计算一次

threshold = 1e-12                  # 初始化阈值，保持原值
lbs_per_freq = 2.58602e-13          # 每LSB对应的频差
threshold_realtime = 1.8 * lbs_per_freq  # 实时触发阈值

large_error_lsb = 4.0              # 达到4 LSB时调整2 LSB

TARGET_IP = "119.78.227.149"
TARGET_PORT = 4002

udp_log = []
max_log_items = 5

log_file_path = os.path.join(
    os.path.dirname(file_path),
    "operation_log.txt"
)


# ---------- 辅助函数 ----------
def write_log(command):
    """记录发送指令。"""
    with open(log_file_path, "a") as log_file:
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_file.write(f"{timestamp}  {command}\n")


def parse_line(line):
    """返回 (timestamp, measurement, data_point)。"""
    parts = line.split()
    if len(parts) < 4:
        return None

    try:
        timestamp = datetime.strptime(
            parts[0] + " " + parts[1],
            "%Y-%m-%d %H:%M:%S.%f"
        )
        measurement = float(parts[2])  # 单位：ns
        data_point = int(parts[3])
    except ValueError as e:
        print(f"Error parsing line: {e}")
        return None

    return timestamp, measurement, data_point


def read_new_data(file_path, last_position):
    """从上次位置读取新增数据。"""
    new_data = []

    try:
        with open(file_path, 'r') as f:
            f.seek(last_position)

            for line in f.readlines():
                record = parse_line(line)
                if record is not None:
                    new_data.append(record)

            last_position = f.tell()

    except Exception as e:
        print(f"Error reading file: {e}")

    return new_data, last_position


def calculate_frequency_difference_general(window):
    """
    沿用原频差计算方式，假设相邻记录间隔1秒。
    N条记录对应N-1个时间间隔。

    返回：
        相对频差
        首尾时差变化量（ns）
    """
    if len(window) < 2:
        return 0, 0

    meas_diff_ns = window[-1][1] - window[0][1]
    freq_diff = meas_diff_ns * 1e-9 / (len(window) - 1)

    return freq_diff, meas_diff_ns


def compute_voltage_adjustment(freq_diff):
    """
    调用方先判断是否超过触发阈值。

    绝对频差不足4 LSB：调整1 LSB。
    绝对频差达到4 LSB：调整2 LSB。
    保持原代码的调节方向。
    """
    if freq_diff == 0:
        return 0

    if abs(freq_diff) >= large_error_lsb * lbs_per_freq:
        step = 2
    else:
        step = 1

    return step if freq_diff > 0 else -step


def update_udp_log_label():
    log_text = "Last UDP commands:\n" + "\n".join(udp_log)
    label_udp.config(text=log_text)


def send_voltage_command(adjustment):
    """发送相对调节指令，例如 $S0M+1 或 $S0M-2。"""
    if adjustment == 0:
        return

    sign = '+' if adjustment > 0 else '-'
    command = f"$S0M{sign}{abs(adjustment)}"

    try:
        with socket.socket(
            socket.AF_INET, socket.SOCK_DGRAM
        ) as sock:
            sock.sendto(
                command.encode('utf-8'),
                (TARGET_IP, TARGET_PORT)
            )
    except Exception as e:
        print(f"Error sending voltage command: {e}")
        return

    print(f"Sent command: {command}")

    udp_log.append(command)
    if len(udp_log) > max_log_items:
        udp_log.pop(0)

    update_udp_log_label()

    try:
        write_log(command)
    except Exception as e:
        print(f"Command sent, but logging failed: {e}")


# ---------- 全局变量 ----------
last_position = 0
buffer = []
new_records_count = 0
countdown_time = 20000


# ---------- 初始化 ----------
while len(buffer) < max_buffer:
    new_data, last_position = read_new_data(
        file_path, last_position
    )

    if new_data:
        buffer.extend(new_data)
    else:
        time.sleep(0.1)

buffer = buffer[-max_buffer:]

init_freq_diff, init_meas_diff = (
    calculate_frequency_difference_general(buffer)
)

print(f"Initialization successful. Read {len(buffer)} records.")
print(f"Initial frequency difference: {init_freq_diff:.8e}")
print(f"Original measurement difference: {init_meas_diff:.6f} ns")
print(f"Realtime threshold: {threshold_realtime:.8e} (1.8 LSB)")
print(f"2-LSB adjustment threshold: {large_error_lsb} LSB")
print(f"Calculation interval: {new_records_per_calc} new records")


# ---------- 动态界面 ----------
root = tk.Tk()
root.title("频差动态监控")

label_info = tk.Label(
    root,
    text="",
    font=("Helvetica", 14)
)
label_info.pack(padx=20, pady=10)

label_voltage = tk.Label(
    root,
    text="",
    font=("Helvetica", 14)
)
label_voltage.pack(padx=20, pady=10)

label_udp = tk.Label(
    root,
    text="",
    font=("Helvetica", 14),
    fg="blue"
)
label_udp.pack(padx=20, pady=10)

update_udp_log_label()

# 标签创建后再执行初始化调节。
# 初始化也使用1/2 LSB分级步长。
if abs(init_freq_diff) > threshold:
    init_adjustment = compute_voltage_adjustment(init_freq_diff)

    print(f"Initial voltage adjustment: {init_adjustment:+d} LSB")
    send_voltage_command(init_adjustment)

    label_voltage.config(
        text=(
            f"初始化频差：{init_freq_diff:.8e}\n"
            f"初始化调整指令：{init_adjustment:+d} LSB"
        )
    )
else:
    print("Initial frequency difference is within acceptable range.")

    label_voltage.config(
        text=(
            f"初始化频差：{init_freq_diff:.8e}\n"
            "初始化无需调整"
        )
    )


# ---------- 实时更新 ----------
def update_monitor():
    global last_position, buffer
    global new_records_count, countdown_time

    new_data, last_position = read_new_data(
        file_path, last_position
    )

    if new_data:
        buffer.extend(new_data)
        new_records_count += len(new_data)
        buffer = buffer[-max_buffer:]

    label_info.config(
        text=(
            f"缓冲区记录数：{len(buffer)}\n"
            f"本轮新增记录：{new_records_count}"
            f" / {new_records_per_calc}\n"
            f"实时阈值：1.8 LSB"
            f"（{threshold_realtime:.8e}）\n"
            f"2 LSB步长触发条件：偏差达到"
            f" {large_error_lsb:g} LSB"
        )
    )

    if (
        new_records_count >= new_records_per_calc
        and len(buffer) >= new_records_per_calc
    ):
        # 每次计算后重新累计，包括无需调整的情况。
        # 批量收到多条数据时，只根据最新窗口判断一次，
        # 避免针对同一批数据连续发送多条调节指令。
        new_records_count = 0

        window = buffer[-new_records_per_calc:]

        avg_freq_diff, meas_diff_ns = (
            calculate_frequency_difference_general(window)
        )

        equivalent_lsb = avg_freq_diff / lbs_per_freq

        result_text = (
            f"最近 {new_records_per_calc} 条数据频差："
            f"{avg_freq_diff:.8e}\n"
            f"等效偏差：{equivalent_lsb:+.3f} LSB\n"
            f"窗口首尾时差变化：{meas_diff_ns:+.6f} ns\n"
        )

        if abs(avg_freq_diff) > threshold_realtime:
            voltage_adjustment = compute_voltage_adjustment(
                avg_freq_diff
            )

            send_voltage_command(voltage_adjustment)

            label_voltage.config(
                text=(
                    result_text
                    + f"本次调整指令：{voltage_adjustment:+d} LSB"
                )
            )
        else:
            label_voltage.config(
                text=result_text + "频差在阈值内，无需调整"
            )

            # 沿用上一版退出计数逻辑：
            # 每次计算结果在阈值内时减1，
            # 此计数并非实际经过的秒数。
            countdown_time -= 1

            if countdown_time <= 0:
                root.quit()
                return

    root.after(100, update_monitor)


update_monitor()
root.mainloop()
