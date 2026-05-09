import sys
import os
import csv
import numpy as np
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QLabel, QPushButton, QFileDialog, 
                             QDialog, QTextEdit, QStackedWidget)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap, QFont
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.pyplot as plt

# 解决 Matplotlib 中文显示问题 (兼容 Mac 和 Windows)
plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'SimHei', 'Microsoft YaHei']
plt.rcParams['axes.unicode_minus'] = False

# ==========================================
# 模态对话框：用于显示数据读取状态
# ==========================================
class DataCheckDialog(QDialog):
    def __init__(self, check_msg, is_valid, parent=None):
        super().__init__(parent)
        self.setWindowTitle("数据读取状态")
        self.setFixedSize(400, 250)
        
        layout = QVBoxLayout()
        
        # 显示信息的文本框 (只读)
        self.info_box = QTextEdit()
        self.info_box.setReadOnly(True)
        self.info_box.setText(check_msg)
        layout.addWidget(self.info_box)
        
        # 按钮布局
        btn_layout = QHBoxLayout()
        self.btn_continue = QPushButton("继续")
        self.btn_exit = QPushButton("退出")
        
        # 只有数据有效时，才允许点击继续
        self.btn_continue.setEnabled(is_valid)
        if is_valid:
            self.btn_continue.setStyleSheet("background-color: #4CAF50; color: white;")
        
        btn_layout.addStretch(1) # 把按钮推到右边
        btn_layout.addWidget(self.btn_continue)
        btn_layout.addWidget(self.btn_exit)
        layout.addLayout(btn_layout)
        
        self.setLayout(layout)
        
        # 信号绑定
        self.btn_continue.clicked.connect(self.accept) # 点击继续，返回 accepted 状态
        self.btn_exit.clicked.connect(self.reject)     # 点击退出，返回 rejected 状态

# ==========================================
# 主窗口
# ==========================================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DOA 天线幅相数据分析工具")
        self.resize(800, 600)
        
        # 使用多页面管理器，方便实现“窗口刷新”
        self.stacked_widget = QStackedWidget()
        self.setCentralWidget(self.stacked_widget)
        
        # 数据存储
        self.amplitude_data = {}  # 幅度数据 {antenna_id: (frequencies, values)}
        self.phase_data = {}      # 相位数据 {antenna_id: (frequencies, values)}
        self.frequencies = None   # 频率数组
        self.antenna_count = 0    # 天线数量
        self.complex_data = None  # 复数数据数组: [频率][角度][天线] = A*exp(ia)
        
        # 初始化两个页面
        self.init_welcome_page()
        self.init_plot_page()
        
        # 默认显示欢迎页
        self.stacked_widget.setCurrentWidget(self.welcome_page)

    def init_welcome_page(self):
        """初始化第一页：图片、文字说明、导入按钮"""
        self.welcome_page = QWidget()
        layout = QVBoxLayout()
        
        # 1. 天线模型图片展示区
        self.img_label = QLabel()
        self.img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.img_label.setStyleSheet("border: 2px dashed #aaa; background-color: #f0f0f0;")
        self.img_label.setMinimumHeight(300)
        
        # 尝试加载图片，如果没有图片则显示文字占位
        img_path = "antenna_model.png" # 请将真实图片放在同一目录下
        if os.path.exists(img_path):
            pixmap = QPixmap(img_path)
            self.img_label.setPixmap(pixmap.scaled(400, 300, Qt.AspectRatioMode.KeepAspectRatio))
        else:
            self.img_label.setText("【天线模型示意图】\n(请在程序目录下放置 antenna_model.png)")
        layout.addWidget(self.img_label)
        
        # 2. 文字描述区
        desc_label = QLabel(
            "数据输入要求说明：\n"
            "1. 请点击下方按钮选择包含仿真数据的【文件夹】。\n"
            "2. 天线以及角度需按照坐标系定义。\n"
            "3. 幅度文件按An.csv命名，相位文件按Pn.csv命名（n为天线序号，如A1.csv、P8.csv）。\n"
            "4. 数据第一列为频率，最后一列为数据，幅值单位为dB，相位单位为角度。\n"
            "5. 程序将自动进行完整性校验。"
        )
        desc_label.setFont(QFont("Arial", 12))
        layout.addWidget(desc_label)
        
        layout.addStretch(1) # 把按钮推到底部
        
        # 3. 左下角的导入按钮
        btn_layout = QHBoxLayout()
        self.btn_import = QPushButton("导入模型")
        self.btn_import.setFixedSize(120, 40)
        self.btn_import.clicked.connect(self.handle_import)
        
        btn_layout.addWidget(self.btn_import)
        btn_layout.addStretch(1) # 保证按钮在左边
        layout.addLayout(btn_layout)
        
        self.welcome_page.setLayout(layout)
        self.stacked_widget.addWidget(self.welcome_page)

    def init_plot_page(self):
        """初始化第二页：绘图展示区"""
        self.plot_page = QWidget()
        layout = QVBoxLayout()
        
        # 创建 Matplotlib 画布
        self.figure = Figure()
        self.canvas = FigureCanvas(self.figure)
        layout.addWidget(self.canvas)
        
        # 增加一个返回按钮（方便调试）
        self.btn_back = QPushButton("重新导入")
        self.btn_back.clicked.connect(lambda: self.stacked_widget.setCurrentWidget(self.welcome_page))
        layout.addWidget(self.btn_back)
        
        self.plot_page.setLayout(layout)
        self.stacked_widget.addWidget(self.plot_page)

    # ==========================================
    # 核心交互逻辑
    # ==========================================
    def handle_import(self):
        # 1. 弹出文件夹选择框
        folder_path = QFileDialog.getExistingDirectory(self, "选择仿真数据所在文件夹", "")
        
        if not folder_path:
            return # 用户取消了选择
        
        # 2. 处理数据 (调用你自定义的函数)
        is_valid, msg = self.process_simulation_data(folder_path)
        
        # 3. 弹出校验结果对话框
        dialog = DataCheckDialog(check_msg=msg, is_valid=is_valid, parent=self)
        result = dialog.exec() # 阻塞执行，等待用户点击
        
        if result == QDialog.DialogCode.Accepted:
            # 用户点击了“继续” -> 刷新窗口显示图表
            self.draw_amplitude_pattern()
            self.stacked_widget.setCurrentWidget(self.plot_page)
        else:
            # 用户点击了“退出”或关闭了对话框 -> 什么都不做，留在原页面
            pass

    # ------------------------------------------
    # 数据处理核心函数
    # ------------------------------------------
    def process_simulation_data(self, folder_path):
        """
        读取并校验数据的函数
        返回: 
            is_valid (bool): 数据是否可用
            msg (str): 要在弹窗中显示的提示信息
        """
        # 清空之前的数据
        self.amplitude_data = {}
        self.phase_data = {}
        self.frequencies = None
        self.antenna_count = 0
        self.complex_data = None
        
        msg_lines = [f"读取路径: {folder_path}"]
        msg_lines.append("-----------------------------")
        
        # 获取文件夹中的所有文件
        try:
            files = os.listdir(folder_path)
        except Exception as e:
            msg_lines.append(f"❌ 无法读取文件夹: {str(e)}")
            return False, "\n".join(msg_lines)
        
        # 查找所有 An.csv 和 Pn.csv 文件
        amp_files = {}  # {antenna_id: filename}
        phase_files = {}
        
        for f in files:
            if f.startswith('A') and f.endswith('.csv'):
                try:
                    n = int(f[1:-4])  # 提取天线序号
                    amp_files[n] = f
                except ValueError:
                    pass
            elif f.startswith('P') and f.endswith('.csv'):
                try:
                    n = int(f[1:-4])  # 提取天线序号
                    phase_files[n] = f
                except ValueError:
                    pass
        
        # 检查是否有数据文件
        if not amp_files and not phase_files:
            msg_lines.append("❌ 未找到任何 An.csv 或 Pn.csv 文件")
            return False, "\n".join(msg_lines)
        
        # 确定天线数量（最大序号）
        all_antennas = set(amp_files.keys()).union(set(phase_files.keys()))
        if not all_antennas:
            msg_lines.append("❌ 未找到有效的天线数据文件")
            return False, "\n".join(msg_lines)
        
        max_antenna = max(all_antennas)
        
        # 检查天线序号是否连续
        missing_antennas = []
        for n in range(1, max_antenna + 1):
            if n not in amp_files:
                missing_antennas.append(f"A{n}.csv")
            if n not in phase_files:
                missing_antennas.append(f"P{n}.csv")
        
        errors = []
        if missing_antennas:
            errors.append(f"❌ 缺少数据文件: {', '.join(missing_antennas)}")
        
        # 读取所有天线数据
        freq_data = {}  # {freq: {antenna: (amp_data, phase_data)}}
        all_freqs = set()
        
        for n in range(1, max_antenna + 1):
            if n not in amp_files or n not in phase_files:
                continue  # 跳过缺失的天线
            
            amp_path = os.path.join(folder_path, amp_files[n])
            phase_path = os.path.join(folder_path, phase_files[n])
            
            try:
                # 读取幅度文件
                freqs, amp_values, angles = self.read_csv_data_with_angles(amp_path)
                self.amplitude_data[n] = (freqs, amp_values, angles)
                
                # 读取相位文件
                freqs_p, phase_values, angles_p = self.read_csv_data_with_angles(phase_path)
                self.phase_data[n] = (freqs_p, phase_values, angles_p)
                
                # 检查频率一致性
                if not np.allclose(freqs, freqs_p):
                    errors.append(f"❌ 天线{n}幅度与相位数据频率不一致")
                    continue
                
                # 检查角度一致性
                if not np.allclose(angles, angles_p):
                    errors.append(f"❌ 天线{n}幅度与相位数据角度不一致")
                    continue
                
                # 存储数据
                for i, freq in enumerate(freqs):
                    if freq not in freq_data:
                        freq_data[freq] = {}
                        all_freqs.add(freq)
                    freq_data[freq][n] = (amp_values[i], phase_values[i])
                
                msg_lines.append(f"✅ 读取天线{n}数据 (A{n}.csv + P{n}.csv)")
                
            except Exception as e:
                errors.append(f"❌ 读取天线{n}数据失败: {str(e)}")
        
        # 检查所有天线的频率数量是否一致
        if self.amplitude_data:
            first_freq_count = len(self.amplitude_data[1][0]) if 1 in self.amplitude_data else 0
            
            for n in range(1, max_antenna + 1):
                if n in self.amplitude_data:
                    freq_count = len(self.amplitude_data[n][0])
                    if freq_count != first_freq_count:
                        errors.append(f"❌ 天线{n}频率点数({freq_count})与天线1频率点数({first_freq_count})不一致")
        
        # 添加错误信息（只添加一次）
        msg_lines.extend(errors)
        
        # 如果有错误，返回失败
        if errors:
            msg_lines.append(f"\n⚠️ 发现 {len(errors)} 个错误，请检查数据文件")
            return False, "\n".join(msg_lines)
        
        # 整理频率数组（排序）
        self.frequencies = np.sort(np.array(list(all_freqs)))
        self.antenna_count = max_antenna
        
        # 构建复数数据数组 [频率][角度][天线]
        num_freqs = len(self.frequencies)
        num_angles = 360  # 去除最后一个点（360度与0度相同）
        
        try:
            self.complex_data = np.zeros((num_freqs, num_angles, max_antenna), dtype=np.complex128)
            
            for freq_idx, freq in enumerate(self.frequencies):
                if freq in freq_data:
                    for n in range(1, max_antenna + 1):
                        if n in freq_data[freq]:
                            amp_db, phase_deg = freq_data[freq][n]
                            # 转换为线性幅度和弧度相位
                            amp_linear = 10 ** (amp_db / 20.0)
                            phase_rad = np.deg2rad(phase_deg)
                            # 存储复数数据 A * exp(ia)
                            self.complex_data[freq_idx, :, n - 1] = amp_linear * np.exp(1j * phase_rad)
            
            msg_lines.append(f"\n✅ 成功构建复数数据数组 [{num_freqs}x{num_angles}x{max_antenna}]")
        except Exception as e:
            msg_lines.append(f"❌ 构建复数数据数组失败: {str(e)}")
            return False, "\n".join(msg_lines)
        
        # 计算频率信息
        freq_info = self.analyze_frequency_info(self.frequencies)
        msg_lines.append(f"\n📊 频率信息:")
        msg_lines.append(freq_info)
        
        msg_lines.append(f"\n✅ 数据校验通过，可以继续！")
        return True, "\n".join(msg_lines)
    
    def read_csv_data_with_angles(self, filepath):
        """
        读取 CSV 文件数据，包含频率和角度信息
        格式要求：第一列为频率，最后一列为数据值
        每个频率有361行数据（0-360度），返回时去除最后一行（360度）
        返回: (frequencies, data_array, angles)
            frequencies: 唯一频率数组
            data_array: [频率][角度] 的数据数组（360个角度）
            angles: 角度数组（360个，0-359度）
        抛出异常: 如果数据不完整（每个频率应包含361行数据）
        """
        freq_data_map = {}  # {freq: [values]}
        filename = os.path.basename(filepath)
        
        with open(filepath, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            header = next(reader)  # 跳过表头
            
            for row in reader:
                if len(row) >= 2:
                    freq = float(row[0])  # 第一列是频率
                    value = float(row[-1])  # 最后一列是数据
                    
                    if freq not in freq_data_map:
                        freq_data_map[freq] = []
                    freq_data_map[freq].append(value)
        
        # 排序频率
        sorted_freqs = sorted(freq_data_map.keys())
        num_freqs = len(sorted_freqs)
        
        if num_freqs == 0:
            raise ValueError(f"{filename}: 未找到任何有效数据行")
        
        # 检查每个频率的数据行数是否完整（应为361行，包含0-360度）
        required_angle_count = 361
        incomplete_freqs = []
        
        for freq, data in freq_data_map.items():
            if len(data) != required_angle_count:
                incomplete_freqs.append(f"频率 {freq} GHz: 期望 {required_angle_count} 行，实际 {len(data)} 行")
        
        if incomplete_freqs:
            raise ValueError(f"{filename}: 数据不完整\n  " + "\n  ".join(incomplete_freqs))
        
        # 构建角度数组（0-359度，共360个点）
        angles = np.linspace(0, 359, 360)
        
        # 构建数据数组（去除360度点）
        num_angles = 360
        data_array = np.zeros((num_freqs, num_angles))
        
        for i, freq in enumerate(sorted_freqs):
            data = freq_data_map[freq]
            # 取前360个点（去除360度点）
            data_array[i, :] = np.array(data[:num_angles])
        
        return np.array(sorted_freqs), data_array, angles
    
    def analyze_frequency_info(self, frequencies):
        """
        分析频率信息，返回格式化的描述字符串
        支持分段描述频率间隔变化
        """
        if len(frequencies) == 0:
            return "   无频率数据"
        
        freq_str = []
        freq_str.append(f"   频率点数: {len(frequencies)}")
        freq_str.append(f"   起始频率: {frequencies[0]:.6f} GHz")
        freq_str.append(f"   结束频率: {frequencies[-1]:.6f} GHz")
        
        if len(frequencies) > 1:
            # 计算频率间隔
            intervals = np.diff(frequencies)
            
            # 检查是否有多个不同的间隔
            unique_intervals = np.unique(np.round(intervals, 10))
            
            if len(unique_intervals) == 1:
                freq_str.append(f"   频率间隔: {unique_intervals[0]:.6f} GHz")
            else:
                freq_str.append("   频率间隔:")
                # 分段描述
                start_idx = 0
                current_interval = intervals[0]
                
                for i in range(1, len(intervals)):
                    if not np.isclose(intervals[i], current_interval, rtol=1e-9):
                        # 输出当前段
                        start_freq = frequencies[start_idx]
                        end_freq = frequencies[i]
                        freq_str.append(f"      [{start_freq:.6f} - {end_freq:.6f}] GHz: {current_interval:.6f} GHz")
                        start_idx = i
                        current_interval = intervals[i]
                
                # 输出最后一段
                start_freq = frequencies[start_idx]
                end_freq = frequencies[-1]
                freq_str.append(f"      [{start_freq:.6f} - {end_freq:.6f}] GHz: {current_interval:.6f} GHz")
        
        return "\n".join(freq_str)

    def draw_amplitude_pattern(self):
        """绘制天线幅度方向图（第一个频率点）"""
        self.figure.clear()
        
        if self.amplitude_data and self.frequencies is not None:
            # 使用第一个频率的数据绘制方向图
            ax = self.figure.add_subplot(111)
            
            colors = ['blue', 'red', 'green', 'orange', 'purple', 'cyan', 'magenta', 'brown']
            angles = np.linspace(0, 359, 360)
            
            for i, (antenna_id, (freqs, amp_values, _)) in enumerate(sorted(self.amplitude_data.items())):
                color = colors[i % len(colors)]
                # 取第一个频率的幅度数据
                if len(freqs) > 0 and len(amp_values) > 0:
                    ax.plot(angles, amp_values[0], linewidth=2, color=color, label=f'天线{antenna_id}')
            
            ax.set_title(f"天线幅度方向图 (频率: {self.frequencies[0]:.4f} GHz)", fontsize=14)
            ax.set_xlabel("角度 (度)")
            ax.set_ylabel("幅度 (dB)")
            ax.grid(True, linestyle='--')
            ax.set_xlim(0, 360)
            ax.legend()
        else:
            # 如果没有数据，显示提示
            ax = self.figure.add_subplot(111)
            ax.text(0.5, 0.5, '暂无幅度数据', ha='center', va='center', fontsize=14)
            ax.set_title("天线幅度方向图", fontsize=14)
        
        self.canvas.draw()

# ==========================================
# 程序启动入口
# ==========================================
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())