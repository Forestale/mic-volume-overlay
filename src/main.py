import sys
import os
import json
import numpy as np
import sounddevice as sd
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QUrl
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QSpinBox, QComboBox, QPushButton, QSystemTrayIcon, QMenu, QFileDialog
)
from PyQt6.QtGui import QIcon, QPixmap, QColor
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput

CONFIG_FILE = "config.json"

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    return os.path.join(base_path, relative_path)

def load_config():
    default_config = {
        "green_limit": -25.0,
        "yellow_limit": -12.0,
        "device_index": None,
        "sound_file": ""
    }
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return {**default_config, **json.load(f)}
        except Exception as e:
            print(f"Ошибка чтения конфига: {e}")
    return default_config

def save_config(config):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"Ошибка сохранения конфига: {e}")

class AudioThread(QThread):
    volume_signal = pyqtSignal(float)

    def __init__(self, device_index=None):
        super().__init__()
        self.device_index = device_index
        self.running = True

    def set_device(self, device_index):
        self.device_index = device_index

    def stop(self):
        self.running = False
        self.wait()

    def run(self):
        self.running = True
        def callback(indata, frames, time, status):
            rms = np.sqrt(np.mean(indata**2))
            db = 20 * np.log10(rms) if rms > 0 else -100.0
            self.volume_signal.emit(db)

        try:
            with sd.InputStream(device=self.device_index, callback=callback, channels=1, samplerate=44100, blocksize=2048):
                while self.running and self.isRunning():
                    self.msleep(50)
        except Exception as e:
            print(f"Ошибка аудиопотока: {e}")

class SettingsWindow(QWidget):
    def __init__(self, overlay):
        super().__init__()
        self.overlay = overlay
        self.devices = []
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("Настройки MicOverlay")
        self.setFixedSize(380, 280)
        
        layout = QVBoxLayout()

        layout.addWidget(QLabel("Микрофон:"))
        self.mic_combo = QComboBox()
        self.load_microphones()
        layout.addWidget(self.mic_combo)

        h_layout1 = QHBoxLayout()
        h_layout1.addWidget(QLabel("Порог ЖЁЛТОГО (dBFS):"))
        self.yellow_spin = QSpinBox()
        self.yellow_spin.setRange(-60, 0)
        self.yellow_spin.setValue(int(self.overlay.green_limit))
        h_layout1.addWidget(self.yellow_spin)
        layout.addLayout(h_layout1)

        h_layout2 = QHBoxLayout()
        h_layout2.addWidget(QLabel("Порог КРАСНОГО (dBFS):"))
        self.red_spin = QSpinBox()
        self.red_spin.setRange(-60, 0)
        self.red_spin.setValue(int(self.overlay.yellow_limit))
        h_layout2.addWidget(self.red_spin)
        layout.addLayout(h_layout2)

        # Выбор звукового файла
        layout.addWidget(QLabel("Звук при превышении:"))
        sound_layout = QHBoxLayout()
        self.sound_label = QLabel(os.path.basename(self.overlay.sound_file) if self.overlay.sound_file else "По умолчанию (Beep)")
        self.sound_label.setWordWrap(True)
        sound_layout.addWidget(self.sound_label)

        browse_btn = QPushButton("Обзор...")
        browse_btn.clicked.connect(self.browse_sound)
        sound_layout.addWidget(browse_btn)

        test_btn = QPushButton("▶")
        test_btn.setFixedWidth(30)
        test_btn.setToolTip("Прослушать звук")
        test_btn.clicked.connect(self.overlay.play_alert_sound)
        sound_layout.addWidget(test_btn)

        reset_btn = QPushButton("✕")
        reset_btn.setFixedWidth(30)
        reset_btn.setToolTip("Сбросить на звук по умолчанию")
        reset_btn.clicked.connect(self.reset_sound)
        sound_layout.addWidget(reset_btn)

        layout.addLayout(sound_layout)

        save_btn = QPushButton("Сохранить")
        save_btn.clicked.connect(self.save_settings)
        layout.addWidget(save_btn)

        self.setLayout(layout)

    def load_microphones(self):
        self.mic_combo.clear()
        self.devices = []
        try:
            all_devices = sd.query_devices()
            default_input = sd.default.device[0]
            
            for idx, dev in enumerate(all_devices):
                if dev['max_input_channels'] > 0:
                    self.devices.append(idx)
                    name = f"{idx}: {dev['name']}"
                    if idx == default_input:
                        name += " (По умолчанию)"
                    self.mic_combo.addItem(name, idx)
                    
            if self.overlay.current_device_index is not None:
                index = self.mic_combo.findData(self.overlay.current_device_index)
                if index != -1:
                    self.mic_combo.setCurrentIndex(index)
        except Exception as e:
            print(f"Ошибка получения списка микрофонов: {e}")

    def browse_sound(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Выберите аудиофайл", "", "Аудиофайлы (*.wav *.mp3 *.ogg)"
        )
        if file_path:
            self.overlay.sound_file = file_path
            self.sound_label.setText(os.path.basename(file_path))

    def reset_sound(self):
        self.overlay.sound_file = ""
        self.sound_label.setText("По умолчанию (Beep)")

    def save_settings(self):
        self.overlay.green_limit = float(self.yellow_spin.value())
        self.overlay.yellow_limit = float(self.red_spin.value())
        
        selected_device = self.mic_combo.currentData()
        if selected_device is not None:
            self.overlay.change_audio_device(selected_device)

        config = {
            "green_limit": self.overlay.green_limit,
            "yellow_limit": self.overlay.yellow_limit,
            "device_index": self.overlay.current_device_index,
            "sound_file": self.overlay.sound_file
        }
        save_config(config)
            
        self.hide()

class SoundAlertOverlay(QWidget):
    def __init__(self):
        super().__init__()
        config = load_config()
        self.green_limit = config.get("green_limit", -25.0)
        self.yellow_limit = config.get("yellow_limit", -12.0)
        self.current_device_index = config.get("device_index")
        self.sound_file = config.get("sound_file", "")

        # Плеер для кастомных звуков
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)
        self.audio_output.setVolume(1.0)

        self.red_hold_timer = QTimer()
        self.red_hold_timer.setSingleShot(True)
        self.is_red_held = False

        self.init_ui()
        self.init_audio()
        self.init_tray()

    def init_ui(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setGeometry(100, 100, 160, 60)

        layout = QVBoxLayout()
        self.label = QLabel("0 dB", self)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.label)
        self.setLayout(layout)
        self.update_style("rgba(46, 204, 113, 200)")

    def init_tray(self):
        icon_path = resource_path(os.path.join("assets", "app_icon.ico"))
        
        if os.path.exists(icon_path):
            app_icon = QIcon(icon_path)
        else:
            pixmap = QPixmap(16, 16)
            pixmap.fill(QColor(46, 204, 113))
            app_icon = QIcon(pixmap)

        QApplication.setWindowIcon(app_icon)
        self.tray_icon = QSystemTrayIcon(app_icon, self)
        self.tray_icon.setToolTip("Mic Volume Overlay")

        tray_menu = QMenu()
        settings_action = tray_menu.addAction("Настройки")
        settings_action.triggered.connect(self.open_settings)

        toggle_action = tray_menu.addAction("Показать/Скрыть оверлей")
        toggle_action.triggered.connect(self.toggle_visibility)

        quit_action = tray_menu.addAction("Выход")
        quit_action.triggered.connect(QApplication.instance().quit)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.show()

        self.settings_window = None

    def play_alert_sound(self):
        if self.sound_file and os.path.exists(self.sound_file):
            self.player.setSource(QUrl.fromLocalFile(self.sound_file))
            self.player.play()
        else:
            QApplication.beep()

    def open_settings(self):
        if not self.settings_window:
            self.settings_window = SettingsWindow(self)
        else:
            self.settings_window.load_microphones()
        self.settings_window.show()
        self.settings_window.activateWindow()

    def toggle_visibility(self):
        if self.isVisible():
            self.hide()
        else:
            self.show()

    def init_audio(self):
        self.thread = AudioThread(device_index=self.current_device_index)
        self.thread.volume_signal.connect(self.update_volume)
        self.thread.start()

    def change_audio_device(self, new_device_index):
        if self.current_device_index != new_device_index:
            self.current_device_index = new_device_index
            self.thread.stop()
            self.init_audio()

    def update_volume(self, db):
        self.label.setText(f"{db:.1f} dB")

        if db >= self.yellow_limit or self.is_red_held:
            bg_color = "rgba(231, 76, 60, 230)"
            if db >= self.yellow_limit and not self.is_red_held:
                self.is_red_held = True
                self.play_alert_sound()
                self.red_hold_timer.singleShot(1500, self.reset_red_hold)
        elif db >= self.green_limit:
            bg_color = "rgba(241, 196, 15, 200)"
        else:
            bg_color = "rgba(46, 204, 113, 200)"

        self.update_style(bg_color)

    def reset_red_hold(self):
        self.is_red_held = False

    def update_style(self, bg_color):
        self.label.setStyleSheet(f"""
            QLabel {{
                background-color: {bg_color};
                color: white;
                font-weight: bold;
                font-size: 16px;
                border-radius: 10px;
            }}
        """)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_position)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    
    overlay = SoundAlertOverlay()
    overlay.show()
    sys.exit(app.exec())