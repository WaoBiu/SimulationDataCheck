import sys
import os
import csv
import numpy as np
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QLabel, QPushButton, QFileDialog, 
                             QDialog, QTextEdit, QStackedWidget, QCheckBox, 
                             QComboBox, QSpinBox, QGroupBox, QMessageBox, QSizePolicy)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap, QFont
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
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
        self.current_plot_type = "amplitude"  # 当前绘图类型: "amplitude" 或 "phase"
        
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
        main_layout = QHBoxLayout()
        
        # 左侧控制面板
        self.control_panel = QWidget()
        self.control_panel.setFixedWidth(165)
        control_layout = QVBoxLayout()
        
        # ========== 天线控制区 ==========
        self.antenna_group = QGroupBox("天线")
        self.antenna_group.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        antenna_layout = QVBoxLayout()
        
        # 天线复选框列表（动态生成）
        self.antenna_checkboxes = {}
        
        # 单天线模式下的天线选择
        single_antenna_label = QLabel("选择天线:")
        single_antenna_label.setFont(QFont("Arial", 9))
        antenna_layout.addWidget(single_antenna_label)
        
        self.single_antenna_combo = QComboBox()
        self.single_antenna_combo.currentIndexChanged.connect(self.on_single_antenna_changed)
        self.single_antenna_combo.hide()
        antenna_layout.addWidget(self.single_antenna_combo)
        
        # 自动播放
        self.auto_play_checkbox = QCheckBox("自动播放")
        self.auto_play_checkbox.stateChanged.connect(self.on_auto_play_changed)
        self.auto_play_checkbox.hide()
        antenna_layout.addWidget(self.auto_play_checkbox)
        
        self.antenna_group.setLayout(antenna_layout)
        control_layout.addWidget(self.antenna_group)
        
        # ========== 频率控制区 ==========
        freq_group = QGroupBox("频率")
        freq_group.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        freq_layout = QVBoxLayout()
        
        # 频率选择
        freq_label = QLabel("选择频率:")
        freq_label.setFont(QFont("Arial", 9))
        freq_layout.addWidget(freq_label)
        
        self.freq_combo = QComboBox()
        self.freq_combo.currentIndexChanged.connect(self.on_frequency_changed)
        freq_layout.addWidget(self.freq_combo)
        
        # 频率范围（单天线模式）
        self.freq_range_checkbox = QCheckBox("全展示")
        self.freq_range_checkbox.setChecked(True)
        self.freq_range_checkbox.stateChanged.connect(self.on_freq_range_all_changed)
        self.freq_range_checkbox.hide()
        freq_layout.addWidget(self.freq_range_checkbox)
        
        # 起始频率（红色标签）
        self.start_freq_label = QLabel("<span style='color:red; font-weight:bold;'>起始频率</span>")
        self.start_freq_label.setFont(QFont("Arial", 9))
        self.start_freq_label.hide()
        freq_layout.addWidget(self.start_freq_label)
        
        self.start_freq_combo = QComboBox()
        self.start_freq_combo.currentIndexChanged.connect(self.on_start_freq_changed)
        self.start_freq_combo.hide()
        freq_layout.addWidget(self.start_freq_combo)
        
        # 终止频率（蓝色标签）
        self.end_freq_label = QLabel("<span style='color:blue; font-weight:bold;'>终止频率</span>")
        self.end_freq_label.setFont(QFont("Arial", 9))
        self.end_freq_label.hide()
        freq_layout.addWidget(self.end_freq_label)
        
        self.end_freq_combo = QComboBox()
        self.end_freq_combo.currentIndexChanged.connect(self.on_end_freq_changed)
        self.end_freq_combo.hide()
        freq_layout.addWidget(self.end_freq_combo)
        
        # 频率范围提示标签（隐藏，改用颜色区分）
        freq_range_hint = QLabel("")
        freq_range_hint.hide()
        freq_layout.addWidget(freq_range_hint)
        self.freq_range_hint = freq_range_hint
        
        freq_group.setLayout(freq_layout)
        control_layout.addWidget(freq_group)
        
        # ========== 图像控制区 ==========
        plot_group = QGroupBox("图像")
        plot_group.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        plot_layout = QVBoxLayout()
        
        # 线条粗细
        line_width_label = QLabel("线条粗细:")
        line_width_label.setFont(QFont("Arial", 9))
        plot_layout.addWidget(line_width_label)
        
        self.line_width_spin = QSpinBox()
        self.line_width_spin.setRange(1, 10)
        self.line_width_spin.setValue(2)
        self.line_width_spin.setSuffix(" px")
        self.line_width_spin.valueChanged.connect(self.update_plot)
        plot_layout.addWidget(self.line_width_spin)
        
        plot_group.setLayout(plot_layout)
        control_layout.addWidget(plot_group)
        
        # 拉伸填充（让三个大框靠近顶部，重新导入按钮靠近底部）
        control_layout.addStretch(1)
        
        # ========== 底部按钮 ==========
        # 重新导入按钮（红色显示，放在最底部）
        self.btn_back = QPushButton("重新导入")
        self.btn_back.setStyleSheet("background-color: #f44336; color: white;")
        self.btn_back.clicked.connect(self.on_back_clicked)
        self.btn_back.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        control_layout.addWidget(self.btn_back)
        
        self.control_panel.setLayout(control_layout)
        main_layout.addWidget(self.control_panel)
        
        # 右侧绘图区域
        plot_area = QWidget()
        plot_layout = QVBoxLayout()
        
        # 创建 Matplotlib 画布
        self.figure = Figure()
        self.canvas = FigureCanvas(self.figure)
        
        # 添加导航工具栏（支持缩放、拖拽等）
        self.toolbar = NavigationToolbar(self.canvas, self.plot_page)
        # 修改工具栏按钮的tooltip为中文
        self.set_toolbar_tooltips()
        plot_layout.addWidget(self.toolbar)
        
        plot_layout.addWidget(self.canvas)
        
        # 模式切换按钮
        btn_layout = QHBoxLayout()
        self.btn_amplitude = QPushButton("幅度方向图")
        self.btn_phase = QPushButton("相位方向图")
        self.btn_single_antenna = QPushButton("单天线多频率")
        self.btn_amplitude.setStyleSheet("background-color: #4CAF50; color: white;")
        self.btn_amplitude.clicked.connect(self.on_amplitude_clicked)
        self.btn_phase.clicked.connect(self.on_phase_clicked)
        self.btn_single_antenna.clicked.connect(self.on_single_antenna_clicked)
        btn_layout.addStretch(1)
        btn_layout.addWidget(self.btn_amplitude)
        btn_layout.addWidget(self.btn_phase)
        btn_layout.addWidget(self.btn_single_antenna)
        btn_layout.addStretch(1)
        plot_layout.addLayout(btn_layout)
        
        plot_area.setLayout(plot_layout)
        main_layout.addWidget(plot_area)
        
        # 当前显示模式和频率索引
        self.current_plot_mode = 'amplitude'
        self.current_freq_index = 0
        self.current_single_antenna = 1
        
        self.plot_page.setLayout(main_layout)
        self.stacked_widget.addWidget(self.plot_page)
    
    def update_antenna_checkboxes(self):
        """根据读取的天线数据动态更新天线选择面板"""
        # 清除现有复选框
        for cb in self.antenna_checkboxes.values():
            cb.deleteLater()
        self.antenna_checkboxes.clear()
        
        # 获取天线组框的布局
        antenna_layout = self.antenna_group.layout()
        
        # 动态添加天线复选框（插入到全选/全不选按钮之后，单天线选择之前）
        for n in range(1, self.antenna_count + 1):
            cb = QCheckBox(f"天线{n}")
            cb.setChecked(True)
            cb.stateChanged.connect(self.on_antenna_checkbox_changed)
            self.antenna_checkboxes[n] = cb
            # 插入到索引2的位置（全选/全不选按钮之后）
            antenna_layout.insertWidget(2, cb)
    
    def set_toolbar_tooltips(self):
        """将工具栏按钮的英文tooltip改为中文"""
        for action in self.toolbar.actions():
            text = action.text()
            if text == 'Home':
                action.setToolTip('重置视图')
            elif text == 'Back':
                action.setToolTip('上一视图')
            elif text == 'Forward':
                action.setToolTip('下一视图')
            elif text == 'Pan':
                action.setToolTip('拖拽图像')
            elif text == 'Zoom':
                action.setToolTip('缩放')
            elif text == 'Zoom In':
                action.setToolTip('放大')
            elif text == 'Zoom Out':
                action.setToolTip('缩小')
            elif text == 'Subplots':
                action.setToolTip('配置子图')
            elif text == 'Save':
                action.setToolTip('保存图像')
    
    def update_frequency_combo(self):
        """更新频率下拉框"""
        self.freq_combo.clear()
        if self.frequencies is not None:
            for i, freq in enumerate(self.frequencies):
                self.freq_combo.addItem(f"{freq:.6f} GHz", userData=i)
            # 默认选择第一个频率
            self.current_freq_index = 0
            self.freq_combo.setCurrentIndex(0)
    
    def select_all_antennas(self):
        """全选所有天线"""
        for cb in self.antenna_checkboxes.values():
            cb.setChecked(True)
        self.update_plot()
    
    def deselect_all_antennas(self):
        """全不选所有天线"""
        for cb in self.antenna_checkboxes.values():
            cb.setChecked(False)
        self.update_plot()
    
    def on_antenna_checkbox_changed(self, state):
        """天线复选框状态变化时更新图表"""
        self.update_plot()
    
    def on_frequency_changed(self, index):
        """频率下拉框变化时更新图表"""
        if index >= 0 and self.frequencies is not None:
            self.current_freq_index = index
            self.update_plot()
    
    def update_single_antenna_combo(self):
        """更新单天线模式的天线选择下拉框"""
        self.single_antenna_combo.clear()
        for n in range(1, self.antenna_count + 1):
            self.single_antenna_combo.addItem(f"天线{n}", userData=n)
        self.current_single_antenna = 1
        self.single_antenna_combo.setCurrentIndex(0)
    
    def on_single_antenna_changed(self, index):
        """单天线模式下天线选择变化时更新图表"""
        if index >= 0:
            self.current_single_antenna = self.single_antenna_combo.itemData(index)
            self.update_plot()
    
    def on_single_antenna_clicked(self):
        """单天线多频率模式按钮点击事件"""
        self.current_plot_mode = 'single_antenna'
        self.btn_single_antenna.setStyleSheet("background-color: #4CAF50; color: white;")
        self.btn_amplitude.setStyleSheet("")
        self.btn_phase.setStyleSheet("")
        # 显示单天线相关控件，隐藏多天线相关控件
        self.single_antenna_combo.show()
        self.auto_play_checkbox.show()
        self.freq_range_checkbox.show()
        # 更新频率下拉框选项
        self.update_freq_range_combos()
        # 根据全展示状态显示/隐藏频率选择
        self.on_freq_range_all_changed(self.freq_range_checkbox.checkState())
        # 隐藏频率选择和天线复选框
        self.freq_combo.hide()
        for cb in self.antenna_checkboxes.values():
            cb.hide()
        self.update_plot()
    
    def on_back_clicked(self):
        """重新导入按钮点击事件，带确认对话框"""
        from PyQt5.QtWidgets import QMessageBox
        
        # 停止自动播放
        self.stop_auto_play()
        self.auto_play_checkbox.setChecked(False)
        
        # 显示确认对话框
        reply = QMessageBox.question(self, '确认重新导入', 
                                     '确定要重新导入数据吗？当前图表将被清空。',
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.No)
        
        if reply == QMessageBox.StandardButton.Yes:
            self.stacked_widget.setCurrentWidget(self.welcome_page)
    
    def on_auto_play_changed(self, state):
        """自动播放复选框状态变化事件"""
        # PyQt5 中 checkState() 返回整数，Qt.CheckState.Checked 就是整数值
        if state == Qt.CheckState.Checked:
            # 启动自动播放
            self.start_auto_play()
        else:
            # 停止自动播放
            self.stop_auto_play()
    
    def update_freq_range_combos(self):
        """更新频率范围选择的下拉框选项"""
        self.start_freq_combo.clear()
        self.end_freq_combo.clear()
        
        if self.frequencies is not None:
            for i, freq in enumerate(self.frequencies):
                self.start_freq_combo.addItem(f"{freq:.6f} GHz", userData=i)
                self.end_freq_combo.addItem(f"{freq:.6f} GHz", userData=i)
            
            # 默认选择第一个和最后一个频率
            self.start_freq_combo.setCurrentIndex(0)
            self.end_freq_combo.setCurrentIndex(len(self.frequencies) - 1)
    
    def on_freq_range_all_changed(self, state):
        """全展示复选框状态变化事件"""
        # PyQt5 中 checkState() 返回整数，Qt.CheckState.Checked 就是整数值
        if state == Qt.CheckState.Checked:
            # 全展示模式，隐藏起始/终止频率选择
            self.start_freq_label.hide()
            self.start_freq_combo.hide()
            self.end_freq_label.hide()
            self.end_freq_combo.hide()
            self.freq_range_hint.hide()
        else:
            # 范围选择模式，显示起始/终止频率选择和提示
            self.start_freq_label.show()
            self.start_freq_combo.show()
            self.end_freq_label.show()
            self.end_freq_combo.show()
            self.freq_range_hint.show()
        self.update_plot()
    
    def on_start_freq_changed(self, index):
        """起始频率变化时，更新终止频率的可选范围"""
        if self.freq_range_checkbox.isChecked():
            return
        
        # 终止频率不能小于起始频率
        end_count = self.end_freq_combo.count()
        for i in range(end_count):
            # 小于起始频率的选项设为不可选，但仍显示
            self.end_freq_combo.model().item(i).setEnabled(i >= index)
        
        # 如果当前终止频率小于新的起始频率，自动调整
        current_end_idx = self.end_freq_combo.currentIndex()
        if current_end_idx < index:
            self.end_freq_combo.setCurrentIndex(index)
        
        self.update_plot()
    
    def on_end_freq_changed(self, index):
        """终止频率变化时，更新起始频率的可选范围"""
        if self.freq_range_checkbox.isChecked():
            return
        
        # 起始频率不能大于终止频率
        start_count = self.start_freq_combo.count()
        for i in range(start_count):
            # 大于终止频率的选项设为不可选，但仍显示
            self.start_freq_combo.model().item(i).setEnabled(i <= index)
        
        # 如果当前起始频率大于新的终止频率，自动调整
        current_start_idx = self.start_freq_combo.currentIndex()
        if current_start_idx > index:
            self.start_freq_combo.setCurrentIndex(index)
        
        self.update_plot()
    
    def get_selected_freq_indices(self):
        """获取当前选择的频率范围索引"""
        if self.freq_range_checkbox.isChecked():
            # 全展示模式，返回所有频率索引
            return list(range(len(self.frequencies)))
        else:
            # 范围选择模式，返回起始到终止的频率索引
            start_idx = self.start_freq_combo.currentIndex()
            end_idx = self.end_freq_combo.currentIndex()
            # 确保起始不大于终止
            if start_idx > end_idx:
                start_idx, end_idx = end_idx, start_idx
            return list(range(start_idx, end_idx + 1))
    
    def start_auto_play(self):
        """启动自动播放定时器"""
        from PyQt5.QtCore import QTimer
        self.auto_play_timer = QTimer()
        self.auto_play_timer.timeout.connect(self.auto_switch_antenna)
        self.auto_play_timer.start(500)  # 每隔0.5秒切换一次
    
    def stop_auto_play(self):
        """停止自动播放定时器"""
        if hasattr(self, 'auto_play_timer'):
            self.auto_play_timer.stop()
            del self.auto_play_timer
    
    def auto_switch_antenna(self):
        """自动切换到下一个天线"""
        if self.current_plot_mode != 'single_antenna':
            self.auto_play_checkbox.setChecked(False)
            return
        
        current_idx = self.single_antenna_combo.currentIndex()
        max_idx = self.single_antenna_combo.count() - 1
        
        # 循环切换
        next_idx = (current_idx + 1) % (max_idx + 1)
        self.single_antenna_combo.setCurrentIndex(next_idx)

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
            # 用户点击了"继续" -> 刷新窗口显示图表
            self.current_plot_mode = "amplitude"
            self.update_antenna_checkboxes()
            self.update_frequency_combo()
            self.update_single_antenna_combo()
            self.update_plot()
            self.stacked_widget.setCurrentWidget(self.plot_page)
        else:
            # 用户点击了"退出"或关闭了对话框 -> 什么都不做，留在原页面
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
        num_angles = 361  # 保留完整的361个点（0-360度）
        
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
        每个频率有361行数据（0-360度），保留所有361个点
        返回: (frequencies, data_array, angles)
            frequencies: 唯一频率数组
            data_array: [频率][角度] 的数据数组（361个角度）
            angles: 角度数组（361个，0-360度）
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
        
        # 构建角度数组（0-360度，共361个点）
        num_angles = 361
        angles = np.linspace(0, 360, num_angles)
        
        # 构建数据数组（保留所有361个点）
        data_array = np.zeros((num_freqs, num_angles))
        
        for i, freq in enumerate(sorted_freqs):
            data = freq_data_map[freq]
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
        """绘制天线幅度方向图（当前选择的频率点）"""
        self.figure.clear()

        if self.amplitude_data and self.frequencies is not None:
            ax = self.figure.add_subplot(111)

            colors = ['blue', 'red', 'green', 'orange', 'purple', 'cyan', 'magenta', 'brown']
            # 转换角度坐标：从正南(-180)到正北(0)到正南(180)，顺时针旋转
            angles_new = np.linspace(-180, 180, 361)

            # 获取选中的天线
            selected_antennas = [n for n, cb in self.antenna_checkboxes.items() if cb.isChecked()]

            # 获取当前频率索引
            freq_idx = min(self.current_freq_index, len(self.frequencies) - 1)

            # 获取线条粗细
            line_width = self.line_width_spin.value()
            
            for antenna_id in selected_antennas:
                if antenna_id in self.amplitude_data:
                    freqs, amp_values, _ = self.amplitude_data[antenna_id]
                    color = colors[(antenna_id - 1) % len(colors)]
                    if len(freqs) > 0 and len(amp_values) > 0 and freq_idx < len(amp_values):
                        # 转换数据：原始数据0度是正北，需要将180度（正南）放在开头
                        data = amp_values[freq_idx]
                        data_reordered = np.concatenate([data[180:], data[:180]])
                        ax.plot(angles_new, data_reordered, linewidth=line_width, color=color, label=f'天线{antenna_id}')

            ax.set_title(f"天线幅度方向图 (频率: {self.frequencies[freq_idx]:.4f} GHz)", fontsize=14)
            ax.set_xlabel("角度 (度)")
            ax.set_ylabel("幅度 (dB)")
            ax.grid(True, linestyle='--')
            ax.set_xlim(-180, 180)
            # 设置x轴刻度
            ax.set_xticks([-180, -135, -90, -45, 0, 45, 90, 135, 180])
            # 图例置于下方
            ax.legend(loc='upper center', bbox_to_anchor=(0.5, -0.15), ncol=4)
            # 调整布局以容纳图例
            self.figure.tight_layout(pad=2.0)
        else:
            ax = self.figure.add_subplot(111)
            ax.text(0.5, 0.5, '暂无幅度数据', ha='center', va='center', fontsize=14)
            ax.set_title("天线幅度方向图", fontsize=14)

        self.canvas.draw()

    def draw_phase_pattern(self):
        """绘制天线相位方向图（当前选择的频率点）"""
        self.figure.clear()

        if self.phase_data and self.frequencies is not None:
            ax = self.figure.add_subplot(111)

            colors = ['blue', 'red', 'green', 'orange', 'purple', 'cyan', 'magenta', 'brown']
            # 转换角度坐标：从正南(-180)到正北(0)到正南(180)，顺时针旋转
            angles_new = np.linspace(-180, 180, 361)

            # 获取选中的天线
            selected_antennas = [n for n, cb in self.antenna_checkboxes.items() if cb.isChecked()]

            # 获取当前频率索引
            freq_idx = min(self.current_freq_index, len(self.frequencies) - 1)

            # 获取线条粗细
            line_width = self.line_width_spin.value()
            
            for antenna_id in selected_antennas:
                if antenna_id in self.phase_data:
                    freqs, phase_values, _ = self.phase_data[antenna_id]
                    color = colors[(antenna_id - 1) % len(colors)]
                    if len(freqs) > 0 and len(phase_values) > 0 and freq_idx < len(phase_values):
                        # 转换数据：原始数据0度是正北，需要将180度（正南）放在开头
                        data = phase_values[freq_idx]
                        data_reordered = np.concatenate([data[180:], data[:180]])
                        ax.plot(angles_new, data_reordered, linewidth=line_width, color=color, label=f'天线{antenna_id}')

            ax.set_title(f"天线相位方向图 (频率: {self.frequencies[freq_idx]:.4f} GHz)", fontsize=14)
            ax.set_xlabel("角度 (度)")
            ax.set_ylabel("相位 (度)")
            ax.grid(True, linestyle='--')
            ax.set_xlim(-180, 180)
            # 设置x轴刻度
            ax.set_xticks([-180, -135, -90, -45, 0, 45, 90, 135, 180])
            # 图例置于下方
            ax.legend(loc='upper center', bbox_to_anchor=(0.5, -0.15), ncol=4)
            # 调整布局以容纳图例
            self.figure.tight_layout(pad=2.0)
        else:
            ax = self.figure.add_subplot(111)
            ax.text(0.5, 0.5, '暂无相位数据', ha='center', va='center', fontsize=14)
            ax.set_title("天线相位方向图", fontsize=14)

        self.canvas.draw()

    def update_plot(self):
        """根据当前绘图类型更新图表"""
        if self.current_plot_mode == "amplitude":
            self.draw_amplitude_pattern()
        elif self.current_plot_mode == "phase":
            self.draw_phase_pattern()
        elif self.current_plot_mode == "single_antenna":
            self.draw_single_antenna_pattern()

    def on_amplitude_clicked(self):
        """幅度按钮点击事件"""
        self.current_plot_mode = "amplitude"
        self.btn_amplitude.setStyleSheet("background-color: #4CAF50; color: white;")
        self.btn_phase.setStyleSheet("")
        self.btn_single_antenna.setStyleSheet("")
        # 停止自动播放
        self.stop_auto_play()
        self.auto_play_checkbox.setChecked(False)
        # 恢复显示频率选择和天线复选框，隐藏单天线相关控件
        self.single_antenna_combo.hide()
        self.auto_play_checkbox.hide()
        self.freq_range_checkbox.hide()
        self.start_freq_combo.hide()
        self.end_freq_combo.hide()
        self.freq_combo.show()
        for cb in self.antenna_checkboxes.values():
            cb.show()
        self.update_plot()

    def on_phase_clicked(self):
        """相位按钮点击事件"""
        self.current_plot_mode = "phase"
        self.btn_phase.setStyleSheet("background-color: #4CAF50; color: white;")
        self.btn_amplitude.setStyleSheet("")
        self.btn_single_antenna.setStyleSheet("")
        # 停止自动播放
        self.stop_auto_play()
        self.auto_play_checkbox.setChecked(False)
        # 恢复显示频率选择和天线复选框，隐藏单天线相关控件
        self.single_antenna_combo.hide()
        self.auto_play_checkbox.hide()
        self.freq_range_checkbox.hide()
        self.start_freq_combo.hide()
        self.end_freq_combo.hide()
        self.freq_combo.show()
        for cb in self.antenna_checkboxes.values():
            cb.show()
        self.update_plot()
    
    def draw_single_antenna_pattern(self):
        """绘制单天线多频率方向图，支持双击高亮显示频率"""
        self.figure.clear()
        
        if self.amplitude_data and self.frequencies is not None:
            # 创建子图（取消colorbar，改用图例）
            fig = self.figure
            ax = fig.add_subplot(111)
            
            # 角度坐标转换
            angles_new = np.linspace(-180, 180, 361)
            
            # 获取当前选中的天线
            antenna_id = self.current_single_antenna
            
            # 获取线条粗细
            line_width = self.line_width_spin.value()
            
            if antenna_id in self.amplitude_data:
                freqs, amp_values, _ = self.amplitude_data[antenna_id]
                
                # 为每条曲线记录频率信息（用于双击显示）
                self.plot_lines = []
                
                # 获取用户选择的频率范围
                selected_indices = self.get_selected_freq_indices()
                
                for freq_idx in selected_indices:
                    if freq_idx < len(amp_values):
                        freq = self.frequencies[freq_idx]
                        data = amp_values[freq_idx]
                        data_reordered = np.concatenate([data[180:], data[:180]])
                        
                        # 使用默认颜色
                        line, = ax.plot(angles_new, data_reordered, linewidth=line_width, alpha=0.7)
                        line.freq_info = f"{freq:.6f} GHz"
                        line.freq_value = freq
                        self.plot_lines.append(line)
            
            ax.set_title(f"天线{antenna_id} - 多频率幅度方向图", fontsize=14)
            ax.set_xlabel("角度 (度)")
            ax.set_ylabel("幅度 (dB)")
            ax.grid(True, linestyle='--')
            ax.set_xlim(-180, 180)
            ax.set_xticks([-180, -135, -90, -45, 0, 45, 90, 135, 180])
            
            # 双击提示
            ax.text(0.02, 0.98, '双击曲线高亮显示（最多5条）', transform=ax.transAxes, 
                   fontsize=10, verticalalignment='top', color='gray')
            
            # 初始化高亮相关变量
            self.highlighted_lines = []
            self.highlight_texts = []
            
            # 连接双击事件
            self.canvas.mpl_connect('button_press_event', self.on_double_click)
        else:
            ax = self.figure.add_subplot(111)
            ax.text(0.5, 0.5, '暂无数据', ha='center', va='center', fontsize=14)
            ax.set_title(f"天线{antenna_id} - 多频率幅度方向图", fontsize=14)
        
        self.canvas.draw()
    
    def on_double_click(self, event):
        """双击曲线高亮显示频率信息（最多5条，超过后自动取消最早的）"""
        if self.current_plot_mode != 'single_antenna':
            return
        
        if event.dblclick:
            ax = self.figure.axes[0]
            
            # 检查是否点击了已高亮的曲线（取消高亮）
            for i, (line, text) in enumerate(self.highlighted_lines):
                if line.contains(event)[0]:
                    # 取消高亮
                    line.set_linewidth(self.line_width_spin.value())
                    line.set_alpha(0.7)
                    text.remove()
                    del self.highlighted_lines[i]
                    self.canvas.draw()
                    return
            
            # 如果已经有5条高亮，取消最早的一条
            if len(self.highlighted_lines) >= 5:
                # 获取最早高亮的曲线并取消
                old_line, old_text = self.highlighted_lines.pop(0)
                old_line.set_linewidth(self.line_width_spin.value())
                old_line.set_alpha(0.7)
                old_text.remove()
            
            # 查找点击的曲线并高亮
            for line in self.plot_lines:
                if line.contains(event)[0]:
                    freq_info = getattr(line, 'freq_info', '未知频率')
                    
                    # 高亮曲线
                    line.set_linewidth(self.line_width_spin.value() + 2)
                    line.set_alpha(1.0)
                    
                    # 在曲线位置显示频率信息
                    text = ax.text(event.xdata, event.ydata, freq_info,
                                   bbox=dict(facecolor='yellow', alpha=0.8),
                                   fontsize=12)
                    
                    self.highlighted_lines.append((line, text))
                    self.canvas.draw()
                    break

# ==========================================
# 程序启动入口
# ==========================================
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())