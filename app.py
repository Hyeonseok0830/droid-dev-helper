import sys
import os
import subprocess
import html
import shutil
import json
from datetime import datetime
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QComboBox, QTextEdit, QGridLayout,
    QMessageBox, QDialog, QFileDialog, QFormLayout, QDialogButtonBox,
    QCheckBox, QScrollArea, QStatusBar, QTableView, QHeaderView, QAbstractItemView,
    QMenu
)
from PyQt5.QtCore import QThread, pyqtSignal, Qt, QTimer, QAbstractTableModel, QModelIndex
from PyQt5.QtGui import QTextCursor, QBrush, QColor, QFont, QIcon


import traceback

def resource_path(relative_path):
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)

def exception_hook(exctype, value, tb):
    tb_lines = traceback.format_exception(exctype, value, tb)
    error_msg = "".join(tb_lines)
    try:
        with open("crash_report.txt", "w", encoding="utf-8") as f:
            f.write(error_msg)
    except Exception:
        pass
    try:
        app = QApplication.instance()
        if not app:
            app = QApplication(sys.argv)
        QMessageBox.critical(None, "오류 발생 (Crash Report)", f"애플리케이션 실행 중 오류가 발생했습니다.\n\n{error_msg}")
    except Exception:
        pass
    sys.exit(1)

sys.excepthook = exception_hook

# 윈도우 환경에서 콘솔 창(cmd)이 뜨는 것을 완벽하게 숨기는 subprocess 래퍼 함수
def safe_subprocess_run(args, **kwargs):
    if os.name == 'nt':
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0 # SW_HIDE
        kwargs['startupinfo'] = startupinfo
    return subprocess.run(args, **kwargs)

def safe_subprocess_popen(args, **kwargs):
    if os.name == 'nt':
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0 # SW_HIDE
        kwargs['startupinfo'] = startupinfo
    return subprocess.Popen(args, **kwargs)

# 백그라운드 디바이스 실시간 감지 스레드 (메인 GUI 프리징 방지)
class DeviceDetectThread(QThread):
    devices_signal = pyqtSignal(dict)
    error_signal = pyqtSignal(str)

    def __init__(self, adb_path):
        super().__init__()
        self.adb_path = adb_path
        self.running = True

    def run(self):
        while self.running:
            if not self.adb_path:
                self.msleep(1000)
                continue
            try:
                # 5초 타임아웃, 윈도우 콘솔 숨김 처리 적용
                res = safe_subprocess_run(
                    [self.adb_path, 'devices', '-l'],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=5.0
                )
                if res.returncode == 0:
                    lines = res.stdout.strip().split('\n')[1:]
                    current_devices = {}
                    for line in lines:
                        if not line.strip():
                            continue
                        tokens = line.split()
                        if len(tokens) >= 2 and tokens[1] == 'device':
                            serial = tokens[0]
                            model = serial
                            for token in tokens[2:]:
                                if token.startswith('model:'):
                                    model = token.split(':')[1]
                                    break
                            current_devices[serial] = model
                    if self.running:
                        self.devices_signal.emit(current_devices)
                else:
                    if self.running:
                        self.error_signal.emit(res.stderr or "adb command error")
            except subprocess.TimeoutExpired:
                if self.running:
                    self.error_signal.emit("Timeout")
            except Exception as e:
                if self.running:
                    self.error_signal.emit(str(e))
            
            # 2.5초마다 체크
            self.msleep(2500)

    def stop(self):
        self.running = False

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')

# 1. Tool Path Auto-Detection Utility
def detect_tools():
    adb = shutil.which('adb')
    scrcpy = shutil.which('scrcpy')
    
    # Common fallback paths
    home = os.path.expanduser('~')
    adb_fallbacks = [
        '/usr/bin/adb',
        '/usr/local/bin/adb',
        os.path.join(home, 'Android/Sdk/platform-tools/adb'),
        '/home/hans/source2/Android/Sdk/platform-tools/adb'
    ]
    scrcpy_fallbacks = [
        '/usr/bin/scrcpy',
        '/usr/local/bin/scrcpy',
        '/snap/bin/scrcpy',
        '/flatpak/bin/scrcpy'
    ]
    
    if not adb:
        for path in adb_fallbacks:
            if os.path.exists(path) and os.access(path, os.X_OK):
                adb = path
                break
    if not scrcpy:
        for path in scrcpy_fallbacks:
            if os.path.exists(path) and os.access(path, os.X_OK):
                scrcpy = path
                break
                
    return adb or '', scrcpy or ''

def load_config():
    default_config = {
        'adb_path': '',
        'scrcpy_path': '',
        'max_size': '1024',
        'bit_rate': '4M',
        'max_fps': '60',
        'stay_awake': True,
        'turn_screen_off': False,
        'show_touches': False,
        'read_only': False
    }
    
    # Run auto-detect
    detected_adb, detected_scrcpy = detect_tools()
    default_config['adb_path'] = detected_adb
    default_config['scrcpy_path'] = detected_scrcpy
    
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
                # Merge defaults for missing keys
                for k, v in default_config.items():
                    if k not in config:
                        config[k] = v
                return config
        except Exception:
            return default_config
    return default_config

def save_config(config):
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"Error saving config: {e}")

# 2. Logcat Streamer Thread
class LogcatThread(QThread):
    new_log_signal = pyqtSignal(str)
    stopped_signal = pyqtSignal()

    def __init__(self, adb_path, serial):
        super().__init__()
        self.adb_path = adb_path
        self.serial = serial
        self.process = None
        self.running = False

    def run(self):
        self.running = True
        
        # Clear logcat cache first for the target device
        clear_cmd = [self.adb_path]
        if self.serial:
            clear_cmd.extend(['-s', self.serial])
        clear_cmd.extend(['logcat', '-c'])
        safe_subprocess_run(clear_cmd)
        
        # Spawn logcat process
        cmd = [self.adb_path]
        if self.serial:
            cmd.extend(['-s', self.serial])
        cmd.extend(['logcat', '-v', 'threadtime'])
        
        try:
            self.process = safe_subprocess_popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                errors='replace' # Gracefully handle non-UTF-8 characters in logs
            )
        except Exception as e:
            self.new_log_signal.emit(f"Logcat 시작 오류: {str(e)}")
            self.stopped_signal.emit()
            return
        
        while self.running and self.process.poll() is None:
            line = self.process.stdout.readline()
            if line:
                self.new_log_signal.emit(line)
            else:
                self.msleep(10)
        
        self.stopped_signal.emit()

    def stop(self):
        self.running = False
        if self.process:
            self.process.terminate()
            self.process.wait()
            self.process = None

# 3. Scrcpy Executer Thread
class ScrcpyThread(QThread):
    finished_signal = pyqtSignal(int)
    error_signal = pyqtSignal(str)

    def __init__(self, scrcpy_path, adb_path, serial, options):
        super().__init__()
        self.scrcpy_path = scrcpy_path
        self.adb_path = adb_path
        self.serial = serial
        self.options = options
        self.process = None

    def run(self):
        env = os.environ.copy()
        # Bind the exact adb path to scrcpy env to prevent version conflicts
        # Skip binding if using snap scrcpy (as snap is sandboxed and cannot access host adb)
        if 'snap' not in self.scrcpy_path:
            env['ADB'] = self.adb_path
        
        args = [self.scrcpy_path]
        if self.serial:
            args.extend(['--serial', self.serial])
            
        # Parse scrcpy options
        if self.options.get('max_size'):
            args.extend(['--max-size', str(self.options['max_size'])])
        if self.options.get('bit_rate'):
            args.extend(['--video-bit-rate', str(self.options['bit_rate'])])
        if self.options.get('max_fps'):
            args.extend(['--max-fps', str(self.options['max_fps'])])
        if self.options.get('stay_awake'):
            args.append('--stay-awake')
        if self.options.get('turn_screen_off'):
            args.append('--turn-screen-off')
        if self.options.get('show_touches'):
            args.append('--show-touches')
        if self.options.get('read_only'):
            args.append('--read-only')
            
        try:
            creationflags = 0
            if os.name == 'nt':
                creationflags = 0x08000000 # CREATE_NO_WINDOW
                
            self.process = subprocess.Popen(
                args,
                env=env,
                creationflags=creationflags
            )
            code = self.process.wait()
            self.finished_signal.emit(code)
        except FileNotFoundError:
            self.error_signal.emit("scrcpy 실행 파일을 찾을 수 없습니다. 경로 설정을 확인해주세요.")
        except Exception as e:
            self.error_signal.emit(f"scrcpy 실행 오류: {str(e)}")

    def stop(self):
        if self.process:
            self.process.terminate()
            self.process.wait()
            self.process = None

# 4. Background ADB Command Task Thread (Prevents UI Freezing)
class AdbTaskThread(QThread):
    finished_signal = pyqtSignal(bool, str)

    def __init__(self, command_args):
        super().__init__()
        self.command_args = command_args

    def run(self):
        try:
            res = safe_subprocess_run(
                self.command_args, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE, 
                text=True, 
                timeout=30.0
            )
            if res.returncode == 0:
                self.finished_signal.emit(True, res.stdout)
            else:
                self.finished_signal.emit(False, res.stderr or res.stdout)
        except subprocess.TimeoutExpired:
            self.finished_signal.emit(False, "명령어 실행 시간 초과 (30초)")
        except Exception as e:
            self.finished_signal.emit(False, str(e))

# 5. Settings Configuration Dialog
class SettingsDialog(QDialog):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config.copy()
        self.setWindowTitle("환경 설정")
        self.resize(560, 520)
        self.setup_ui()
        self.apply_style()

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(15)
        
        # Scroll Area for high DPI compatibility
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setStyleSheet("background-color: transparent;")
        
        scroll_content = QWidget()
        scroll_content.setStyleSheet("background-color: transparent;")
        form_layout = QFormLayout(scroll_content)
        form_layout.setContentsMargins(10, 10, 10, 10)
        form_layout.setSpacing(12)
        
        # ADB Path
        self.adb_edit = QLineEdit(self.config.get('adb_path', ''))
        btn_browse_adb = QPushButton("찾기")
        btn_browse_adb.setMinimumHeight(32)
        btn_browse_adb.setFixedWidth(75)
        btn_browse_adb.setStyleSheet("padding: 4px 8px; min-width: 50px;")
        btn_browse_adb.clicked.connect(self.browse_adb)
        adb_layout = QHBoxLayout()
        adb_layout.addWidget(self.adb_edit)
        adb_layout.addWidget(btn_browse_adb)
        form_layout.addRow("ADB 경로:", adb_layout)

        # Scrcpy Path
        self.scrcpy_edit = QLineEdit(self.config.get('scrcpy_path', ''))
        btn_browse_scrcpy = QPushButton("찾기")
        btn_browse_scrcpy.setMinimumHeight(32)
        btn_browse_scrcpy.setFixedWidth(75)
        btn_browse_scrcpy.setStyleSheet("padding: 4px 8px; min-width: 50px;")
        btn_browse_scrcpy.clicked.connect(self.browse_scrcpy)
        scrcpy_layout = QHBoxLayout()
        scrcpy_layout.addWidget(self.scrcpy_edit)
        scrcpy_layout.addWidget(btn_browse_scrcpy)
        form_layout.addRow("Scrcpy 경로:", scrcpy_layout)

        # Separator Line
        sep = QLabel()
        sep.setFrameShape(QLabel.HLine)
        sep.setStyleSheet("color: rgba(255,255,255,0.08);")
        form_layout.addRow("", sep)

        # Mirror Options Title
        options_title = QLabel("미러링 (scrcpy) 기본 옵션")
        options_title.setStyleSheet("font-weight: bold; font-size: 13px; color: #818cf8; margin-top: 5px;")
        form_layout.addRow("", options_title)

        # Max Resolution
        self.res_combo = QComboBox()
        self.res_combo.addItems(["제한 없음", "1920", "1440", "1024", "768", "480"])
        current_res = self.config.get('max_size', '1024')
        idx = self.res_combo.findText(current_res)
        self.res_combo.setCurrentIndex(idx if idx >= 0 else 3)
        form_layout.addRow("최대 해상도 (Max Size):", self.res_combo)

        # Bitrate
        self.bit_combo = QComboBox()
        self.bit_combo.addItems(["제한 없음", "16M", "8M", "4M", "2M", "1M"])
        current_bit = self.config.get('bit_rate', '4M')
        idx = self.bit_combo.findText(current_bit)
        self.bit_combo.setCurrentIndex(idx if idx >= 0 else 3)
        form_layout.addRow("비트레이트 (Bitrate):", self.bit_combo)

        # Max FPS
        self.fps_combo = QComboBox()
        self.fps_combo.addItems(["제한 없음", "60", "30", "15"])
        current_fps = self.config.get('max_fps', '60')
        idx = self.fps_combo.findText(current_fps)
        self.fps_combo.setCurrentIndex(idx if idx >= 0 else 1)
        form_layout.addRow("최대 FPS:", self.fps_combo)

        # Checkboxes Layout
        cb_grid = QGridLayout()
        cb_grid.setSpacing(12)
        
        self.cb_awake = QCheckBox("화면 켜짐 유지")
        self.cb_awake.setChecked(self.config.get('stay_awake', True))
        
        self.cb_screen_off = QCheckBox("모바일 화면 끄기")
        self.cb_screen_off.setChecked(self.config.get('turn_screen_off', False))
        
        self.cb_touches = QCheckBox("터치 피드백 표시")
        self.cb_touches.setChecked(self.config.get('show_touches', False))
        
        self.cb_read_only = QCheckBox("읽기 전용 모드")
        self.cb_read_only.setChecked(self.config.get('read_only', False))
        
        cb_grid.addWidget(self.cb_awake, 0, 0)
        cb_grid.addWidget(self.cb_screen_off, 0, 1)
        cb_grid.addWidget(self.cb_touches, 1, 0)
        cb_grid.addWidget(self.cb_read_only, 1, 1)
        
        form_layout.addRow("", cb_grid)
        
        scroll.setWidget(scroll_content)
        main_layout.addWidget(scroll)

        # Button Box
        button_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept_settings)
        button_box.rejected.connect(self.reject)
        
        # Enlarge button height for better Windows display
        btn_save = button_box.button(QDialogButtonBox.Save)
        if btn_save:
            btn_save.setMinimumHeight(36)
            btn_save.setText("저장")
        btn_cancel = button_box.button(QDialogButtonBox.Cancel)
        if btn_cancel:
            btn_cancel.setMinimumHeight(36)
            btn_cancel.setText("취소")
            
        main_layout.addWidget(button_box)

    def browse_adb(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "ADB 실행 파일 선택", "", "All Files (*)")
        if file_path:
            self.adb_edit.setText(file_path)

    def browse_scrcpy(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Scrcpy 실행 파일 선택", "", "All Files (*)")
        if file_path:
            self.scrcpy_edit.setText(file_path)

    def accept_settings(self):
        self.config['adb_path'] = self.adb_edit.text().strip()
        self.config['scrcpy_path'] = self.scrcpy_edit.text().strip()
        
        res = self.res_combo.currentText()
        self.config['max_size'] = '' if res == "제한 없음" else res
        
        bit = self.bit_combo.currentText()
        self.config['bit_rate'] = '' if bit == "제한 없음" else bit
        
        fps = self.fps_combo.currentText()
        self.config['max_fps'] = '' if fps == "제한 없음" else fps
        
        self.config['stay_awake'] = self.cb_awake.isChecked()
        self.config['turn_screen_off'] = self.cb_screen_off.isChecked()
        self.config['show_touches'] = self.cb_touches.isChecked()
        self.config['read_only'] = self.cb_read_only.isChecked()
        
        self.accept()

    def apply_style(self):
        self.setStyleSheet("""
            QDialog {
                background-color: #0f111a;
                color: #e5e7eb;
            }
            QLabel {
                color: #e5e7eb;
                font-size: 12px;
            }
            QLineEdit, QComboBox {
                background-color: #07080d;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 6px;
                color: #f3f4f6;
                padding: 6px 10px;
                font-size: 12px;
            }
            QLineEdit:focus {
                border: 1px solid #6366f1;
            }
            QCheckBox {
                color: #9ca3af;
                font-size: 12px;
            }
            QCheckBox:hover {
                color: #ffffff;
            }
            QPushButton {
                background-color: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 6px;
                color: #e5e7eb;
                padding: 8px 12px;
                font-size: 12px;
                min-width: 100px;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.1);
            }
        """)

import re

THREADTIME_RE = re.compile(
    r'^(\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d{3})\s+(\d+)\s+(\d+)\s+([VDIWEF])\s+(.*?)\s*:\s*(.*)$'
)

class LogTableModel(QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window = parent
        self.logs = []  # List of parsed log dicts
        self.headers = ['Line', 'Time', 'PID', 'TID', 'Level', 'Tag', 'Message']
        # Colors for LogNote Dark theme
        self.level_colors = {
            'V': QColor('#F0F0F0'),
            'D': QColor('#6C9876'),
            'I': QColor('#5084C4'),
            'W': QColor('#CB8742'),
            'E': QColor('#CD6C79'),
            'F': QColor('#ED3030')
        }
        self.bg_color = QColor('#151515')
        self.alt_bg_color = QColor('#1c1d22')
        self.line_num_fg = QColor('#A0A0A0')
        
        # Highlight colors matching LogNote dark style style indexes 0-9
        self.highlight_colors = [
            QColor('#E06000'), # 0
            QColor('#0090E0'), # 1
            QColor('#A0A000'), # 2
            QColor('#F070A0'), # 3
            QColor('#E0E0E0'), # 4
            QColor('#C00000'), # 5
            QColor('#20B0A0'), # 6
            QColor('#9050E0'), # 7
            QColor('#C0C060'), # 8
            QColor('#FFFFFF')  # 9
        ]
        
        # Setup monospace font
        self.font = QFont('D2Coding', 10)
        if not self.font.exactMatch():
            self.font = QFont('Fira Code', 10)
            if not self.font.exactMatch():
                self.font = QFont('JetBrains Mono', 10)
                if not self.font.exactMatch():
                    self.font.setFamily('monospace')
                    self.font.setStyleHint(QFont.Monospace)

    def rowCount(self, parent=QModelIndex()):
        return len(self.logs)

    def columnCount(self, parent=QModelIndex()):
        return len(self.headers)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.headers[section]
        return None

    def get_highlight_color(self, item):
        if not self.main_window:
            return None
        keyword_text = self.main_window.search_edit.text().strip()
        if not keyword_text:
            return None
            
        use_regex = self.main_window.cb_regex_filter.isChecked()
        
        # LogNote split by |
        terms = keyword_text.split('|')
        for term in terms:
            term = term.strip()
            if not term:
                continue
                
            color_idx = None
            match_text = term
            
            # Check if starts with # and a digit (0-9)
            if len(term) >= 2 and term[0] == '#' and term[1].isdigit():
                color_idx = int(term[1])
                match_text = term[2:]
                
            if not match_text:
                continue
                
            matched = False
            if use_regex:
                try:
                    import re
                    if (re.search(match_text, item['message'], re.IGNORECASE) or 
                        re.search(match_text, item['tag'], re.IGNORECASE)):
                        matched = True
                except Exception:
                    if match_text.lower() in item['tag'].lower() or match_text.lower() in item['message'].lower():
                        matched = True
            else:
                if match_text.lower() in item['tag'].lower() or match_text.lower() in item['message'].lower():
                    matched = True
                    
            if matched:
                if color_idx is not None and 0 <= color_idx < len(self.highlight_colors):
                    return self.highlight_colors[color_idx]
                else:
                    return QColor('#E06000') # Default highlight color
                    
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
            
        row = index.row()
        col = index.column()
        
        if row >= len(self.logs):
            return None
            
        item = self.logs[row]
        
        if role == Qt.DisplayRole:
            if col == 0:
                return str(row + 1)
            elif col == 1:
                return item['time']
            elif col == 2:
                return item['pid']
            elif col == 3:
                return item['tid']
            elif col == 4:
                return item['level']
            elif col == 5:
                return item['tag']
            elif col == 6:
                return item['message']
                
        elif role == Qt.ForegroundRole:
            if col > 0:
                hl_color = self.get_highlight_color(item)
                if hl_color:
                    # Return black text for light highlight backgrounds, white for dark ones
                    r = hl_color.red()
                    g = hl_color.green()
                    b = hl_color.blue()
                    brightness = r * 0.299 + g * 0.587 + b * 0.114
                    if brightness > 150:
                        return QBrush(QColor('#000000'))
                    else:
                        return QBrush(QColor('#FFFFFF'))
            
            level = item['level']
            color = self.level_colors.get(level, QColor('#F0F0F0'))
            if col == 0:
                return QBrush(self.line_num_fg)
            return QBrush(color)
            
        elif role == Qt.BackgroundRole:
            if col > 0:
                hl_color = self.get_highlight_color(item)
                if hl_color:
                    return QBrush(hl_color)
            
            if row % 2 == 0:
                return QBrush(self.bg_color)
            else:
                return QBrush(self.alt_bg_color)
                
        elif role == Qt.FontRole:
            return self.font
            
        elif role == Qt.TextAlignmentRole:
            if col in (0, 1, 2, 3, 4):
                return Qt.AlignCenter
            return Qt.AlignLeft | Qt.AlignVCenter
            
        return None

    def clear(self):
        self.beginResetModel()
        self.logs.clear()
        self.endResetModel()

    def set_logs(self, logs):
        self.beginResetModel()
        self.logs = list(logs)
        self.endResetModel()

    def append_log(self, item):
        self.beginInsertRows(QModelIndex(), len(self.logs), len(self.logs))
        self.logs.append(item)
        self.endInsertRows()
        
    def remove_first_row(self):
        if self.logs:
            self.beginRemoveRows(QModelIndex(), 0, 0)
            self.logs.pop(0)
            self.endRemoveRows()

# 6. Main GUI Application
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config = load_config()
        self.adb_path = self.config.get('adb_path', '')
        self.scrcpy_path = self.config.get('scrcpy_path', '')
        
        self.logcat_thread = None
        self.scrcpy_thread = None
        self.scrcpy_running = False
        self.layout_bounds_enabled = False
        self.show_touches_enabled = False
        self.connected_serials = set()
        self.active_tasks = []
        
        self.setWindowTitle('Droid Dev Helper')
        self.resize(1150, 800)
        self.setAcceptDrops(True)
        
        # Set Window Icon
        icon_path = resource_path('droid-dev-helper.png')
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        
        self.setup_ui()
        self.apply_dark_style()
        
        # Periodic check for device connections via background thread
        self.device_detect_thread = DeviceDetectThread(self.adb_path)
        self.device_detect_thread.devices_signal.connect(self.on_devices_detected)
        self.device_detect_thread.error_signal.connect(self.on_device_detect_error)
        self.device_detect_thread.start()

    def setup_ui(self):
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Sidebar wrapped in Scroll Area
        sidebar_scroll = QScrollArea()
        sidebar_scroll.setWidgetResizable(True)
        sidebar_scroll.setFixedWidth(340)
        sidebar_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        sidebar_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        sidebar_scroll.setObjectName('sidebar-scroll')
        
        sidebar = QWidget()
        sidebar.setObjectName('sidebar')
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(15, 15, 15, 15)
        sidebar_layout.setSpacing(15)
        
        # Logo Section with Settings Button
        logo_layout = QHBoxLayout()
        logo_label = QLabel('Droid Dev Helper')
        logo_label.setObjectName('logo')
        
        btn_settings = QPushButton('설정 ⚙')
        btn_settings.setObjectName('btn-settings')
        btn_settings.setFixedWidth(78)
        btn_settings.clicked.connect(self.open_settings)
        
        logo_layout.addWidget(logo_label)
        logo_layout.addWidget(btn_settings)
        sidebar_layout.addLayout(logo_layout)

        # 1. Device Info Panel
        device_box = QWidget()
        device_box.setObjectName('panel-box')
        device_layout = QVBoxLayout(device_box)
        device_layout.setSpacing(8)
        
        device_title = QLabel('장치 연결 상태')
        device_title.setObjectName('panel-title')
        device_layout.addWidget(device_title)
        
        self.status_label = QLabel('연결 대기 중...')
        self.status_label.setObjectName('status-pill')
        device_layout.addWidget(self.status_label)
        
        # Device dropdown
        self.device_combo = QComboBox()
        self.device_combo.currentIndexChanged.connect(self.on_device_selection_changed)
        device_layout.addWidget(self.device_combo)
        
        # Device details info
        self.info_label = QLabel("디바이스 정보 없음")
        self.info_label.setObjectName('device-info-lbl')
        self.info_label.setWordWrap(True)
        device_layout.addWidget(self.info_label)
        
        btn_refresh = QPushButton('연결 강제 확인')
        btn_refresh.clicked.connect(self.force_check_device_connection)
        device_layout.addWidget(btn_refresh)
        
        sidebar_layout.addWidget(device_box)

        # 2. Mirroring Control Panel
        mirror_box = QWidget()
        mirror_box.setObjectName('panel-box')
        mirror_layout = QVBoxLayout(mirror_box)
        
        mirror_title = QLabel('화면 미러링 (scrcpy)')
        mirror_title.setObjectName('panel-title')
        mirror_layout.addWidget(mirror_title)
        
        self.btn_mirror = QPushButton('미러링 시작')
        self.btn_mirror.setObjectName('btn-primary')
        self.btn_mirror.clicked.connect(self.toggle_mirroring)
        mirror_layout.addWidget(self.btn_mirror)
        
        sidebar_layout.addWidget(mirror_box)

        # 3. Dev Helper Shortcuts
        dev_box = QWidget()
        dev_box.setObjectName('panel-box')
        dev_layout = QVBoxLayout(dev_box)
        dev_layout.setSpacing(8)
        
        dev_title = QLabel('개발 편의 기능')
        dev_title.setObjectName('panel-title')
        dev_layout.addWidget(dev_title)
        
        self.btn_layout = QPushButton('레이아웃 경계 표시 켜기')
        self.btn_layout.clicked.connect(self.toggle_layout_bounds)
        dev_layout.addWidget(self.btn_layout)
        
        self.btn_touches = QPushButton('터치 피드백 표기 켜기')
        self.btn_touches.clicked.connect(self.toggle_show_touches)
        dev_layout.addWidget(self.btn_touches)
        
        btn_screenshot = QPushButton('화면 스크린샷 캡처')
        btn_screenshot.clicked.connect(self.take_screenshot)
        dev_layout.addWidget(btn_screenshot)
        
        btn_dev_opts = QPushButton('개발자 옵션 설정 열기')
        btn_dev_opts.clicked.connect(self.open_developer_options)
        dev_layout.addWidget(btn_dev_opts)
        
        # Package control layout
        pkg_title = QLabel('앱 패키지 관리')
        pkg_title.setStyleSheet("font-size: 11px; color: #a78bfa; font-weight: bold; margin-top: 5px;")
        dev_layout.addWidget(pkg_title)
        
        self.pkg_edit = QLineEdit()
        self.pkg_edit.setPlaceholderText('패키지명 (예: com.example.app)')
        dev_layout.addWidget(self.pkg_edit)
        
        pkg_btn_layout = QHBoxLayout()
        btn_clear_data = QPushButton('데이터 초기화')
        btn_clear_data.clicked.connect(self.clear_package_data)
        btn_uninstall = QPushButton('앱 삭제')
        btn_uninstall.clicked.connect(self.uninstall_package)
        pkg_btn_layout.addWidget(btn_clear_data)
        pkg_btn_layout.addWidget(btn_uninstall)
        dev_layout.addLayout(pkg_btn_layout)
        
        sidebar_layout.addWidget(dev_box)

        # 4. Hardware Keypad Simulator
        key_box = QWidget()
        key_box.setObjectName('panel-box')
        key_layout = QVBoxLayout(key_box)
        
        key_title = QLabel('디바이스 하드웨어 키 제어')
        key_title.setObjectName('panel-title')
        key_layout.addWidget(key_title)
        
        grid = QGridLayout()
        grid.setSpacing(6)
        
        btn_back = QPushButton('Back')
        btn_back.clicked.connect(lambda: self.send_keyevent(4))
        btn_home = QPushButton('Home')
        btn_home.clicked.connect(lambda: self.send_keyevent(3))
        btn_menu = QPushButton('Menu')
        btn_menu.clicked.connect(lambda: self.send_keyevent(82))
        btn_volup = QPushButton('Vol +')
        btn_volup.clicked.connect(lambda: self.send_keyevent(24))
        btn_power = QPushButton('Power')
        btn_power.clicked.connect(lambda: self.send_keyevent(26))
        btn_voldown = QPushButton('Vol -')
        btn_voldown.clicked.connect(lambda: self.send_keyevent(25))
        btn_recents = QPushButton('Recents')
        btn_recents.clicked.connect(lambda: self.send_keyevent(187))
        btn_enter = QPushButton('Enter')
        btn_enter.clicked.connect(lambda: self.send_keyevent(66))
        btn_del = QPushButton('Del')
        btn_del.clicked.connect(lambda: self.send_keyevent(67))
        
        grid.addWidget(btn_back, 0, 0)
        grid.addWidget(btn_home, 0, 1)
        grid.addWidget(btn_menu, 0, 2)
        grid.addWidget(btn_volup, 1, 0)
        grid.addWidget(btn_power, 1, 1)
        grid.addWidget(btn_voldown, 1, 2)
        grid.addWidget(btn_recents, 2, 0)
        grid.addWidget(btn_enter, 2, 1)
        grid.addWidget(btn_del, 2, 2)
        
        key_layout.addLayout(grid)
        sidebar_layout.addWidget(key_box)

        # 5. Text Input Injection
        input_box = QWidget()
        input_box.setObjectName('panel-box')
        input_layout = QVBoxLayout(input_box)
        input_layout.setSpacing(8)
        
        input_title = QLabel('텍스트 입력 주입')
        input_title.setObjectName('panel-title')
        input_layout.addWidget(input_title)
        
        input_form = QHBoxLayout()
        self.input_edit = QLineEdit()
        self.input_edit.setPlaceholderText('텍스트 입력 (영어/기호)...')
        self.input_edit.returnPressed.connect(self.send_input_text)
        
        btn_send = QPushButton('전송')
        btn_send.setObjectName('btn-primary')
        btn_send.clicked.connect(self.send_input_text)
        
        input_form.addWidget(self.input_edit)
        input_form.addWidget(btn_send)
        
        input_layout.addLayout(input_form)
        sidebar_layout.addWidget(input_box)
        
        # Drag and Drop Visual Zone
        self.drop_zone = QLabel('이곳에 APK/파일 드래그 & 드롭\n(APK: 자동 설치 | 파일: Download 전송)')
        self.drop_zone.setObjectName('drop-zone')
        self.drop_zone.setAlignment(Qt.AlignCenter)
        self.drop_zone.setWordWrap(True)
        sidebar_layout.addWidget(self.drop_zone)
        
        sidebar_layout.addStretch()
        sidebar_scroll.setWidget(sidebar)
        main_layout.addWidget(sidebar_scroll)

        # Right Panel - Logcat Console Board
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(20, 20, 20, 20)
        right_layout.setSpacing(12)
        
        # Header Row
        header_layout = QHBoxLayout()
        header_title = QLabel('실시간 Logcat 디버거')
        header_title.setObjectName('header-title')
        
        btn_clear = QPushButton('로그 비우기')
        btn_clear.clicked.connect(self.clear_logs)
        
        btn_save = QPushButton('로그 파일로 저장')
        btn_save.setObjectName('btn-primary')
        btn_save.clicked.connect(self.save_logs)
        
        header_layout.addWidget(header_title)
        header_layout.addStretch()
        header_layout.addWidget(btn_clear)
        header_layout.addWidget(btn_save)
        right_layout.addLayout(header_layout)

        # Logcat Filter Bar
        filter_layout = QHBoxLayout()
        filter_layout.setSpacing(10)
        
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText('로그 내용 키워드 검색...')
        self.search_edit.textChanged.connect(self.update_log_filter)
        
        self.tag_edit = QLineEdit()
        self.tag_edit.setPlaceholderText('태그 필터...')
        self.tag_edit.setFixedWidth(130)
        self.tag_edit.textChanged.connect(self.update_log_filter)
        
        self.level_combo = QComboBox()
        self.level_combo.addItems(['전체 등급 (ALL)', 'Verbose (V)', 'Debug (D)', 'Info (I)', 'Warning (W)', 'Error (E)'])
        self.level_combo.currentIndexChanged.connect(self.update_log_filter)
        
        self.cb_regex_filter = QCheckBox("Regex")
        self.cb_regex_filter.stateChanged.connect(self.update_log_filter)
        
        self.cb_autoscroll = QCheckBox("실시간 스크롤")
        self.cb_autoscroll.setChecked(True)
        
        filter_layout.addWidget(self.search_edit, 3)
        filter_layout.addWidget(self.tag_edit, 2)
        filter_layout.addWidget(self.level_combo, 1)
        filter_layout.addWidget(self.cb_regex_filter)
        filter_layout.addWidget(self.cb_autoscroll)
        right_layout.addLayout(filter_layout)

        # Log Output Box
        self.log_table = QTableView()
        self.log_model = LogTableModel(self)
        self.log_table.setModel(self.log_model)
        self.log_table.setAlternatingRowColors(True)
        self.log_table.setShowGrid(True)
        self.log_table.verticalHeader().setVisible(False)
        self.log_table.horizontalHeader().setStretchLastSection(True)
        self.log_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.log_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        
        # Set selection behavior
        self.log_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.log_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        
        # Configure columns width
        # Line, Time, PID, TID, Level, Tag, Message
        self.log_table.setColumnWidth(0, 55)  # Line
        self.log_table.setColumnWidth(1, 140) # Time
        self.log_table.setColumnWidth(2, 60)  # PID
        self.log_table.setColumnWidth(3, 60)  # TID
        self.log_table.setColumnWidth(4, 50)  # Level
        self.log_table.setColumnWidth(5, 120) # Tag
        
        # Setup font for table headers
        header_font = QFont('D2Coding', 10)
        if not header_font.exactMatch():
            header_font = QFont('Fira Code', 10)
            if not header_font.exactMatch():
                header_font = QFont('JetBrains Mono', 10)
                if not header_font.exactMatch():
                    header_font.setFamily('monospace')
                    header_font.setStyleHint(QFont.Monospace)
        self.log_table.horizontalHeader().setFont(header_font)
        
        # Connect table signals for double-click filter and right-click context menu
        self.log_table.doubleClicked.connect(self.on_log_cell_double_clicked)
        self.log_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.log_table.customContextMenuRequested.connect(self.show_log_context_menu)
        
        right_layout.addWidget(self.log_table)

        main_layout.addWidget(right_panel)
        
        # Status Bar
        self.setStatusBar(QStatusBar(self))
        self.statusBar().showMessage('디바이스 검색 준비 완료.')

        self.all_log_lines = []

    # 7. Settings Handler
    def open_settings(self):
        dialog = SettingsDialog(self.config, self)
        if dialog.exec_() == QDialog.Accepted:
            self.config = dialog.config
            save_config(self.config)
            
            # Apply new paths
            self.adb_path = self.config.get('adb_path', '')
            self.scrcpy_path = self.config.get('scrcpy_path', '')
            
            # Update background thread's adb path
            if hasattr(self, 'device_detect_thread'):
                self.device_detect_thread.adb_path = self.adb_path
            
            # Restart logcat with new settings if device is selected
            self.on_device_selection_changed()
            self.statusBar().showMessage('설정이 저장 및 적용되었습니다.', 3000)

    # 8. Device Detection & Selection (Slots from Background Thread)
    def on_devices_detected(self, current_devices):
        # Avoid rebuilding drop-down if connected device set has not changed
        if set(current_devices.keys()) == self.connected_serials:
            return

        self.connected_serials = set(current_devices.keys())
        prev_selected = self.get_selected_device_serial()
        
        # Rebuild combobox
        self.device_combo.clear()
        
        if current_devices:
            for serial, model in current_devices.items():
                self.device_combo.addItem(f"{model} ({serial})", serial)
            
            # Restore previous selection if it's still connected
            index = self.device_combo.findData(prev_selected)
            if index >= 0:
                self.device_combo.setCurrentIndex(index)
            else:
                self.device_combo.setCurrentIndex(0)
            
            device_count = len(current_devices)
            self.status_label.setText(f'연결됨 ({device_count}개 장치)')
            self.status_label.setStyleSheet('color: #34c759; background: rgba(52, 199, 89, 0.1); padding: 6px 12px; border-radius: 8px; font-weight: bold;')
            self.enable_controls(True)
        else:
            self.status_label.setText('연결된 장치 없음')
            self.status_label.setStyleSheet('color: #ff3b30; background: rgba(255, 59, 48, 0.1); padding: 6px 12px; border-radius: 8px; font-weight: bold;')
            self.info_label.setText("디바이스 정보 없음")
            self.enable_controls(False)
            self.stop_logcat_stream()

    def on_device_detect_error(self, err_msg):
        if err_msg == "Timeout":
            self.status_label.setText('연결 대기 중 (시간 초과)')
            self.status_label.setStyleSheet('color: #ff9f0a; background: rgba(255, 159, 10, 0.1); padding: 6px 12px; border-radius: 8px; font-weight: bold;')
            self.statusBar().showMessage("디바이스 연결 응답 시간 초과 (5초)", 3000)
        else:
            self.status_label.setText('오류 발생')
            self.statusBar().showMessage(f"디바이스 상태 확인 오류: {err_msg}", 3000)
            
        self.connected_serials.clear()
        self.device_combo.clear()
        self.enable_controls(False)
        self.stop_logcat_stream()
        self.info_label.setText("디바이스 정보 없음")

    def force_check_device_connection(self):
        if not self.adb_path:
            self.status_label.setText('ADB 경로 미지정 (설정 확인)')
            self.status_label.setStyleSheet('color: #ff9f0a; background: rgba(255, 159, 10, 0.1); padding: 6px 12px; border-radius: 8px; font-weight: bold;')
            self.enable_controls(False)
            return
            
        self.status_label.setText('기기 감지 중...')
        self.status_label.setStyleSheet('color: #a78bfa; background: rgba(167, 139, 250, 0.1); padding: 6px 12px; border-radius: 8px; font-weight: bold;')
        
        # Query devices asynchronously using AdbTaskThread to prevent UI freeze
        self.refresh_task = AdbTaskThread([self.adb_path, 'devices', '-l'])
        
        def on_refresh_finished(success, output):
            if success:
                lines = output.strip().split('\n')[1:]
                current_devices = {}
                for line in lines:
                    if not line.strip():
                        continue
                    tokens = line.split()
                    if len(tokens) >= 2 and tokens[1] == 'device':
                        serial = tokens[0]
                        model = serial
                        for token in tokens[2:]:
                            if token.startswith('model:'):
                                model = token.split(':')[1]
                                break
                        current_devices[serial] = model
                self.on_devices_detected(current_devices)
            else:
                self.on_device_detect_error(output)
                
        self.refresh_task.finished_signal.connect(on_refresh_finished)
        self.active_tasks.append(self.refresh_task)
        self.refresh_task.start()

    def get_selected_device_serial(self):
        index = self.device_combo.currentIndex()
        if index >= 0:
            return self.device_combo.itemData(index)
        return None

    def on_device_selection_changed(self):
        serial = self.get_selected_device_serial()
        if serial:
            self.stop_logcat_stream()
            self.all_log_lines.clear()
            self.log_model.clear()
            
            self.start_logcat_stream()
            self.update_device_details(serial)
            self.update_dev_features_ui_state(serial)
        else:
            self.stop_logcat_stream()
            self.all_log_lines.clear()
            self.log_model.clear()
            self.info_label.setText("디바이스 정보 없음")

    def update_device_details(self, serial):
        if not serial: return
        
        # Async fetch device information properties
        class DeviceInfoThread(QThread):
            info_signal = pyqtSignal(dict)
            
            def __init__(self, adb_path, serial):
                super().__init__()
                self.adb_path = adb_path
                self.serial = serial
                
            def run(self):
                try:
                    brand = safe_subprocess_run([self.adb_path, '-s', self.serial, 'shell', 'getprop', 'ro.product.brand'], stdout=subprocess.PIPE, text=True, timeout=0.8).stdout.strip().upper()
                    model = safe_subprocess_run([self.adb_path, '-s', self.serial, 'shell', 'getprop', 'ro.product.model'], stdout=subprocess.PIPE, text=True, timeout=0.8).stdout.strip()
                    version = safe_subprocess_run([self.adb_path, '-s', self.serial, 'shell', 'getprop', 'ro.build.version.release'], stdout=subprocess.PIPE, text=True, timeout=0.8).stdout.strip()
                    res_out = safe_subprocess_run([self.adb_path, '-s', self.serial, 'shell', 'wm', 'size'], stdout=subprocess.PIPE, text=True, timeout=0.8).stdout.strip()
                    resolution = res_out.split(':')[-1].strip() if res_out else "알 수 없음"
                    
                    details = f"제조사/모델: {brand} {model}\nOS 버전: Android {version}\n화면 해상도: {resolution}"
                    self.info_signal.emit({'success': True, 'text': details})
                except Exception as e:
                    self.info_signal.emit({'success': False, 'text': f"디바이스 속성 조회 실패: {str(e)}"})
                    
        self.info_thread = DeviceInfoThread(self.adb_path, serial)
        self.info_thread.info_signal.connect(lambda info: self.info_label.setText(info['text']))
        self.active_tasks.append(self.info_thread)
        self.info_thread.start()

    def update_dev_features_ui_state(self, serial):
        if not serial: return
        try:
            # Check Layout Bounds (debug.layout)
            res = safe_subprocess_run([self.adb_path, '-s', serial, 'shell', 'getprop', 'debug.layout'], stdout=subprocess.PIPE, text=True, timeout=0.8)
            layout_state = res.stdout.strip()
            self.layout_bounds_enabled = (layout_state == 'true')
            self.btn_layout.setText('레이아웃 경계 표시 끄기' if self.layout_bounds_enabled else '레이아웃 경계 표시 켜기')
            self.btn_layout.setStyleSheet('border-left: 4px solid #34c759; font-weight: bold;' if self.layout_bounds_enabled else '')

            # Check Show Touches (show_touches settings)
            res = safe_subprocess_run([self.adb_path, '-s', serial, 'shell', 'settings', 'get', 'system', 'show_touches'], stdout=subprocess.PIPE, text=True, timeout=0.8)
            touches_state = res.stdout.strip()
            self.show_touches_enabled = (touches_state == '1')
            self.btn_touches.setText('터치 피드백 표기 끄기' if self.show_touches_enabled else '터치 피드백 표기 켜기')
            self.btn_touches.setStyleSheet('border-left: 4px solid #34c759; font-weight: bold;' if self.show_touches_enabled else '')
        except Exception:
            pass

    def enable_controls(self, enabled):
        self.btn_mirror.setEnabled(enabled)
        self.btn_layout.setEnabled(enabled)
        self.btn_touches.setEnabled(enabled)
        self.input_edit.setEnabled(enabled)
        self.device_combo.setEnabled(True)

    # 9. Scrcpy Mirroring Integration
    def toggle_mirroring(self):
        if self.scrcpy_running:
            self.stop_mirroring()
        else:
            self.start_mirroring()

    def start_mirroring(self):
        serial = self.get_selected_device_serial()
        if not serial:
            QMessageBox.warning(self, "경고", "미러링할 디바이스가 선택되지 않았습니다.")
            return

        if not self.scrcpy_path:
            QMessageBox.warning(self, "경고", "Scrcpy 경로가 지정되지 않았습니다. 설정 ⚙ 창에서 경로를 설정해주세요.")
            return

        if self.scrcpy_thread is None:
            scrcpy_options = {
                'max_size': self.config.get('max_size', ''),
                'bit_rate': self.config.get('bit_rate', ''),
                'max_fps': self.config.get('max_fps', ''),
                'stay_awake': self.config.get('stay_awake', True),
                'turn_screen_off': self.config.get('turn_screen_off', False),
                'show_touches': self.config.get('show_touches', False),
                'read_only': self.config.get('read_only', False)
            }
            
            self.scrcpy_thread = ScrcpyThread(self.scrcpy_path, self.adb_path, serial, scrcpy_options)
            self.scrcpy_thread.finished_signal.connect(self.on_scrcpy_finished)
            self.scrcpy_thread.error_signal.connect(self.on_scrcpy_error)
            self.scrcpy_thread.start()
            self.scrcpy_running = True
            
            self.btn_mirror.setText('미러링 중지')
            self.btn_mirror.setObjectName('btn-danger')
            self.btn_mirror.style().unpolish(self.btn_mirror)
            self.btn_mirror.style().polish(self.btn_mirror)
            self.statusBar().showMessage('미러링 화면 실행 중...', 5000)

    def stop_mirroring(self):
        if self.scrcpy_thread:
            self.scrcpy_thread.stop()
            self.scrcpy_thread = None
            self.scrcpy_running = False
            
            self.btn_mirror.setText('미러링 시작')
            self.btn_mirror.setObjectName('btn-primary')
            self.btn_mirror.style().unpolish(self.btn_mirror)
            self.btn_mirror.style().polish(self.btn_mirror)
            self.statusBar().showMessage('미러링 화면이 중지되었습니다.', 3000)

    def on_scrcpy_finished(self, code):
        self.scrcpy_running = False
        self.scrcpy_thread = None
        self.btn_mirror.setText('미러링 시작')
        self.btn_mirror.setObjectName('btn-primary')
        self.btn_mirror.style().unpolish(self.btn_mirror)
        self.btn_mirror.style().polish(self.btn_mirror)
        self.statusBar().showMessage(f'미러링이 정상적으로 종료되었습니다. (종료 코드: {code})', 4000)

    def on_scrcpy_error(self, err_msg):
        self.scrcpy_running = False
        self.scrcpy_thread = None
        self.btn_mirror.setText('미러링 시작')
        self.btn_mirror.setObjectName('btn-primary')
        self.btn_mirror.style().unpolish(self.btn_mirror)
        self.btn_mirror.style().polish(self.btn_mirror)
        QMessageBox.critical(self, 'Scrcpy 실행 실패', err_msg)
        self.statusBar().showMessage('미러링 프로세스 실행 실패', 4000)

    # 10. Developer Shortcuts
    def toggle_layout_bounds(self):
        serial = self.get_selected_device_serial()
        if not serial: return
        try:
            res = safe_subprocess_run([self.adb_path, '-s', serial, 'shell', 'getprop', 'debug.layout'], stdout=subprocess.PIPE, text=True)
            current = res.stdout.strip()
            next_state = 'false' if current == 'true' else 'true'
            
            safe_subprocess_run([self.adb_path, '-s', serial, 'shell', 'setprop', 'debug.layout', next_state])
            safe_subprocess_run([self.adb_path, '-s', serial, 'shell', 'service', 'call', 'activity', '1599295570'])
            
            self.layout_bounds_enabled = (next_state == 'true')
            self.btn_layout.setText('레이아웃 경계 표시 끄기' if self.layout_bounds_enabled else '레이아웃 경계 표시 켜기')
            self.btn_layout.setStyleSheet('border-left: 4px solid #34c759; font-weight: bold;' if self.layout_bounds_enabled else '')
            self.statusBar().showMessage(f'레이아웃 경계 표시 변경: {next_state}', 2000)
        except Exception as e:
            QMessageBox.critical(self, '오류', f'명령어 실패: {str(e)}')

    def toggle_show_touches(self):
        serial = self.get_selected_device_serial()
        if not serial: return
        try:
            res = safe_subprocess_run([self.adb_path, '-s', serial, 'shell', 'settings', 'get', 'system', 'show_touches'], stdout=subprocess.PIPE, text=True)
            current = res.stdout.strip()
            next_state = '0' if current == '1' else '1'
            
            safe_subprocess_run([self.adb_path, '-s', serial, 'shell', 'settings', 'put', 'system', 'show_touches', next_state])
            
            self.show_touches_enabled = (next_state == '1')
            self.btn_touches.setText('터치 피드백 표기 끄기' if self.show_touches_enabled else '터치 피드백 표기 켜기')
            self.btn_touches.setStyleSheet('border-left: 4px solid #34c759; font-weight: bold;' if self.show_touches_enabled else '')
            self.statusBar().showMessage(f'터치 피드백 표기 변경: {"켜짐" if next_state == "1" else "꺼짐"}', 2000)
        except Exception as e:
            QMessageBox.critical(self, '오류', f'명령어 실패: {str(e)}')

    def send_keyevent(self, code):
        serial = self.get_selected_device_serial()
        if not serial: return
        safe_subprocess_popen([self.adb_path, '-s', serial, 'shell', 'input', 'keyevent', str(code)])

    def send_input_text(self):
        serial = self.get_selected_device_serial()
        if not serial: return
        text = self.input_edit.text()
        if not text: return
        
        # Space should be escaped as %s inside standard 'input text' commands
        sanitized = text.replace(' ', '%s')
        # Standard filter to avoid symbols breaking the bash syntax
        sanitized = ''.join(c for c in sanitized if c.isalnum() or c in '._-%$')
        
        safe_subprocess_popen([self.adb_path, '-s', serial, 'shell', 'input', 'text', sanitized])
        self.input_edit.clear()

    def open_developer_options(self):
        serial = self.get_selected_device_serial()
        if not serial: return
        try:
            safe_subprocess_popen([self.adb_path, '-s', serial, 'shell', 'am', 'start', '-a', 'android.settings.APPLICATION_DEVELOPMENT_SETTINGS'])
            self.statusBar().showMessage('개발자 옵션 설정 화면 진입', 2000)
        except Exception as e:
            QMessageBox.critical(self, '오류', f'명령어 실패: {str(e)}')

    def clear_package_data(self):
        serial = self.get_selected_device_serial()
        if not serial: return
        pkg = self.pkg_edit.text().strip()
        if not pkg:
            QMessageBox.warning(self, '경고', '앱 패키지명을 입력해주세요.')
            return
            
        cmd = [self.adb_path, '-s', serial, 'shell', 'pm', 'clear', pkg]
        self.statusBar().showMessage(f'앱 데이터 초기화 중: {pkg}...', 5000)
        self.run_background_adb_task(cmd, f"앱 {pkg} 데이터 초기화 완료", f"앱 {pkg} 데이터 초기화 실패")

    def uninstall_package(self):
        serial = self.get_selected_device_serial()
        if not serial: return
        pkg = self.pkg_edit.text().strip()
        if not pkg:
            QMessageBox.warning(self, '경고', '앱 패키지명을 입력해주세요.')
            return
            
        reply = QMessageBox.question(
            self, '앱 삭제 확인', f"정말로 패키지 {pkg} 앱을 디바이스에서 제거하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            cmd = [self.adb_path, '-s', serial, 'uninstall', pkg]
            self.statusBar().showMessage(f'앱 삭제 진행 중: {pkg}...', 5000)
            self.run_background_adb_task(cmd, f"앱 {pkg} 삭제 완료", f"앱 {pkg} 삭제 실패")

    def take_screenshot(self):
        serial = self.get_selected_device_serial()
        if not serial: return
        
        try:
            filename = f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            device_path = f"/sdcard/{filename}"
            
            # Select target desktop folder
            local_dir = os.path.expanduser('~/Desktop')
            if not os.path.exists(local_dir):
                local_dir_ko = os.path.expanduser('~/바탕화면')
                if os.path.exists(local_dir_ko):
                    local_dir = local_dir_ko
                else:
                    local_dir = os.path.expanduser('~')
            
            local_path = os.path.join(local_dir, filename)
            self.statusBar().showMessage('화면 캡처 파일 생성 중...', 5000)
            
            class ScreenshotThread(QThread):
                finished_signal = pyqtSignal(bool, str)
                
                def __init__(self, adb_path, serial, device_path, local_path):
                    super().__init__()
                    self.adb_path = adb_path
                    self.serial = serial
                    self.device_path = device_path
                    self.local_path = local_path
                    
                def run(self):
                    try:
                        # 1. Capture screen on android
                        res1 = safe_subprocess_run([self.adb_path, '-s', self.serial, 'shell', 'screencap', '-p', self.device_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                        if res1.returncode != 0:
                            self.finished_signal.emit(False, f"안드로이드 캡처 실패: {res1.stderr.decode('utf-8', errors='ignore')}")
                            return
                        # 2. Pull down to PC local path
                        res2 = safe_subprocess_run([self.adb_path, '-s', self.serial, 'pull', self.device_path, self.local_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                        if res2.returncode != 0:
                            self.finished_signal.emit(False, f"파일 가져오기 실패: {res2.stderr.decode('utf-8', errors='ignore')}")
                            return
                        # 3. Clean up android storage
                        safe_subprocess_run([self.adb_path, '-s', self.serial, 'shell', 'rm', self.device_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                        
                        self.finished_signal.emit(True, self.local_path)
                    except Exception as e:
                        self.finished_signal.emit(False, str(e))
            
            self.ss_thread = ScreenshotThread(self.adb_path, serial, device_path, local_path)
            self.ss_thread.finished_signal.connect(self.on_screenshot_finished)
            self.active_tasks.append(self.ss_thread)
            self.ss_thread.start()
            
        except Exception as e:
            QMessageBox.critical(self, '오류', f'스크린샷 실패: {str(e)}')

    def on_screenshot_finished(self, success, result):
        sender = self.sender()
        if sender in self.active_tasks:
            self.active_tasks.remove(sender)
            
        if success:
            self.statusBar().showMessage(f'스크린샷 캡처 완료: {result}', 4000)
            QMessageBox.information(self, '스크린샷 저장 성공', f'바탕화면에 스크린샷이 성공적으로 저장되었습니다:\n{result}')
        else:
            self.statusBar().showMessage('스크린샷 저장 오류', 4000)
            QMessageBox.critical(self, '오류', f'스크린샷 실패: {result}')

    # 11. Logcat Processing System
    def start_logcat_stream(self):
        serial = self.get_selected_device_serial()
        if not serial: return
        
        if self.logcat_thread is None:
            self.logcat_thread = LogcatThread(self.adb_path, serial)
            self.logcat_thread.new_log_signal.connect(self.on_new_log_line)
            self.logcat_thread.start()

    def stop_logcat_stream(self):
        if self.logcat_thread:
            self.logcat_thread.stop()
            self.logcat_thread = None

    def parse_log_line(self, line):
        line_str = line.strip('\r\n')
        m = THREADTIME_RE.match(line_str)
        if m:
            return {
                'time': m.group(1),
                'pid': m.group(2),
                'tid': m.group(3),
                'level': m.group(4),
                'tag': m.group(5).strip(),
                'message': m.group(6),
                'raw': line
            }
        else:
            return {
                'time': '',
                'pid': '',
                'tid': '',
                'level': 'I' if 'beginning of' in line_str else 'V',
                'tag': '',
                'message': line_str,
                'raw': line
            }

    def on_new_log_line(self, line):
        parsed = self.parse_log_line(line)
        self.all_log_lines.append(parsed)
        
        # Limit memory buffer storage
        if len(self.all_log_lines) > 3000:
            self.all_log_lines.pop(0)

        # Apply active filter conditions
        if self.should_display_log(parsed):
            self.log_model.append_log(parsed)
            # Enforce line limit buffer on model
            if len(self.log_model.logs) > 3000:
                self.log_model.remove_first_row()
            
            # Automatic scrolling
            if self.cb_autoscroll.isChecked():
                self.log_table.scrollToBottom()

    def should_display_log(self, parsed_item):
        # 1. Level Filter Check
        level_index = self.level_combo.currentIndex()
        if level_index > 0:
            levels = ['ALL', 'V', 'D', 'I', 'W', 'E']
            min_level = levels[level_index]
            level_order = {'V': 1, 'D': 2, 'I': 3, 'W': 4, 'E': 5, 'F': 6}
            item_level = parsed_item['level']
            min_val = level_order.get(min_level, 0)
            item_val = level_order.get(item_level, 1)
            if item_val < min_val:
                return False
        
        # 2. Tag Filter Check (Supports multiple tags separated by '|')
        tag_keyword = self.tag_edit.text().strip()
        if tag_keyword:
            tag_terms = [t.strip().lower() for t in tag_keyword.split('|') if t.strip()]
            if tag_terms:
                matched_tag = False
                for t in tag_terms:
                    if t in parsed_item['tag'].lower():
                        matched_tag = True
                        break
                if not matched_tag:
                    return False

        # 3. Content Search Keyword Check (Supports multiple keywords separated by '|' and strips '#num' prefix)
        keyword_text = self.search_edit.text().strip()
        if keyword_text:
            use_regex = self.cb_regex_filter.isChecked()
            terms = keyword_text.split('|')
            matched_any = False
            for term in terms:
                term = term.strip()
                if not term:
                    continue
                    
                match_text = term
                # Strip #num prefix for matching comparison
                if len(term) >= 2 and term[0] == '#' and term[1].isdigit():
                    match_text = term[2:]
                    
                if not match_text:
                    continue
                    
                if use_regex:
                    try:
                        import re
                        if (re.search(match_text, parsed_item['message'], re.IGNORECASE) or 
                            re.search(match_text, parsed_item['tag'], re.IGNORECASE)):
                            matched_any = True
                            break
                    except Exception:
                        if (match_text.lower() in parsed_item['message'].lower() or 
                            match_text.lower() in parsed_item['tag'].lower()):
                            matched_any = True
                            break
                else:
                    if (match_text.lower() in parsed_item['message'].lower() or 
                        match_text.lower() in parsed_item['tag'].lower()):
                        matched_any = True
                        break
            if not matched_any:
                has_valid_terms = any(t.strip() and (t.strip()[2:] if (len(t.strip()) >= 2 and t.strip()[0] == '#' and t.strip()[1].isdigit()) else t.strip()) for t in terms)
                if has_valid_terms:
                    return False
            
        return True

    def update_log_filter(self):
        filtered_logs = [item for item in self.all_log_lines if self.should_display_log(item)]
        self.log_model.set_logs(filtered_logs)
        if self.cb_autoscroll.isChecked():
            self.log_table.scrollToBottom()

    def clear_logs(self):
        self.all_log_lines.clear()
        self.log_model.clear()

    def save_logs(self):
        if not self.all_log_lines:
            QMessageBox.warning(self, '경고', '저장할 로그 내용이 존재하지 않습니다.')
            return
        try:
            filename = f"logcat_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            local_dir = os.path.expanduser('~/Desktop')
            if not os.path.exists(local_dir):
                local_dir_ko = os.path.expanduser('~/바탕화면')
                if os.path.exists(local_dir_ko):
                    local_dir = local_dir_ko
                else:
                    local_dir = os.path.expanduser('~')
            local_path = os.path.join(local_dir, filename)

            with open(local_path, 'w', encoding='utf-8') as f:
                f.write(''.join(item['raw'] for item in self.all_log_lines))

            QMessageBox.information(self, '로그 저장 성공', f'바탕화면에 로그 텍스트 파일이 저장되었습니다:\n{local_path}')
        except Exception as e:
            QMessageBox.critical(self, '오류', f'로그 저장 실패: {str(e)}')

    def on_log_cell_double_clicked(self, index):
        if not index.isValid():
            return
            
        col = index.column()
        row = index.row()
        if row >= len(self.log_model.logs):
            return
            
        item = self.log_model.logs[row]
        
        # Double click to add filters, similar to LogNote
        if col == 2:  # PID
            pid = item['pid']
            if pid:
                current = self.tag_edit.text().strip()
                self.tag_edit.setText(f"{current}|{pid}" if current else pid)
        elif col == 3:  # TID
            tid = item['tid']
            if tid:
                current = self.tag_edit.text().strip()
                self.tag_edit.setText(f"{current}|{tid}" if current else tid)
        elif col == 4:  # Level
            level = item['level']
            level_map = {'V': 1, 'D': 2, 'I': 3, 'W': 4, 'E': 5}
            idx = level_map.get(level, 0)
            self.level_combo.setCurrentIndex(idx)
        elif col == 5:  # Tag
            tag = item['tag']
            if tag:
                current = self.tag_edit.text().strip()
                if current:
                    tags = [t.strip() for t in current.split('|')]
                    if tag not in tags:
                        self.tag_edit.setText(f"{current}|{tag}")
                else:
                    self.tag_edit.setText(tag)
        elif col == 6:  # Message
            message = item['message'].strip()
            if message:
                current = self.search_edit.text().strip()
                self.search_edit.setText(f"{current}|{message}" if current else message)

    def show_log_context_menu(self, pos):
        menu = QMenu(self)
        copy_action = menu.addAction("로그 줄 복사 (Copy)")
        action = menu.exec_(self.log_table.viewport().mapToGlobal(pos))
        if action == copy_action:
            self.copy_selected_logs()

    def copy_selected_logs(self):
        selected_indexes = self.log_table.selectionModel().selectedRows()
        if not selected_indexes:
            return
            
        selected_indexes.sort(key=lambda idx: idx.row())
        
        lines_to_copy = []
        for index in selected_indexes:
            row = index.row()
            if row < len(self.log_model.logs):
                item = self.log_model.logs[row]
                lines_to_copy.append(item['raw'])
                
        if lines_to_copy:
            clipboard_text = "".join(lines_to_copy)
            QApplication.clipboard().setText(clipboard_text)
            self.statusBar().showMessage(f"{len(lines_to_copy)}개 로그 복사 완료.", 2000)

    # 12. Drag & Drop Actions (APK Install and File Push)
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.drop_zone.setStyleSheet("""
                QLabel#drop-zone {
                    border: 2px dashed #6366f1;
                    border-radius: 12px;
                    color: #ffffff;
                    font-size: 11px;
                    background-color: rgba(99, 102, 241, 0.15);
                    padding: 12px;
                }
            """)
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self.reset_drop_zone_style()

    def dropEvent(self, event):
        self.reset_drop_zone_style()
        urls = event.mimeData().urls()
        if urls:
            file_path = urls[0].toLocalFile()
            if os.path.exists(file_path):
                self.handle_dropped_file(file_path)

    def reset_drop_zone_style(self):
        self.drop_zone.setStyleSheet("""
            QLabel#drop-zone {
                border: 2px dashed rgba(255, 255, 255, 0.15);
                border-radius: 12px;
                color: #9ca3af;
                font-size: 11px;
                background-color: rgba(22, 28, 45, 0.2);
                padding: 12px;
            }
        """)

    def handle_dropped_file(self, file_path):
        serial = self.get_selected_device_serial()
        if not serial:
            QMessageBox.warning(self, "장치 선택 필요", "연결된 안드로이드 디바이스를 먼저 선택해주세요.")
            return

        filename = os.path.basename(file_path)
        if file_path.lower().endswith('.apk'):
            self.statusBar().showMessage(f"APK 설치 진행 중: {filename}...", 10000)
            cmd = [self.adb_path, '-s', serial, 'install', '-r', file_path]
            self.run_background_adb_task(cmd, f"APK 패키지 설치 완료: {filename}", f"APK 패키지 설치 실패: {filename}")
        else:
            self.statusBar().showMessage(f"파일 전송 진행 중: {filename}...", 10000)
            cmd = [self.adb_path, '-s', serial, 'push', file_path, '/sdcard/Download/']
            self.run_background_adb_task(cmd, f"파일 전송 성공: /sdcard/Download/{filename}", f"파일 전송 실패: {filename}")

    def run_background_adb_task(self, command_args, success_msg, fail_msg):
        thread = AdbTaskThread(command_args)
        thread.finished_signal.connect(lambda success, output: self.on_adb_task_finished(success, output, success_msg, fail_msg))
        self.active_tasks.append(thread)
        thread.start()

    def on_adb_task_finished(self, success, output, success_msg, fail_msg):
        sender = self.sender()
        if sender in self.active_tasks:
            self.active_tasks.remove(sender)
            
        if success:
            self.statusBar().showMessage(success_msg, 5000)
            QMessageBox.information(self, "작업 성공", success_msg)
        else:
            self.statusBar().showMessage("백그라운드 ADB 작업 실패", 5000)
            QMessageBox.critical(self, "작업 실패", f"{fail_msg}\n\n상세 정보:\n{output}")

    # 13. UI Stylesheet Styles
    def apply_dark_style(self):
        self.setStyleSheet("""
            QMainWindow {
                background-color: #0d0e15;
            }
            QScrollArea#sidebar-scroll {
                border: none;
                background-color: #121420;
                border-right: 1px solid rgba(255, 255, 255, 0.06);
            }
            QWidget#sidebar {
                background-color: #121420;
            }
            QLabel {
                color: #e5e7eb;
            }
            QLabel#logo {
                font-size: 15px;
                font-weight: bold;
                color: #ffffff;
            }
            QLabel#header-title {
                font-size: 20px;
                font-weight: bold;
                color: #ffffff;
            }
            QLabel#panel-title {
                font-size: 11px;
                text-transform: uppercase;
                color: #a78bfa;
                font-weight: bold;
                letter-spacing: 0.5px;
            }
            QWidget#panel-box {
                background-color: rgba(22, 28, 45, 0.55);
                border: 1px solid rgba(255, 255, 255, 0.05);
                border-radius: 12px;
                padding: 12px;
            }
            QLabel#status-pill {
                padding: 6px 12px;
                border-radius: 8px;
                font-size: 12px;
                font-weight: bold;
            }
            QLabel#device-info-lbl {
                color: #9ca3af;
                font-size: 11px;
                line-height: 1.4;
                padding: 4px;
                background-color: rgba(0,0,0,0.15);
                border-radius: 6px;
            }
            QPushButton {
                background-color: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 8px;
                color: #e5e7eb;
                padding: 8px 12px;
                font-size: 12px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.1);
                border-color: rgba(255, 255, 255, 0.15);
            }
            QPushButton:pressed {
                background-color: rgba(255, 255, 255, 0.15);
            }
            QPushButton#btn-settings {
                background-color: rgba(99, 102, 241, 0.1);
                border: 1px solid rgba(99, 102, 241, 0.25);
                color: #a5b4fc;
                padding: 6px 8px;
            }
            QPushButton#btn-settings:hover {
                background-color: rgba(99, 102, 241, 0.2);
            }
            QPushButton#btn-primary {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #6366f1, stop:1 #4f46e5);
                border: none;
                color: #ffffff;
                font-weight: bold;
            }
            QPushButton#btn-primary:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #818cf8, stop:1 #6366f1);
            }
            QPushButton#btn-danger {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #ef4444, stop:1 #dc2626);
                border: none;
                color: #ffffff;
                font-weight: bold;
            }
            QPushButton#btn-danger:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #f87171, stop:1 #ef4444);
            }
            QTextEdit {
                background-color: #07080d;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 12px;
                color: #f3f4f6;
                font-family: 'Fira Code', 'JetBrains Mono', 'Courier New', monospace;
                font-size: 11px;
                padding: 12px;
            }
            QTableView {
                background-color: #151515;
                gridline-color: rgba(255, 255, 255, 0.04);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 12px;
                color: #f0f0f0;
                selection-background-color: #3A3D41;
                selection-color: #ffffff;
            }
            QHeaderView::section {
                background-color: #0d0e15;
                color: #9ca3af;
                padding: 6px;
                border: none;
                border-right: 1px solid rgba(255, 255, 255, 0.05);
                border-bottom: 1px solid rgba(255, 255, 255, 0.05);
                font-weight: bold;
                font-size: 11px;
            }
            QLineEdit {
                background-color: #07080d;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 8px;
                color: #f3f4f6;
                padding: 6px 12px;
                font-size: 12px;
            }
            QLineEdit:focus {
                border: 1px solid #6366f1;
            }
            QComboBox {
                background-color: #07080d;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 8px;
                color: #f3f4f6;
                padding: 6px 12px;
                font-size: 12px;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QComboBox QAbstractItemView {
                background-color: #121420;
                border: 1px solid rgba(255, 255, 255, 0.08);
                color: #f3f4f6;
                selection-background-color: #4f46e5;
            }
            QCheckBox {
                color: #9ca3af;
                font-size: 11px;
            }
            QCheckBox:hover {
                color: #ffffff;
            }
            QCheckBox::indicator {
                width: 14px;
                height: 14px;
                border-radius: 3px;
                border: 1px solid rgba(255, 255, 255, 0.2);
                background-color: #07080d;
            }
            QCheckBox::indicator:checked {
                background-color: #6366f1;
                border-color: #6366f1;
            }
            QLabel#drop-zone {
                border: 2px dashed rgba(255, 255, 255, 0.15);
                border-radius: 12px;
                color: #9ca3af;
                font-size: 11px;
                background-color: rgba(22, 28, 45, 0.2);
                padding: 12px;
            }
            QStatusBar {
                background-color: #07080d;
                color: #9ca3af;
                font-size: 11px;
                border-top: 1px solid rgba(255, 255, 255, 0.05);
            }
        """)

    def closeEvent(self, event):
        # Stop background device detection thread
        if hasattr(self, 'device_detect_thread') and self.device_detect_thread:
            self.device_detect_thread.stop()
            self.device_detect_thread.wait()

        self.stop_logcat_stream()
        self.stop_mirroring()
        
        # Stop any active QThreads to prevent background hang on close
        for task in self.active_tasks:
            if task.isRunning():
                task.terminate()
                task.wait()
                
        event.accept()

if __name__ == '__main__':
    # High DPI scaling 활성화 (화면 해상도 배율 대응)
    from PyQt5.QtCore import Qt
    from PyQt5.QtGui import QFont
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    
    app = QApplication(sys.argv)
    app.setApplicationName("DroidDevHelper")
    app.setDesktopFileName("droid-dev-helper.desktop")
    
    # 윈도우/맥/리눅스 환경에서 가독성이 높고 미려한 기본 고딕 폰트 적용
    font = QFont('Malgun Gothic', 9)
    if not font.exactMatch():
        font = QFont('Apple SD Gothic Neo', 9)
        if not font.exactMatch():
            font = QFont('Noto Sans CJK KR', 9)
            if not font.exactMatch():
                font.setFamily('sans-serif')
    app.setFont(font)
    
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
