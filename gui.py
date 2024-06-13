import re
import spacy
from fuzzywuzzy import fuzz
from PyQt5 import QtCore, QtGui, QtWidgets
import pyautogui
import pytesseract
import pyperclip
import keyboard
import pygetwindow as gw
import winsound
import time
import logging
import os
import sys
import ctypes
import shutil
import urllib.request
import subprocess

logging.basicConfig(filename='debug.log', level=logging.DEBUG, format='%(asctime)s:%(levelname)s:%(message)s')

# Load spaCy model
nlp = spacy.load("en_core_web_sm")

def is_admin():
    """Check if the script is running with administrative privileges."""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def run_as_admin():
    """Re-run the script with administrative privileges."""
    ctypes.windll.shell32.ShellExecuteW(
        None, "runas", sys.executable, ' '.join(sys.argv), None, 1)

def is_tesseract_installed():
    """Check if Tesseract is installed by looking for its executable."""
    tesseract_path = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
    return os.path.exists(tesseract_path)

def download_and_install_tesseract():
    """Download and install Tesseract."""
    url = "https://digi.bib.uni-mannheim.de/tesseract/tesseract-ocr-w64-setup-5.4.0.20240606.exe"
    installer_path = os.path.join(os.getenv('TEMP'), "tesseract_installer.exe")

    try:
        print("Downloading Tesseract OCR installer...")
        with urllib.request.urlopen(url) as response, open(installer_path, 'wb') as out_file:
            shutil.copyfileobj(response, out_file)
        print("Tesseract OCR installer downloaded successfully.")
        
        print("Installing Tesseract OCR...")
        installer_process = subprocess.Popen([installer_path, '/SILENT'])
        
        time.sleep(3)
        
        installer_process.terminate()
        
        print("Tesseract OCR installation completed.")
        
    except Exception as e:
        print(f"Failed to install Tesseract OCR: {e}")
        sys.exit(1)
    finally:
        if os.path.exists(installer_path):
            os.remove(installer_path)

if not is_tesseract_installed():
    if not is_admin():
        run_as_admin()
        sys.exit()
    download_and_install_tesseract()
else:
    print("Tesseract is already installed.")

pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

CURRENT_DIR = getattr(sys, '_MEIPASS', os.path.abspath(os.path.dirname(__file__)))
IMAGE_PATH = os.path.join(CURRENT_DIR, "image.png")

class OCRWorker(QtCore.QThread):
    resultReady = QtCore.pyqtSignal(str)
    notifyReady = QtCore.pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.running = False
        self.screenshot_path = os.path.join(CURRENT_DIR, "screenshot.png")  # Path to save the screenshot

    def run(self):
        self.running = True
        while self.running:
            try:
                screenshot = pyautogui.screenshot(region=(350, 200, 1000, 300))
                screenshot.save(self.screenshot_path)  # Save the screenshot
                screenshot = screenshot.convert('L')
                text = pytesseract.image_to_string(screenshot)

                error = self.extract_error(text)
                qb_link = self.extract_qb_link(text)
                qb_id = self.extract_qb_id(text)
                product = self.extract_product(text)

                if all([error, qb_link, qb_id, product]):
                    browser_link = self.get_current_browser_url()
                    if browser_link:
                        message = f"/qbissue product: {product} ticket_link: {browser_link} qb_link: {qb_link} issue: {error} qb_id: {qb_id}"
                        self.resultReady.emit(message)
                        self.notifyReady.emit("All information gathered successfully!")
                        self.running = False
                time.sleep(0.2)
            except Exception as e:
                print(f"Error during OCR processing: {e}")

    def stop(self):
        self.running = False

    def extract_error(self, text):
        """Extract error information from text."""
        doc = nlp(text)
        error_sentences = []
        for sent in doc.sents:
            if "error" in sent.text.lower() or "issue" in sent.text.lower():
                error_sentences.append(sent.text.strip())

        # Further process the sentences to isolate specific error messages
        if error_sentences:
            for sentence in error_sentences:
                if "error" in sentence.lower():
                    return self.extract_specific_error(sentence)
        return None

    def extract_specific_error(self, sentence):
        """Use dependency parsing to isolate the error message."""
        doc = nlp(sentence)
        for token in doc:
            if "error" in token.text.lower():
                # Get the subtree of the error token which usually contains the full error message
                return ' '.join([subtoken.text for subtoken in token.subtree])
        return sentence  # Return the whole sentence if we can't isolate further

    def extract_qb_link(self, text):
        """Extract QB link from text using regex."""
        match = re.search(r'https?://\S+', text)
        return match.group(0) if match else None

    def extract_qb_id(self, text):
        """Extract QB ID from text using regex."""
        match = re.search(r'\b[0-9a-fA-F]{8}\b', text)
        return match.group(0) if match else None

    def extract_product(self, text):
        """Extract product information from text using fuzzy matching."""
        products = {
            "R6 Full": ["r6 full", "rainbow six full", "rainbow full"],
            "R6 Lite": ["r6 lite", "rainbow six lite", "rainbow lite", "lite"],
            "XDefiant": ["xdefiant", "xd", "defiant"]
        }

        text = text.lower()
        best_match = ("r6_full", 0)

        for product, aliases in products.items():
            for alias in aliases:
                match_ratio = fuzz.partial_ratio(alias, text)
                if match_ratio > best_match[1]:
                    best_match = (product, match_ratio)

        if best_match[1] > 70:
            return best_match[0]
        else:
            return "r6_full"

    def get_current_browser_url(self):
        try:
            browsers = {
                'Opera': ('ctrl', 'l'),
                'Chrome': ('ctrl', 'l'),
                'Firefox': ('ctrl', 'l'),
                'Microsoft Edge': ('ctrl', 'l'),
            }

            window = None
            for browser_name, (hotkey1, hotkey2) in browsers.items():
                for w in gw.getWindowsWithTitle(browser_name):
                    if browser_name in w.title:
                        window = w
                        break
                if window:
                    break
            
            if window is None:
                raise Exception("Supported browser window not found")

            window.activate()
            pyautogui.hotkey(hotkey1, hotkey2)
            pyautogui.hotkey('ctrl', 'c')
            time.sleep(0.05)

            url = pyperclip.paste()
            return url

        except Exception as e:
            print(f"Error retrieving browser URL: {e}")
            return None

class CustomTitleBar(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super(CustomTitleBar, self).__init__(parent)
        self.parent = parent
        self.setAutoFillBackground(True)
        self.setBackgroundRole(QtGui.QPalette.Window)
        self.initUI()

    def initUI(self):
        self.setFixedHeight(40)
        layout = QtWidgets.QHBoxLayout()
        layout.setContentsMargins(10, 0, 0, 0)
        self.setLayout(layout)

        self.titleLabel = QtWidgets.QLabel("QuickBuild Auto Scanner")
        self.titleLabel.setStyleSheet("color: white; font: bold 14px;")
        layout.addWidget(self.titleLabel)

        layout.addStretch()

        self.minimizeButton = QtWidgets.QPushButton("-")
        self.minimizeButton.setFixedSize(40, 40)
        self.minimizeButton.setStyleSheet(
            "QPushButton { background-color: transparent; border-image: url(minimize.png); color: white; font-weight: bold; }"
            "QPushButton:hover { background-color: #4a4a4a; }"
        )
        self.minimizeButton.clicked.connect(self.parent.showMinimized)
        layout.addWidget(self.minimizeButton)

        self.closeButton = QtWidgets.QPushButton("X")
        self.closeButton.setFixedSize(40, 40)
        self.closeButton.setStyleSheet(
            "QPushButton { background-color: transparent; border-image: url(close.png); color: white; font-weight: bold; }"
            "QPushButton:hover { background-color: #ff5555; }"
        )
        self.closeButton.clicked.connect(self.parent.close)
        layout.addWidget(self.closeButton)

        self.old_pos = None

        palette = self.palette()
        palette.setColor(QtGui.QPalette.Background, QtGui.QColor('#181c34'))
        self.setPalette(palette)

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.old_pos = event.globalPos()

    def mouseMoveEvent(self, event):
        if self.old_pos is not None:
            delta = event.globalPos() - self.old_pos
            self.parent.move(self.parent.pos() + delta)
            self.old_pos = event.globalPos()

    def mouseReleaseEvent(self, event):
        self.old_pos = None

class App(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.initUI()
        self.worker = None
        self.hotkey = None  # Initialize hotkey attribute

    def initUI(self):
        self.setWindowFlags(QtCore.Qt.FramelessWindowHint)
        self.setGeometry(100, 100, 400, 300)

        self.titleBar = CustomTitleBar(self)
        centralWidget = QtWidgets.QWidget()
        self.setCentralWidget(centralWidget)
        layout = QtWidgets.QVBoxLayout(centralWidget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.titleBar)

        content = QtWidgets.QWidget()
        contentLayout = QtWidgets.QVBoxLayout(content)
        layout.addWidget(content)

        palette = self.palette()
        palette.setColor(QtGui.QPalette.Background, QtGui.QColor('#181c34'))
        self.setPalette(palette)

        appIcon = QtGui.QIcon(os.path.join(CURRENT_DIR, 'icon.ico'))
        self.setWindowIcon(appIcon)

        pixmap = QtGui.QPixmap(IMAGE_PATH)
        pixmap = pixmap.scaled(100, 100, QtCore.Qt.KeepAspectRatio)

        self.logoLabel = QtWidgets.QLabel()
        self.logoLabel.setPixmap(pixmap)
        contentLayout.addWidget(self.logoLabel, alignment=QtCore.Qt.AlignCenter)

        self.usernameLabel = QtWidgets.QLabel("Hotkey:")
        self.usernameLabel.setStyleSheet("color: white;")
        contentLayout.addWidget(self.usernameLabel, alignment=QtCore.Qt.AlignCenter)

        self.hotkeyField = QtWidgets.QLineEdit()
        contentLayout.addWidget(self.hotkeyField, alignment=QtCore.Qt.AlignCenter)

        self.setButton = QtWidgets.QPushButton("Set!")
        self.setButton.clicked.connect(self.set_hotkey)
        contentLayout.addWidget(self.setButton, alignment=QtCore.Qt.AlignCenter)

        self.create_tray_icon()
        self.show()

    def set_hotkey(self):
        new_hotkey = self.hotkeyField.text().lower()
        if new_hotkey:
            if self.hotkey:
                keyboard.remove_hotkey(self.hotkey)
            self.hotkey = new_hotkey
            keyboard.add_hotkey(self.hotkey, self.toggle_scan)
            QtWidgets.QMessageBox.information(self, "Hotkey Set", f'Hotkey "{self.hotkey}" has been set!')

    def toggle_scan(self):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait()
            self.worker = None
            self.play_stop_sound()
        else:
            self.worker = OCRWorker()
            self.worker.resultReady.connect(self.handle_result)
            self.worker.notifyReady.connect(self.notify_user)
            self.worker.start()
            self.play_start_sound()

    def handle_result(self, message):
        print(message)
        pyperclip.copy(message)

    def notify_user(self, notification_message):
        QtWidgets.QMessageBox.information(self, "Scanning Complete", notification_message)

    def create_tray_icon(self):
        self.trayIcon = QtWidgets.QSystemTrayIcon(self)
        self.trayIcon.setIcon(QtGui.QIcon(IMAGE_PATH))
        self.trayIcon.setToolTip("QuickBuild Auto Scanner")

        showAction = QtWidgets.QAction("Show", self)
        showAction.triggered.connect(self.showNormal)

        quitAction = QtWidgets.QAction("Quit", self)
        quitAction.triggered.connect(self.close)

        trayMenu = QtWidgets.QMenu()
        trayMenu.addAction(showAction)
        trayMenu.addAction(quitAction)

        self.trayIcon.setContextMenu(trayMenu)
        self.trayIcon.show()

    def play_start_sound(self):
        winsound.Beep(500, 200)

    def play_stop_sound(self):
        winsound.Beep(300, 200)

if __name__ == '__main__':
    if not is_admin():
        run_as_admin()
        sys.exit()
    else:
        if not is_tesseract_installed():
            download_and_install_tesseract()

        if os.name == 'nt':
            ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)

        app = QtWidgets.QApplication(sys.argv)
        window = App()
        sys.exit(app.exec_())