import os
import sys
import subprocess
import re
import datetime
import tkinter as tk
from tkinter import filedialog
import concurrent.futures
import time
import threading

print_lock = threading.Lock()

def get_resource_path(filename):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, filename)
    return os.path.join(os.path.abspath("."), filename)

def parse_ffmpeg_time(time_str):
    try:
        h, m, s = time_str.split(':')
        return int(h) * 3600 + int(m) * 60 + float(s)
    except:
        return 0

# --- 核心处理逻辑 ---
def process_video_safe(file_info):
    file_path, ffmpeg_path = file_info
    filename = os.path.basename(file_path)

    # 1. 快速元数据分析
    cmd_quick = [ffmpeg_path, "-i", file_path]
    try:
        result = subprocess.run(cmd_quick, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='ignore', timeout=5)
        output = result.stderr
        
        duration_match = re.search(r"Duration:\s*(\d{2}:\d{2}:\d{2}\.\d{2})", output)
        
        if duration_match:
            header_seconds = parse_ffmpeg_time(duration_match.group(1))
            file_size = os.path.getsize(file_path)
            if header_seconds > 0:
                avg_bitrate = file_size / header_seconds
                # 码率检测：大于 100KB/s 视为有效索引
                if avg_bitrate > 100 * 1024:
                    return filename, header_seconds, "索引读取"
    except:
        pass

    # 2. 全量流式分析 (深度扫描)
    with print_lock:
        print(f"-> [深度分析] {filename} (元数据异常，执行全量扫描)...", flush=True)

    cmd_deep = [
        ffmpeg_path,
        "-i", file_path,
        "-c", "copy",
        "-f", "null",
        "-"
    ]
    
    try:
        result = subprocess.run(cmd_deep, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='ignore', timeout=600)
        output = result.stderr
        
        time_matches = re.findall(r"time=(\d{2}:\d{2}:\d{2}\.\d{2})", output)
        if time_matches:
            final_seconds = parse_ffmpeg_time(time_matches[-1])
            if final_seconds > 1:
                return filename, final_seconds, "全量校验"

        return filename, 0, "解析失败"

    except subprocess.TimeoutExpired:
        return filename, 0, "读取超时"
    except Exception:
        return filename, 0, "未知错误"

# --- 主流程 ---
def scan_folder_single_thread(folder_path):
    EXTENSIONS = ('.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.dav', '.264', '.ts')
    tasks = []
    ffmpeg_path = get_resource_path("ffmpeg.exe")
    
    print(f"目标目录: {folder_path}")
    print("正在初始化文件索引...", end="", flush=True)
    
    for root, dirs, files in os.walk(folder_path):
        for file in files:
            if file.lower().endswith(EXTENSIONS):
                full_path = os.path.join(root, file)
                tasks.append((full_path, ffmpeg_path))
    
    total_files = len(tasks)
    print(f" 就绪 (共 {total_files} 个文件)")
    
    # 强制单线程 (保护 I/O)
    max_workers = 1
    
    print("-" * 80)
    print(f"运行模式: 串行 I/O 扫描 (数据完整性优先)")
    print("-" * 80)
    print(f"{'文件名':<35} | {'处理方式':<10} | {'时长':<10} | {'状态'}")
    print("-" * 80)
    
    total_seconds = 0.0
    valid_count = 0
    start_time = time.time()
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_file = {executor.submit(process_video_safe, task): task for task in tasks}
        
        for future in concurrent.futures.as_completed(future_to_file):
            filename, duration, method = future.result()
            
            with print_lock:
                if duration > 0:
                    total_seconds += duration
                    valid_count += 1
                    time_str = str(datetime.timedelta(seconds=int(duration)))
                    
                    # 状态标记
                    status_icon = "√"
                    if method == "全量校验": status_icon = "★" # 特殊标记
                    
                    print(f"{status_icon} {filename:<35} | {method:<10} | {time_str:<10} | 成功")
                else:
                    print(f"X {filename:<35} | {'--':<10} | --:--:--   | {method}")

    end_time = time.time()
    return total_seconds, valid_count, total_files, end_time - start_time

if __name__ == "__main__":
    if not os.path.exists(get_resource_path("ffmpeg.exe")):
        print("【错误】核心组件 ffmpeg.exe 缺失。")
        input("按回车键退出...")
        sys.exit()

    root = tk.Tk()
    root.withdraw()
    target_folder = filedialog.askdirectory(title="选择视频文件夹")

    if target_folder:
        target_folder = os.path.abspath(target_folder)
        seconds, valid, total, cost_time = scan_folder_single_thread(target_folder)
        
        final_time = str(datetime.timedelta(seconds=int(seconds)))
        
        # 课时计算
        class_hours = seconds / 2700.0
        
        print("\n" + "=" * 80)
        print(f"视频统计分析报告")
        print("-" * 80)
        print(f"执行耗时 : {cost_time:.1f} 秒")
        print(f"处理进度 : {valid} / {total} 文件")
        print("-" * 80)
        print(f"累计时长 : {final_time}")
        print(f"折算课时 : {class_hours:.1f} 课时 (标准: 45分钟/课时)")
        print("=" * 80)

    input("\n按回车键退出...")
