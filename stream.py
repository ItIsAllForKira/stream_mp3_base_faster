import threading
import sys
import subprocess
import numpy as np
import os
cache_dir = os.path.expanduser("~/.cache/huggingface")
hf_home_dir = os.path.join(cache_dir, "hub")
os.makedirs(hf_home_dir, exist_ok=True)
os.environ["HF_HOME"] = cache_dir
import faster_whisper
from colorama import Fore, Style, init
import time
from datetime import datetime
import requests
import re
import wave
import logging
from logging.handlers import RotatingFileHandler
import pyaudio
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QPushButton, QTextEdit, QLabel, QLineEdit,
    QVBoxLayout, QHBoxLayout, QWidget, QFileDialog, QMessageBox, QSpinBox,
    QComboBox, QDoubleSpinBox
)
from PySide6.QtCore import QTimer, Qt, Signal, QCoreApplication, QThread
from PySide6.QtGui import QTextCharFormat, QFont, QColor, QTextCursor, QBrush
from pydub import AudioSegment
from contextlib import contextmanager
@contextmanager
def suppress_stdout():
    devnull = open(os.devnull, "w")
    old_stdout = sys.stdout
    old_stderr = sys.stderr
    sys.stdout = devnull
    sys.stderr = devnull
    try:
        yield
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr
        devnull.close()
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s")
usage_logger = logging.getLogger("stream")
usage_logger.setLevel(logging.INFO)
if not usage_logger.handlers:
    if getattr(sys, 'frozen', False):
        base_path = sys._MEIPASS
        log_dir = os.path.dirname(sys.executable)
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
        log_dir = base_path
    log_file_path = os.path.join(log_dir, "stream.log")
    handler = RotatingFileHandler(log_file_path, maxBytes=5*1024*1024, backupCount=3)
    formatter = logging.Formatter('%(asctime)s %(stream_name)s - %(action)s: %(duration_formatted)s', datefmt='%Y-%m-%d %H:%M:%S')
    handler.setFormatter(formatter)
    usage_logger.addHandler(handler)
    usage_logger.propagate = False
init(autoreset=True)
class WorkerThread(QThread):
    update_signal = Signal(str, bool, Qt.GlobalColor)
    reset_signal = Signal()
    def __init__(self, parent=None, process_func=None, args=None):
        super().__init__(parent)
        self.process_func = process_func
        self.args = args if args is not None else ()
    def run(self):
        self.process_func(*self.args)
class AudioRecorderApp(QMainWindow):
    update_signal = Signal(str, bool, Qt.GlobalColor)
    reset_signal = Signal()
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Stream Recorder and Transcriber ("base") - V211125')
        self.setGeometry(100, 100, 1000, 600)
        self.current_chunk_ranges = []
        if getattr(sys, 'frozen', False):
            self.base_path = sys._MEIPASS
            self.output_dir = os.path.dirname(sys.executable)
        else:
            self.base_path = os.path.dirname(os.path.abspath(__file__))
            self.output_dir = self.base_path
        self.running = False
        self.model = None
        self.model_state = "not_loaded"
        self.wav_filename = None
        self.transcript_filename = None
        self.process_ffmpeg = None
        self.start_time = 0
        self.max_duration = 0
        self.audio_bytes_read_default = 16000 * 2 * 15
        self.audio_bytes_read = self.audio_bytes_read_default
        self.operation_start_time = None
        self.current_stream_name = "Unknown Stream"
        self.init_ui()
        self.update_signal.connect(self.update_status)
        self.reset_signal.connect(self.reset_text_format)
        self.p = pyaudio.PyAudio()
        self.stream = self.p.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=16000,
            output=True,
            frames_per_buffer=1024
        )
    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout()
        self.elapsed_time_label = QLabel("Timer 00:00", self)
        self.elapsed_time_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.elapsed_time_label)
        self.status_label = QLabel("Status: Waiting", self)
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)
        stream_select_layout = QHBoxLayout()
        self.stream_selector_label = QLabel("Select a stream:")
        self.stream_selector = QComboBox()
        self.stream_selector.setEditable(True)
        self.streams = {
            "URL": "Select from the drop-down list or enter a different URL manually.",
            "Aljazeera": "https://live-hls-audio-aje-fa.getaj.net/VOICE-AJE/01.m3u8",
            "Aljazeera_News": "http://live-hls-web-aje.getaj.net/AJE/06.m3u8",
            "BBC": "https://stream.live.vc.bbcmedia.co.uk/bbc_world_service",
            "BBC_east": "https://stream.live.vc.bbcmedia.co.uk/bbc_world_service_east_asia",
            "BBC_radio": "http://as-hls-ww-live.akamaized.net/pool_55057080/live/ww/bbc_radio_fourfm/bbc_radio_fourfm.isml/bbc_radio_fourfm-audio%3d128000.norewind.m3u8",
            "Bloomberg": "https://playerservices.streamtheworld.com/api/livestream-redirect/WBBRDCAAC.aac",
            "Bloomberg_Boston": "https://playerservices.streamtheworld.com/api/livestream-redirect/WRCAAMAAC.aac",
            "Bloomberg_Busines": "https://stream.revma.ihrhls.com/zc301",
            "CNN_Int": "https://tunein.cdnstream1.com/3519_96.aac",
            "CNN": "https://tunein.cdnstream1.com/2868_96.aac",
            "Sport": "http://13.54.221.214:8000/sen.mp3",
            "VOA": "https://voa-ingest.akamaized.net/hls/live/2035234/160_342L/playlist.m3u8",
            "VOA_news": "http://voa-28.akacast.akamaistream.net/7/54/322040/v1/ibb.akacast.akamaistream.net/voa-28"
        }
        for name in self.streams:
            self.stream_selector.addItem(name)
        self.stream_selector.currentIndexChanged.connect(self.update_url_from_selection)
        stream_select_layout.addWidget(self.stream_selector_label)
        stream_select_layout.addWidget(self.stream_selector)
        layout.addLayout(stream_select_layout)
        url_entry_layout = QHBoxLayout()
        self.url_label = QLabel("Or enter a different URL manually:")
        self.url_entry = QLineEdit()
        self.url_entry.setText(self.streams["URL"])
        url_entry_layout.addWidget(self.url_label)
        url_entry_layout.addWidget(self.url_entry)
        layout.addLayout(url_entry_layout)
        duration_layout = QHBoxLayout()
        self.duration_label = QLabel("Specify the duration of the stream up to 30 minutes and click the button:")
        self.duration_spinbox = QSpinBox()
        self.duration_spinbox.setMinimum(1)
        self.duration_spinbox.setMaximum(30)
        self.duration_spinbox.setValue(2)
        duration_layout.addWidget(self.duration_label)
        duration_layout.addWidget(self.duration_spinbox)
        duration_layout.addStretch()
        layout.addLayout(duration_layout)
        audio_bytes_layout = QHBoxLayout()
        self.audio_bytes_read_label = QLabel("To change the block duration (default is 15 sec) (160000 = 5 sec, 320000 = 10 sec, 640000 = 20 sec, 960000 = 30 sec, 1920000 = 60 sec):")
        self.audio_bytes_read_spinbox = QSpinBox()
        self.audio_bytes_read_spinbox.setMinimum(32000)
        self.audio_bytes_read_spinbox.setMaximum(1920000)
        self.audio_bytes_read_spinbox.setValue(self.audio_bytes_read_default)
        self.audio_bytes_read_spinbox.valueChanged.connect(self.update_audio_bytes_read)
        audio_bytes_layout.addWidget(self.audio_bytes_read_label)
        audio_bytes_layout.addWidget(self.audio_bytes_read_spinbox)
        audio_bytes_layout.addStretch()
        layout.addLayout(audio_bytes_layout)
        self.text_box = QTextEdit()
        self.text_box.setReadOnly(True)
        layout.addWidget(self.text_box)
        self.text_box.setStyleSheet("background-color: white; color: black;")
        button_frame = QWidget()
        button_layout = QHBoxLayout()
        self.start_button = QPushButton("Record")
        self.start_button.clicked.connect(self.toggle_recording)
        button_layout.addWidget(self.start_button)
        self.listen_button = QPushButton("Listen")
        self.listen_button.clicked.connect(self.toggle_listen_mode)
        button_layout.addWidget(self.listen_button)
        button_frame.setLayout(button_layout)
        layout.addWidget(button_frame)
        central_widget.setLayout(layout)
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_progress)
    def update_status_display(self):
        status_text = self.status_label.text().split(" | ")[0]
        model_state_text = self.get_model_state_text()
        self.status_label.setText(f"{status_text} | Model: {model_state_text}")
    def get_model_state_text(self):
        state_map = {
            "not_loaded": "Not loaded",
            "loading": "Loading",
            "loaded": "Loaded",
            "error": "Error"
        }
        return state_map.get(self.model_state, "Unknown")
    def load_model_if_needed(self):
        if self.model is None:
            self.model_state = "loading"
            self.update_status_display()
            QApplication.processEvents()
            try:
                with suppress_stdout():
                    self.model = faster_whisper.WhisperModel("base", device="cpu", compute_type="int8")
                logging.info("Model Whisper loaded successfully.")
                self.model_state = "loaded"
                self.update_status_display()
                QApplication.processEvents()
            except Exception as e:
                self.model_state = "error"
                self.update_status_display()
                QApplication.processEvents()
                QMessageBox.critical(self, "Error", f"Failed to load Whisper model: {str(e)}")
                raise
    def update_url_from_selection(self):
        selected_name = self.stream_selector.currentText()
        url = self.streams.get(selected_name, "")
        self.url_entry.setText(url)
    def update_status(self, text, bold=True, color=Qt.GlobalColor.red):
        cursor = self.text_box.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        start_pos = cursor.position()
        fmt = QTextCharFormat()
        if bold:
            fmt.setFontWeight(QFont.Weight.Bold)
        fmt.setForeground(QBrush(color))
        cursor.insertText(text, fmt)
        end_pos = cursor.position()
        self.current_chunk_ranges.append((start_pos, end_pos))
        self.text_box.ensureCursorVisible()
    def reset_text_format(self):
        cursor = self.text_box.textCursor()
        normal_format = QTextCharFormat()
        normal_format.setFontWeight(QFont.Weight.Bold)
        normal_format.setForeground(QBrush(Qt.GlobalColor.blue))
        for start, end in self.current_chunk_ranges:
            cursor.setPosition(start)
            cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
            cursor.mergeCharFormat(normal_format)
        self.current_chunk_ranges = []
    def log_usage_event(self, action):
        if self.operation_start_time:
            duration_seconds = time.time() - self.operation_start_time
            minutes = int(duration_seconds // 60)
            seconds = int(duration_seconds % 60)
            duration_formatted = f"{minutes}:{seconds:02d}"
            usage_logger.info(
                "",
                extra={
                    'stream_name': self.current_stream_name,
                    'action': action,
                    'duration_formatted': duration_formatted
                }
            )
    def toggle_recording(self):
        if self.running:
            self.stop_recording()
        else:
            url = self.url_entry.text().strip()
            if not url:
                QMessageBox.warning(self, "Warning", "Enter a stream URL")
                return
            self.text_box.clear()
            self.start_stream_processing(url)
            self.listen_button.setEnabled(False)
    def start_stream_processing(self, url):
        try:
            self.load_model_if_needed()
        except Exception:
            return
        self.operation_start_time = time.time()
        self.current_stream_name = self.stream_selector.currentText()
        try:
            response = requests.get(url, timeout=5, stream=True)
            if response.status_code != 200:
                QMessageBox.critical(self, "Error", f"URL is unavailable: {url}")
                return
        except requests.exceptions.RequestException as e:
            QMessageBox.critical(self, "Error", f"Error checking URL: {str(e)}")
            return
        self.max_duration = self.duration_spinbox.value() * 60
        self.start_time = time.time()
        selected_name = self.stream_selector.currentText()
        current_time = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        base_name = re.sub(r'[^a-zA-Z0-9]', '_', selected_name)
        self.wav_filename = os.path.join(self.output_dir, f"{base_name}_audio_{current_time}.wav")
        ffmpeg_path = os.path.join(self.base_path, "ffmpeg.exe") if getattr(sys, 'frozen', False) else "ffmpeg"
        ffmpeg_cmd = [
            ffmpeg_path,
            "-y",
            "-stream_loop", "-1",
            "-i", url,
            "-vn",
            "-acodec", "pcm_s16le",
            "-ar", "16000",
            "-ac", "1",
            "-f", "s16le",
            "-"
        ]
        try:
            self.process_ffmpeg = subprocess.Popen(
                ffmpeg_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=10**8,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            self.wav_file = wave.open(self.wav_filename, "wb")
            self.wav_file.setnchannels(1)
            self.wav_file.setsampwidth(2)
            self.wav_file.setframerate(16000)
            self.running = True
            self.start_button.setText("Stop")
            self.status_label.setText("Status: In progress... | Model: Loaded")
            self.worker_thread = WorkerThread(self, self.process_audio, ())
            self.worker_thread.update_signal.connect(self.update_status)
            self.worker_thread.reset_signal.connect(self.reset_text_format)
            self.worker_thread.finished.connect(self.stop_processing_stream)
            self.worker_thread.start()
            self.read_stderr_thread = threading.Thread(target=self.read_stderr, daemon=True)
            self.read_stderr_thread.start()
            self.timer.start(1000)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to start FFmpeg: {str(e)}")
            return
    def process_audio(self):
        try:
            while self.running:
                if self.process_ffmpeg.poll() is not None:
                    logging.error("FFmpeg process ended with an error.")
                    self.running = False
                    break
                audio_bytes = self.process_ffmpeg.stdout.read(self.audio_bytes_read)
                if not audio_bytes or (time.time() - self.start_time >= self.max_duration):
                    self.running = False
                    break
                audio = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
                self.wav_file.writeframes(audio_bytes)
                segments, info = self.model.transcribe(audio, language="en", vad_filter=True)  # , task="translate"
                full_text = ""
                for segment in segments:
                    full_text += segment.text
                if full_text.strip():
                    sentences = re.split(r'[.!?]\s*', full_text)
                    for sentence in sentences:
                        sentence = sentence.strip()
                        if sentence:
                            self.update_signal.emit(f"{sentence}.\n", True, Qt.GlobalColor.red)
                self.stream.write(audio_bytes)
                self.reset_signal.emit()
        except Exception as e:
            logging.error(f"Audio processing error: {str(e)}")
            self.update_signal.emit(f"Audio processing error: {str(e)}", True, Qt.GlobalColor.red)
        finally:
            if hasattr(self, 'wav_file'):
                self.wav_file.close()
            if hasattr(self, 'process_ffmpeg') and self.process_ffmpeg:
                self.process_ffmpeg.terminate()
                self.process_ffmpeg.wait()
    def stop_processing_stream(self):
        self.running = False
        self.timer.stop()
        self.status_label.setText("Status: Ready for a new job")
        self.start_button.setText("Record")
        self.log_usage_event("Record")
        self.operation_start_time = None
        QMessageBox.information(self, "Information", "Transcription completed.")
        if self.wav_filename:
            self.convert_wav_to_mp3(self.wav_filename)
        self.listen_button.setEnabled(True)
    def read_stderr(self):
        try:
            for line in self.process_ffmpeg.stderr:
                try:
                    decoded_line = line.decode('utf-8').strip()
                    logging.debug(decoded_line)
                except UnicodeDecodeError as e:
                    logging.error(f"Error decoding stderr: {str(e)}")
        except Exception as e:
            logging.error(f"Error reading stderr: {str(e)}")
    def update_progress(self):
        elapsed_time = int(time.time() - self.start_time)
        minutes = elapsed_time // 60
        seconds = elapsed_time % 60
        self.elapsed_time_label.setText(f"Timer {minutes:02}:{seconds:02}")
        if elapsed_time >= self.max_duration:
            self.running = False
        QCoreApplication.processEvents()
    def toggle_listen_mode(self):
        if not self.running:
            url = self.url_entry.text().strip()
            if not url:
                QMessageBox.warning(self, "Warning", "Enter a stream URL")
                return
            try:
                self.load_model_if_needed()
            except Exception:
                return
            self.operation_start_time = time.time()
            self.current_stream_name = self.stream_selector.currentText()
            try:
                response = requests.get(url, timeout=5, stream=True)
                if response.status_code != 200:
                    self.operation_start_time = None
                    QMessageBox.critical(self, "Error", f"URL is unavailable: {url}")
                    return
            except requests.exceptions.RequestException as e:
                self.operation_start_time = None
                QMessageBox.critical(self, "Error", f"Error checking URL: {str(e)}")
                return
            self.text_box.clear()
            self.max_duration = self.duration_spinbox.value() * 60
            self.start_time = time.time()
            selected_name = self.stream_selector.currentText()
            base_name = re.sub(r'[^a-zA-Z0-9]', '_', selected_name)
            ffmpeg_path = os.path.join(self.base_path, "ffmpeg.exe") if getattr(sys, 'frozen', False) else "ffmpeg"
            ffmpeg_cmd = [
                ffmpeg_path,
                "-y",
                "-stream_loop", "-1",
                "-i", url,
                "-vn",
                "-acodec", "pcm_s16le",
                "-ar", "16000",
                "-ac", "1",
                "-f", "s16le",
                "-"
            ]
            try:
                self.process_ffmpeg = subprocess.Popen(
                    ffmpeg_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    bufsize=10**8,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
                self.running = True
                self.start_button.setEnabled(False)
                self.listen_button.setText("Stop")
                self.status_label.setText("Status: Transcription in progress... | Model: Loaded")
                self.worker_thread = WorkerThread(self, self.process_audio_for_listen, ())
                self.worker_thread.update_signal.connect(self.update_status)
                self.worker_thread.reset_signal.connect(self.reset_text_format)
                self.worker_thread.finished.connect(self.stop_listening)
                self.worker_thread.start()
                self.read_stderr_thread = threading.Thread(target=self.read_stderr, daemon=True)
                self.read_stderr_thread.start()
                self.timer.start(1000)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to start FFmpeg: {str(e)}")
                self.operation_start_time = None
                return
        else:
            self.running = False
            self.timer.stop()
            self.status_label.setText("Status: Ready for a new job | Model: Loaded")
            self.start_button.setEnabled(True)
            self.listen_button.setText("Listen")
            QMessageBox.information(self, "Information", "The stream has stopped, wait for the next message.")
    def process_audio_for_listen(self):
        try:
            while self.running:
                if self.process_ffmpeg.poll() is not None:
                    logging.error("FFmpeg process ended with an error.")
                    self.running = False
                    break
                audio_bytes = self.process_ffmpeg.stdout.read(self.audio_bytes_read)
                if not audio_bytes or (time.time() - self.start_time >= self.max_duration):
                    self.running = False
                    break
                audio = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
                segments, info = self.model.transcribe(audio, language="en", vad_filter=True)
                full_text = ""
                for segment in segments:
                    full_text += segment.text
                if full_text.strip():
                    sentences = re.split(r'[.!?]\s*', full_text)
                    for sentence in sentences:
                        sentence = sentence.strip()
                        if sentence:
                            self.update_signal.emit(f"{sentence}.\n", True, Qt.GlobalColor.red)
                self.stream.write(audio_bytes)
                self.reset_signal.emit()
        except Exception as e:
            logging.error(f"Audio processing error: {str(e)}")
            self.update_signal.emit(f"Audio processing error: {str(e)}", True, Qt.GlobalColor.red)
        finally:
            if hasattr(self, 'process_ffmpeg') and self.process_ffmpeg:
                self.process_ffmpeg.terminate()
                self.process_ffmpeg.wait()
    def stop_listening(self):
        self.running = False
        self.timer.stop()
        self.status_label.setText("Status: Ready for a new job | Model: Loaded")
        self.start_button.setEnabled(True)
        self.listen_button.setText("Listen")
        self.log_usage_event("Listening")
        self.operation_start_time = None
        QMessageBox.information(self, "Information", "Listening is over")
        if self.wav_filename:
            self.convert_wav_to_mp3(self.wav_filename)
    def update_audio_bytes_read(self, value):
        self.audio_bytes_read = value
    def stop_recording(self):
        self.running = False
        self.timer.stop()
        self.status_label.setText("Status: The record has stopped, wait for the next message.")
        self.start_button.setText("Record")
        self.listen_button.setEnabled(True)
        self.log_usage_event("Recording (int)")
        self.operation_start_time = None
        QMessageBox.information(self, "Information", "Recording stopped, wait for next message..")
    def convert_wav_to_mp3(self, wav_file_path):
        try:
            audio = AudioSegment.from_wav(wav_file_path)
            mp3_file_path = os.path.splitext(wav_file_path)[0] + ".mp3"
            audio.export(mp3_file_path, format="mp3", bitrate="192k")
            logging.info(f"File saved successfully: {mp3_file_path}")
            with suppress_stdout():
                os.remove(wav_file_path)
            logging.info(f"WAV file deleted: {wav_file_path}")
        except Exception as e:
            logging.error(f"Failed to convert {wav_file_path}: {str(e)}")
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = AudioRecorderApp()
    window.show()
    sys.exit(app.exec())