### without  vlc but not working
from PyQt5.QtWidgets import (
    QApplication,
    QWidget,
    QAction,
    QPushButton,
    QHBoxLayout,
    QVBoxLayout,
    QLabel,
    QSlider,
    QStyle,
    QSizePolicy,
    QFileDialog,
    QLineEdit,
    QFormLayout,
    QGroupBox,
    QScrollArea,
    QMainWindow,
    QComboBox,
)
import sys
import os
import platform
import cv2

from PyQt5.QtMultimedia import (
    QMediaContent,
    QMediaPlayer,
    QVideoFrame,
    QAbstractVideoSurface,
    QAbstractVideoBuffer,
    QVideoSurfaceFormat,
)
from PyQt5.QtMultimediaWidgets import QVideoWidget
from PyQt5.QtGui import QIcon, QPalette, QImage, QPainter, QFont, QPixmap
from PyQt5.QtCore import Qt, QUrl, pyqtSignal, QPoint, QRect, QObject
from PyQt5.QtCore import *
from PyQt5.QtWidgets import *
from PyQt5 import QtWidgets
from functools import partial
import subprocess
import json
import time

USE_VLC = False
if USE_VLC:
    import vlc
    
    
# class Slider(QSlider):
#     def mousePressEvent(self, event, window):
#         if event.button() == Qt.LeftButton:
#             event.accept()
#             x = event.pos().x()
#             value = (
#                 self.maximum() - self.minimum()
#             ) * x / self.width() + self.minimum()
#             window.timer.stop()
#             # pos = self.slider.value()

#             window.mediaPlayer.set_position(value / 100000)
#             window.timer.start()
#         else:
#             return super().mousePressEvent(window, event)

#     def mouseMoveEvent(self, event, window):
#         event.accept()
#         x = event.pos().x()
#         value = (self.maximum() - self.minimum()) * x / self.width() + self.minimum()
#         window.mediaPlayer.set_position(value / 100000)
#         self.setValue(value)
class Slider(QSlider):
    def __init__(self, parent=None):
        super().__init__(Qt.Horizontal, parent)
        self.preview_label = None
        self.preview_timer = QTimer()
        self.preview_timer.timeout.connect(self.hide_preview)
        self.preview_timer.setSingleShot(True)
        self.is_dragging = False
        self.press_timer = QTimer()
        self.press_timer.timeout.connect(self.show_preview)
        self.press_timer.setSingleShot(True)
        
        # Make slider wider
        self.setMinimumWidth(600)  # Much wider than default
        self.setMinimumHeight(30)   # Taller for better interaction
        
        # Style the slider to be more prominent
        self.setStyleSheet("""
            QSlider::groove:horizontal {
                border: 1px solid #999999;
                height: 8px;
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                    stop:0 #B1B1B1, stop:1 #c4c4c4);
                margin: 2px 0;
                border-radius: 4px;
            }
            QSlider::handle:horizontal {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, 
                    stop:0 #b4b4b4, stop:1 #8f8f8f);
                border: 1px solid #5c5c5c;
                width: 18px;
                margin: -2px 0;
                border-radius: 3px;
            }
            QSlider::handle:horizontal:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, 
                    stop:0 #d4d4d4, stop:1 #afafaf);
            }
        """)

    def setup_preview(self, parent_window):
        """Setup preview functionality with parent window reference"""
        self.window = parent_window
        self.preview_label = QLabel(parent_window)
        self.preview_label.setFixedSize(50, 30)
        self.preview_label.setStyleSheet("""
            QLabel {
                border: 2px solid #333;
                background-color: black;
                border-radius: 5px;
            }
        """)
        self.preview_label.hide()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            event.accept()
            self.is_dragging = True
            
            # Calculate position and update media player
            x = event.pos().x()
            value = (self.maximum() - self.minimum()) * x / self.width() + self.minimum()
            
            if hasattr(self, 'window'):
                self.window.timer.stop()
                self.window.mediaPlayer.setPosition(value)
                self.window.timer.start()
            
            # Start timer for long press detection
            self.press_timer.start(500)  # 500ms for long press
            
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.is_dragging:
            event.accept()
            x = max(0, min(event.pos().x(), self.width()))
            value = (self.maximum() - self.minimum()) * x / self.width() + self.minimum()
            
            if hasattr(self, 'window'):
                self.window.mediaPlayer.setPosition(value)
            
            self.setValue(value)
            
            # Update preview if visible
            if self.preview_label and self.preview_label.isVisible():
                self.update_preview(value)
                self.position_preview(event.globalPos())

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.is_dragging = False
            self.press_timer.stop()
            
            # Hide preview after a delay
            if self.preview_label and self.preview_label.isVisible():
                self.preview_timer.start(1000)  # Hide after 1 second
                
        super().mouseReleaseEvent(event)

    def show_preview(self):
        """Show preview thumbnail on long press"""
        if self.preview_label and hasattr(self, 'window'):
            current_pos = self.value()
            self.update_preview(current_pos)
            self.preview_label.show()
            # Position preview above the slider
            slider_pos = self.mapToGlobal(self.pos())
            self.preview_label.move(
                slider_pos.x() + self.width() // 2 - self.preview_label.width() // 2,
                slider_pos.y() - self.preview_label.height() - 10
            )
            # Ensure the preview is on top of other widgets
            self.preview_label.raise_() # Add this line

    def hide_preview(self):
        """Hide the preview thumbnail"""
        if self.preview_label:
            self.preview_label.hide()

    def update_preview(self, slider_value):
        """Update preview image based on slider position"""
        if not hasattr(self, 'window') or not self.preview_label:
            return
            
        try:
            # Calculate timestamp from slider value
            duration = self.window.mediaPlayer.duration() / 1000.0  # Convert to seconds
            position = (slider_value / 100000) * duration
            
            # Get frame at position (this is a simplified example)
            # You'll need to adapt this to your media player's frame extraction method
            frame = self.extract_frame_at_position(position)
            
            if frame is not None:
                # Convert frame to QPixmap and display
                height, width, channel = frame.shape
                bytes_per_line = 3 * width
                q_image = QImage(frame.data, width, height, bytes_per_line, QImage.Format_RGB888).rgbSwapped()
                pixmap = QPixmap.fromImage(q_image)
                scaled_pixmap = pixmap.scaled(
                    self.preview_label.size(), 
                    Qt.KeepAspectRatio, 
                    Qt.SmoothTransformation
                )
                self.preview_label.setPixmap(scaled_pixmap)
                
        except Exception as e:
            print(f"Error updating preview: {e}")

    def extract_frame_at_position(self, position_seconds):
        """Extract frame at specific position - adapt this to your media player"""
        # This is a placeholder - you'll need to implement frame extraction
        # based on your media player (VLC, OpenCV, etc.)
        
        # Example with OpenCV (if you have the video file path):
        if hasattr(self.window, 'vid_path'):
            cap = cv2.VideoCapture(self.window.vid_path)
            fps = cap.get(cv2.CAP_PROP_FPS)
            frame_number = int(position_seconds * fps)
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
            ret, frame = cap.read()
            cap.release()
            return frame if ret else None
        
        return None

    def position_preview(self, global_pos):
        """Position preview near mouse cursor"""
        if self.preview_label:
            self.preview_label.move(
                global_pos.x() - self.preview_label.width() // 2,
                global_pos.y() - self.preview_label.height() - 20
            )


# Alternative: Extra Wide Slider with Timeline Marks
class TimelineSlider(Slider):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(800)  # Even wider
        self.setMinimumHeight(40)   # Taller
        self.timeline_marks = []    # Store timeline markers
        
    def paintEvent(self, event):
        super().paintEvent(event)
        
        # Draw timeline marks
        painter = QPainter(self)
        painter.setPen(Qt.gray)
        font = QFont()
        font.setPointSize(8)
        painter.setFont(font)
        
        # Draw time markers every 10% of the timeline
        for i in range(11):  # 0%, 10%, 20%, ... 100%
            x = int(i * self.width() / 10)
            painter.drawLine(x, self.height() - 15, x, self.height() - 5)
            
            # Calculate time text
            if hasattr(self, 'window') and hasattr(self.window, 'mediaPlayer'):
                total_time = self.window.mediaPlayer.duration() / 1000.0
                current_time = (i / 10.0) * total_time
                time_text = f"{int(current_time//60):02d}:{int(current_time%60):02d}"
                painter.drawText(x - 15, self.height() - 20, time_text)
                
################### Slider end ####################              
                
################## Menu Bar ########################

# class MenuBar(QMenuBar):
#     menuBar = QMenuBar(self)
#     self.setMenuBar(menuBar)
#     # --- Apply StyleSheet to fix the black background ---
#     # Set a light background for the menu bar itself
#     menuBar.setStyleSheet("""
#         QMenuBar {
#             background-color: lightgray; /* Or any color you prefer */
#             color: black; /* Ensure text is visible */
#         }
#         QMenuBar::item {
#             spacing: 3px; /* space between menu bar items */
#             padding: 1px 4px;
#             background: transparent;
#             color: black;
#         }
#         QMenuBar::item:selected { /* when selected using keyboard or mouse */
#             background: #a8a8a8;
#         }
#         QMenuBar::item:pressed {
#             background: #888888;
#         }
#         QMenu {
#             background-color: white; /* Background for dropdown menus */
#             border: 1px solid #888;
#             color: black; /* Ensure text is visible */
#         }
#         QMenu::item {
#             padding: 2px 25px 2px 20px;
#             border: 1px solid transparent; /* reserve space for selection border */
#         }
#         QMenu::item:selected {
#             border-color: darkblue;
#             background-color: #f0f0f0; /* Light highlight on hover */
#         }
#         QMenu::item:disabled {
#             color: #b0b0b0;
#         }
#     """)                
            

class Window(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Surgical Video Player")
        self.setGeometry(350, 100, 700, 500)
        # Remove icon dependency
        # self.setWindowIcon(QIcon("player.png"))

        p = self.palette()
        p.setColor(QPalette.Window, Qt.black)
        self.setPalette(p)

        self.setFocusPolicy(Qt.StrongFocus)

        self.num_panels = 0
        self.is_paused = False

        qApp.installEventFilter(self)
        self.init_ui()

        self.showMaximized()
        
        # Use Qt's built-in media player
        self.mediaPlayer = QMediaPlayer(None, QMediaPlayer.VideoSurface)
        self.videowidget = QVideoWidget()
        self.mediaPlayer.setVideoOutput(self.videowidget)
        
        # Connect media player signals
        self.mediaPlayer.stateChanged.connect(self.mediaStateChanged)
        self.mediaPlayer.positionChanged.connect(self.positionChanged)
        self.mediaPlayer.durationChanged.connect(self.durationChanged)
        self.mediaPlayer.error.connect(self.handleError)
        
    def createMenuBar(self):
        # Create menu bar
        menuBar = QMenuBar(self)
        
        # Apply StyleSheet to fix the black background
        menuBar.setStyleSheet("""
            QMenuBar {
                background-color: lightgray;
                color: black;
                min-height: 20px;
                max-height: 30px;
            }
            QMenuBar::item {
                spacing: 3px;
                padding: 1px 4px;
                background: transparent;
                color: black;
            }
            QMenuBar::item:selected {
                background: #a8a8a8;
            }
            QMenuBar::item:pressed {
                background: #888888;
            }
            QMenu {
                background-color: white;
                border: 1px solid #888;
                color: black;
            }
            QMenu::item {
                padding: 2px 25px 2px 20px;
                border: 1px solid transparent;
            }
            QMenu::item:selected {
                border-color: darkblue;
                background-color: #f0f0f0;
            }
            QMenu::item:disabled {
                color: #b0b0b0;
            }
        """)
        
        fileMenu = menuBar.addMenu("&File")
        HelpMenu = menuBar.addMenu("&Help")

        openVideoAction = QAction("&Open Video", self)
        openVideoAction.setShortcut("Ctrl+O")
        openVideoAction.setStatusTip("Open Video")
        openVideoAction.triggered.connect(self.open_video)

        addTimePanelFileAction = QAction("&Add Timestamping Panel", self)
        addTimePanelFileAction.setStatusTip("Add Timestamping Panel From File")
        addTimePanelFileAction.triggered.connect(self.add_time_panel_from_file)

        addRatingPanelFileAction = QAction("&Add Rating Panel", self)
        addRatingPanelFileAction.setStatusTip("Add Rating Panel From File")
        addRatingPanelFileAction.triggered.connect(self.add_rating_panel_from_file)

        saveEntriesAction = QAction("&Save", self)
        saveEntriesAction.setStatusTip("Save all entries")
        saveEntriesAction.setShortcut("Ctrl+S")
        saveEntriesAction.triggered.connect(self.save)

        clearPanelsAction = QAction("&Clear Panels", self)
        clearPanelsAction.setStatusTip("Clear all panels")
        clearPanelsAction.setShortcut("Ctrl+C")
        clearPanelsAction.triggered.connect(self.clearPanels)

        changeSaveDirectoryAction = QAction("&Change Save Directory", self)
        changeSaveDirectoryAction.setStatusTip("Change Save Directory")
        changeSaveDirectoryAction.triggered.connect(self.changeDirectory)

        exitAction = QAction("&Exit", self)
        exitAction.setStatusTip("Exit")
        exitAction.setShortcut("Ctrl+Q")
        exitAction.triggered.connect(self.close)

        fileMenu.addAction(openVideoAction)
        fileMenu.addAction(addTimePanelFileAction)
        fileMenu.addAction(addRatingPanelFileAction)
        fileMenu.addAction(changeSaveDirectoryAction)
        fileMenu.addAction(saveEntriesAction)
        fileMenu.addAction(clearPanelsAction)
        fileMenu.addAction(exitAction)
        
        return menuBar
    
    def init_ui(self):
        # Create the directory where the outputs for all videos are saved
        self.videowidget = QVideoWidget()

        # Create open button
        openBtn = QPushButton("Open Video")
        openBtn.clicked.connect(self.open_video)

        # Create button for taking a snapshot
        snapBtn = QPushButton("snapshot (save the image)")
        snapBtn.clicked.connect(self.screenshotCall)
        self.ImagesBuffer = None

        labelmeBtn = QPushButton("Annotate (labelme)")
        labelmeBtn.clicked.connect(self.annotate)

        # Create button for playing
        self.playBtn = QPushButton()
        self.playBtn.setEnabled(False)
        self.playBtn.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
        self.playBtn.clicked.connect(self.play_video)

        self.playbackspeedBtn = QComboBox()
        self.playbackspeedBtn.addItems(["1X", "1.5X", "2X", "3X"])
        self.playbackspeedBtn.currentIndexChanged.connect(self.set_speed)

        # Create slider
        self.slider = Slider()
        self.slider.setup_preview(self)
        self.slider.setMaximum(1000)
        self.slider.sliderMoved.connect(self.position_changed)
        self.slider.sliderPressed.connect(self.position_changed)

        # Create time labels
        self.l = QLabel("0:00:00")
        self.l.setStyleSheet("color: white")
        self.d = QLabel("0:00:00")
        self.d.setStyleSheet("color: white")

        # Create label
        self.label = QLabel()
        self.label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)

        # Create hbox layout
        hboxLayout = QHBoxLayout()
        hboxLayout.setContentsMargins(0, 0, 0, 0)
        hboxLayout.addWidget(self.playBtn)
        hboxLayout.addWidget(self.playbackspeedBtn)
        hboxLayout.addWidget(self.l)
        hboxLayout.addWidget(self.slider)
        hboxLayout.addWidget(self.d)

        bottomLayout = QHBoxLayout()
        bottomLayout.addWidget(openBtn)
        bottomLayout.addWidget(snapBtn)
        bottomLayout.addWidget(labelmeBtn)

        menuBar = self.createMenuBar()
        
        # Create vbox layout
        vboxLayout = QVBoxLayout()
        vboxLayout.addWidget(menuBar)
        vboxLayout.addWidget(self.videowidget)
        vboxLayout.addLayout(hboxLayout)
        vboxLayout.addLayout(bottomLayout)
        vboxLayout.addWidget(self.label)

        self.mainLayout = QHBoxLayout()
        self.mainLayout.addLayout(vboxLayout)

        # Create empty lists for the panels to be added
        self.groupbox = [None] * 10
        self.formLayout = [None] * 10
        self.form_title = [None] * 10
        self.panelRemoveBtn = [None] * 10
        self.scroll = [None] * 10
        self.tasklist = [None] * 10
        self.startingButtonlist = [None] * 10
        self.startingTimelist = [None] * 10
        self.endingButtonlist = [None] * 10
        self.endingTimelist = [None] * 10
        self.saveEntryBtn = [None] * 10
        self.clearEntryBtn = [None] * 10
        self.ratingButtonslist = [None] * 10
        self.yesButtonlist = [None] * 10
        self.noButtonlist = [None] * 10
        self.ratingItemlist = [None] * 10
        self.groupButtonlist = [None] * 10

        # Timer for updating UI
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self.update_ui)

        self.setLayout(self.mainLayout)

        self.parrentDirectory = None
        self.save_directory = None
        self.vidname = None
        self.image = None
        self.image_save_directory = None
        self.segmentation_labels = set()

        self.setup_video_click()
        
        # Load predefined panels if they exist
        self.add_time_panel_from_file_predefined("samples/phase.txt")
        self.add_time_panel_from_file_predefined("samples/task.txt")

    def setup_video_click(self):
        """Setup video widget to respond to mouse clicks"""
        self.videowidget.mousePressEvent = self.video_clicked

    def video_clicked(self, event):
        """Handle video widget mouse clicks"""
        if event.button() == Qt.LeftButton:
            self.play_video()

    def eventFilter(self, obj, event):
        if event.type() == QEvent.KeyPress and event.key() == Qt.Key_Space:
            self.play_video()
            return True
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Space:
            self.play_video()
            event.accept()
            return
        elif event.key() == Qt.Key_Right:
            # Skip forward 5 seconds
            pos = self.mediaPlayer.position()
            self.mediaPlayer.setPosition(pos + 5000)
        elif event.key() == Qt.Key_Left:
            # Skip backward 5 seconds
            pos = self.mediaPlayer.position()
            self.mediaPlayer.setPosition(max(0, pos - 5000))
        elif event.key() == Qt.Key_F5:
            self.close()
        else:
            super().keyPressEvent(event)

    def open_video(self):
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Open Video",
            os.path.expanduser("~"),
            "Video Files (*.mp4 *.avi *.mov *.mpg *.mkv *.wmv *.flv)",
        )

        if filename != "":
            # Set media content
            self.vid_path = filename
            self.mediaPlayer.setMedia(QMediaContent(QUrl.fromLocalFile(filename)))
            self.setWindowTitle(os.path.basename(filename))
            self.playBtn.setEnabled(True)

            # Initialize OpenCV capture for screenshots
            self.cap = cv2.VideoCapture(filename)
            
            # Start playing
            self.play_video()

            # Setup directories
            if not self.parrentDirectory:
                self.parrentDirectory = "./outputs"
                if not os.path.exists(self.parrentDirectory):
                    os.mkdir(self.parrentDirectory)

            self.vidname = os.path.basename(filename)
            print("Saving directory: ", self.parrentDirectory + "/" + self.vidname)
            if not os.path.exists(self.parrentDirectory + "/" + self.vidname):
                os.mkdir(self.parrentDirectory + "/" + self.vidname)
            self.save_directory = self.parrentDirectory + "/" + self.vidname

            if not os.path.exists(self.parrentDirectory + "/" + self.vidname + "/images"):
                os.mkdir(self.parrentDirectory + "/" + self.vidname + "/images")
            self.image_save_directory = self.parrentDirectory + "/" + self.vidname + "/images"

            # Clear panels if needed
            if self.num_panels > 0:
                self.clearPanels()

    def play_video(self):
        if self.mediaPlayer.state() == QMediaPlayer.PlayingState:
            self.mediaPlayer.pause()
            self.is_paused = True
            self.playBtn.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
        else:
            self.mediaPlayer.play()
            self.is_paused = False
            self.playBtn.setIcon(self.style().standardIcon(QStyle.SP_MediaPause))

    def mediaStateChanged(self, state):
        if state == QMediaPlayer.PlayingState:
            self.timer.start()
        else:
            self.timer.stop()

    def positionChanged(self, position):
        self.slider.setValue(int(position * 1000 / max(1, self.mediaPlayer.duration())))
        self.display_time()

    def durationChanged(self, duration):
        self.slider.setRange(0, 1000)
        self.d.setText(self.format_time(duration))

    def handleError(self):
        self.playBtn.setEnabled(False)
        self.label.setText("Error: " + self.mediaPlayer.errorString())

    def format_time(self, ms):
        seconds = ms // 1000
        minutes = seconds // 60
        hours = minutes // 60
        return "%d:%02d:%02d" % (hours, minutes % 60, seconds % 60)

    def display_time(self):
        position = self.mediaPlayer.position()
        self.l.setText(self.format_time(position))

    def position_changed(self):
        pos = self.slider.value()
        duration = self.mediaPlayer.duration()
        if duration > 0:
            self.mediaPlayer.setPosition(int(pos * duration / 1000))

    def set_speed(self, index):
        rates = [1.0, 1.5, 2.0, 3.0]
        if index < len(rates):
            self.mediaPlayer.setPlaybackRate(rates[index])

    def screenshotCall(self):
        if self.mediaPlayer.state() == QMediaPlayer.PlayingState:
            self.mediaPlayer.pause()
            self.is_paused = True
            self.playBtn.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))

        if self.vidname and hasattr(self, 'cap'):
            # Get current position in milliseconds
            pos = self.mediaPlayer.position()
            self.cap.set(cv2.CAP_PROP_POS_MSEC, pos)
            ret, self.frame = self.cap.read()
            
            if ret and self.image_save_directory:
                self.image = os.path.join(
                    self.image_save_directory, 
                    f"{os.path.splitext(self.vidname)[0]}_Frame{pos}.png"
                )
                cv2.imwrite(self.image, self.frame)
                print(f"Screenshot saved: {self.image}")

    def update_ui(self):
        # Update slider position based on media player position
        if self.mediaPlayer.duration() > 0:
            pos = int(self.mediaPlayer.position() * 1000 / self.mediaPlayer.duration())
            self.slider.setValue(pos)

    def changeDirectory(self):
        self.parrentDirectory = QFileDialog.getExistingDirectory(self, "Select Folder")
        if self.vidname and self.parrentDirectory:
            if not os.path.exists(self.parrentDirectory + "/" + self.vidname):
                os.mkdir(self.parrentDirectory + "/" + self.vidname)
            self.save_directory = self.parrentDirectory + "/" + self.vidname

            if not os.path.exists(self.parrentDirectory + "/" + self.vidname + "/images"):
                os.mkdir(self.parrentDirectory + "/" + self.vidname + "/images")
            self.image_save_directory = self.parrentDirectory + "/" + self.vidname + "/images"

            print("Saving directory: ", self.parrentDirectory + "/" + self.vidname)

    def add_time_panel_from_file_predefined(self, filepath):
        if os.path.exists(filepath):
            self.load_panel_from_file(filepath, self.add_time_panel_from_file)

    def add_rating_panel_from_file_predefined(self, filepath):
        if os.path.exists(filepath):
            self.load_panel_from_file(filepath, self.add_rating_panel_from_file)

    def load_panel_from_file(self, filepath, add_func):
        original_getOpenFileName = QFileDialog.getOpenFileName
        QFileDialog.getOpenFileName = lambda *args, **kwargs: (filepath, True)
        add_func()
        QFileDialog.getOpenFileName = original_getOpenFileName

    def add_time_panel_from_file(self):
        filename, _ = QFileDialog.getOpenFileName(
            self, "Open Text", filter="Text files (*.txt)"
        )

        if filename != "":
            title = str(os.path.basename(filename)).split(".")[0]
            with open(filename) as f:
                lines = f.read().splitlines()
            print("Opened time panel:", title)

            self.num_panels += 1
            self.panel_index = self.num_panels

            self.tasklist[self.panel_index] = []
            self.startingButtonlist[self.panel_index] = []
            self.startingTimelist[self.panel_index] = []
            self.endingButtonlist[self.panel_index] = []
            self.endingTimelist[self.panel_index] = []
            self.saveEntryBtn[self.panel_index] = []
            self.clearEntryBtn[self.panel_index] = []

            self.groupbox[self.panel_index] = QGroupBox()
            self.formLayout[self.panel_index] = QFormLayout()

            self.form_title[self.panel_index] = QLabel(title)
            self.form_title[self.panel_index].setStyleSheet("color: white")
            self.form_title[self.panel_index].setAlignment(Qt.AlignCenter)
            self.form_title[self.panel_index].setFont(QFont("Times", 12, weight=QFont.Bold))

            self.formLayout[self.panel_index].addRow(self.form_title[self.panel_index])

            for i, line in enumerate(lines):
                line = line.split("#")

                self.tasklist[self.panel_index].append(QLabel(line[0]))
                self.tasklist[self.panel_index][i].setStyleSheet("background-color: black ; color: white")
                self.tasklist[self.panel_index][i].setFont(QFont("Times", 10, weight=QFont.Bold))
                self.tasklist[self.panel_index][i].setWordWrap(True)
                
                self.startingButtonlist[self.panel_index].append(QPushButton("starts"))
                self.startingButtonlist[self.panel_index][i].setFixedWidth(50)
                self.startingTimelist[self.panel_index].append(QLabel("0:00:00"))
                self.startingTimelist[self.panel_index][i].setStyleSheet("color: white")
                self.startingButtonlist[self.panel_index][i].clicked.connect(
                    partial(self.onstartbuttonClicked, self.panel_index, i)
                )
                
                self.endingButtonlist[self.panel_index].append(QPushButton("ends"))
                self.endingButtonlist[self.panel_index][i].setFixedWidth(50)
                self.endingTimelist[self.panel_index].append(QLabel("0:00:00"))
                self.endingTimelist[self.panel_index][i].setStyleSheet("color: white")
                self.endingButtonlist[self.panel_index][i].clicked.connect(
                    partial(self.onendbuttonClicked, self.panel_index, i)
                )
                
                if len(line) == 3:
                    self.startingButtonlist[self.panel_index][i].setToolTip(line[1])
                    self.endingButtonlist[self.panel_index][i].setToolTip(line[2])
                
                self.saveEntryBtn[self.panel_index].append(QPushButton("save"))
                self.clearEntryBtn[self.panel_index].append(QPushButton("clear"))
                self.saveEntryBtn[self.panel_index][i].setFixedWidth(50)
                self.clearEntryBtn[self.panel_index][i].setFixedWidth(50)
                self.saveEntryBtn[self.panel_index][i].setEnabled(False)
                self.saveEntryBtn[self.panel_index][i].clicked.connect(
                    partial(self.onsaveEntryBtnClicked, self.panel_index, i)
                )
                self.clearEntryBtn[self.panel_index][i].setEnabled(False)
                self.clearEntryBtn[self.panel_index][i].clicked.connect(
                    partial(self.onclearEntryBtnClicked, self.panel_index, i)
                )

                self.formLayout[self.panel_index].addRow(self.tasklist[self.panel_index][i])
                self.formLayout[self.panel_index].addRow(
                    self.startingButtonlist[self.panel_index][i],
                    self.startingTimelist[self.panel_index][i],
                )
                self.formLayout[self.panel_index].addRow(
                    self.endingButtonlist[self.panel_index][i],
                    self.endingTimelist[self.panel_index][i],
                )
                self.formLayout[self.panel_index].addRow(
                    self.saveEntryBtn[self.panel_index][i],
                    self.clearEntryBtn[self.panel_index][i],
                )

            # Add "Save All" button for this time panel
            saveAllBtn = QPushButton("Save All")
            saveAllBtn.clicked.connect(lambda _, idx=self.panel_index: self.save_panel(idx))
            self.formLayout[self.panel_index].addRow(saveAllBtn)

            self.groupbox[self.panel_index].setLayout(self.formLayout[self.panel_index])

            self.scroll[self.panel_index] = QScrollArea()
            self.scroll[self.panel_index].setWidget(self.groupbox[self.panel_index])
            self.scroll[self.panel_index].setWidgetResizable(True)
            self.scroll[self.panel_index].setFixedWidth(150)
            self.scroll[self.panel_index].setFocusPolicy(Qt.StrongFocus)
            self.mainLayout.addWidget(self.scroll[self.panel_index])

    def add_rating_panel_from_file(self):
        filename, _ = QFileDialog.getOpenFileName(
            self, "Open Text", filter="Text files (*.txt)"
        )

        if filename != "" and str(filename).endswith(".txt"):
            title = str(os.path.basename(filename)).split(".")[0]

            with open(filename) as f:
                lines = f.read().splitlines()
            print("Opened rating panel:", title)

            self.num_panels += 1
            self.panel_index = self.num_panels

            self.tasklist[self.panel_index] = []
            self.yesButtonlist[self.panel_index] = []
            self.noButtonlist[self.panel_index] = []
            self.ratingButtonslist[self.panel_index] = []
            self.groupButtonlist[self.panel_index] = []

            self.groupbox[self.panel_index] = QGroupBox()
            self.formLayout[self.panel_index] = QFormLayout()
            self.formLayout[self.panel_index].setVerticalSpacing(10)
            
            self.form_title[self.panel_index] = QLabel(title)
            self.form_title[self.panel_index].setStyleSheet("color: white")
            self.form_title[self.panel_index].setAlignment(Qt.AlignCenter)
            self.form_title[self.panel_index].setFont(QFont("Times", 12, weight=QFont.Bold))

            self.formLayout[self.panel_index].addRow(self.form_title[self.panel_index])
            
            for i, line in enumerate(lines):
                line = line.split("#")

                num_scores = 2
                if len(line) > 1:
                    try:
                        num_scores = int(line[1])
                    except:
                        num_scores = 2

                self.tasklist[self.panel_index].append(QLabel(line[0]))
                self.tasklist[self.panel_index][i].setStyleSheet("background-color: black ; color: white")
                self.tasklist[self.panel_index][i].setFont(QFont("Times", 10, weight=QFont.Bold))
                self.tasklist[self.panel_index][i].setWordWrap(True)
                self.tasklist[self.panel_index][i].setFixedWidth(100)

                self.ratingButtonslist[self.panel_index].append([])

                for j in range(num_scores):
                    self.ratingButtonslist[self.panel_index][i].append(QRadioButton(str(j)))
                    self.ratingButtonslist[self.panel_index][i][j].setStyleSheet("background-color: black ; color: white")

                self.groupButtonlist[self.panel_index].append(QButtonGroup())
                for j in range(num_scores):
                    self.groupButtonlist[self.panel_index][i].addButton(
                        self.ratingButtonslist[self.panel_index][i][j]
                    )
                
                self.groupButtonlist[self.panel_index][i].buttonClicked.connect(
                    partial(self.save_rating_entry, self.panel_index, i)
                )

                hbLayout = QHBoxLayout()
                for j in range(num_scores):
                    hbLayout.addWidget(self.ratingButtonslist[self.panel_index][i][j])
                hbLayout.setContentsMargins(0, 0, 0, 0)
                container = QWidget()
                container.setLayout(hbLayout)
                self.formLayout[self.panel_index].addRow(self.tasklist[self.panel_index][i], container)

            # Add "Save All Ratings" button for this rating panel
            saveAllRatingsBtn = QPushButton("Save All Ratings")
            saveAllRatingsBtn.clicked.connect(lambda _, idx=self.panel_index: self.save_all_ratings(idx))
            self.formLayout[self.panel_index].addRow(saveAllRatingsBtn)

            self.groupbox[self.panel_index].setLayout(self.formLayout[self.panel_index])
            
            self.scroll[self.panel_index] = QScrollArea()
            self.scroll[self.panel_index].setWidget(self.groupbox[self.panel_index])
            self.scroll[self.panel_index].setWidgetResizable(True)
            self.scroll[self.panel_index].setFixedWidth(300)
            self.scroll[self.panel_index].setFocusPolicy(Qt.StrongFocus)
            self.mainLayout.addWidget(self.scroll[self.panel_index])

            # Load existing ratings if file exists
            if self.save_directory and os.path.exists(
                f"{self.save_directory}/{self.form_title[self.panel_index].text()}_scores.txt"
            ):
                self.load_existing_ratings(self.panel_index)
            elif self.save_directory:
                self.create_rating_file(self.panel_index)

    def getCurrentTimeString(self):
        """Get current playback time as formatted string"""
        position = self.mediaPlayer.position()
        return self.format_time(position)

    def onstartbuttonClicked(self, panel_index, i):
        value = self.getCurrentTimeString()
        self.startingTimelist[panel_index][i].setText(str(value))
        self.startingTimelist[panel_index][i].setStyleSheet("color: white")
        self.saveEntryBtn[panel_index][i].setEnabled(False)
        self.clearEntryBtn[panel_index][i].setEnabled(True)

    def onendbuttonClicked(self, panel_index, i):
        value = self.getCurrentTimeString()
        self.endingTimelist[panel_index][i].setText(str(value))
        self.endingTimelist[panel_index][i].setStyleSheet("color: white")
        self.saveEntryBtn[panel_index][i].setEnabled(True)
        self.clearEntryBtn[panel_index][i].setEnabled(True)

    def onsaveEntryBtnClicked(self, panel_index, i):
        self.saveEntryBtn[panel_index][i].setEnabled(False)
        form_title = self.form_title[panel_index].text()
        task_name = self.tasklist[panel_index][i].text()
        starting_time = self.startingTimelist[panel_index][i].text()
        ending_time = self.endingTimelist[panel_index][i].text()
        
        if self.save_directory:
            with open(f"{self.save_directory}/{form_title}.txt", "a") as f:
                f.write(f"{task_name} : ({starting_time},{ending_time})\n")

    def save_panel(self, panel_index):
        """
        Save every time-entry in this time-panel.
        """
        # loop through each task in this panel
        for i in range(len(self.tasklist[panel_index])):
            # only save if there’s a non-default interval
            start = self.startingTimelist[panel_index][i].text()
            end   = self.endingTimelist[panel_index][i].text()
            if start != "0" or end != "0":
                self.onsaveEntryBtnClicked(panel_index, i)
    def save_all_ratings(self, panel_index):
        """
        Save all checked rating entries in this panel.
        """
        for i, btns in enumerate(self.ratingButtonslist[panel_index]):
            # if any button in the group is selected
            if any(b.isChecked() for b in btns):
                self.save_rating_entry(panel_index, i)

    def onclearEntryBtnClicked(self, panel_index, i):
        self.saveEntryBtn[panel_index][i].setEnabled(False)
        self.clearEntryBtn[panel_index][i].setEnabled(False)
        self.startingTimelist[panel_index][i].setText("0")
        self.endingTimelist[panel_index][i].setText("0")

    def screenshotCall(self):
        # pause video if playing
        if self.mediaPlayer.state() == QMediaPlayer.PlayingState:
            # self.set_speed(0)
            self.mediaPlayer.pause()
            self.is_paused = True
            ##self.mediaPlayer_g.pause()
            self.playBtn.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
            self.timer.stop()

        if self.vidname:
            frame_num = int(
                self.mediaPlayer.position() * (self.media.get_duration())
            )
            self.cap.set(cv2.CAP_PROP_POS_MSEC, frame_num)  # Go to the 1 msec. position
            (
                ret,
                self.frame,
            ) = self.cap.read()  # Retrieves the frame at the specified second
            if self.image_save_directory:
                self.image = self.image_save_directory + "/{}Frame{}.png".format(
                    str(self.vidname).split(".")[-2], str(frame_num)
                )
            cv2.imwrite(self.image, self.frame)

    def set_player_position(self, position):

        # self.slider.setValue(position)
        self.timer.stop()
        pos = self.slider.value()

        self.mediaPlayer.setPosition(
            position / 100000
        )  # / (self.media.get_duration()))
        self.timer.start()
        
    def buffer_frame(self, image):
        self.ImagesBuffer = image

    def update_ui(self):

        media_pos = int(self.mediaPlayer.position() * 100000)
        self.slider.setValue(media_pos)
        # No need to call this function if nothing is played
        if not self.mediaPlayer.state() == QMediaPlayer.PlayingState:
            self.timer.stop()
            # After the video finished, the play button stills shows "Pause",
            # which is not the desired behavior of a media player.
            # This fixes that "bug".
            if not self.is_paused:
                self.stop()
                
    def stop(self):
        """Stop player"""
        self.mediaPlayer.stop()
        self.playBtn.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))

    def set_speed(self, i):
        if i == 0:
            self.mediaPlayer.set_rate(1)
        elif i == 1:
            self.mediaPlayer.set_rate(1.5)
        elif i == 2:
            self.mediaPlayer.set_rate(2)
        elif i == 3:
            self.mediaPlayer.set_rate(3)

    def save(self):
        value = 0

        if self.num_panels != 0:
            for panel_index in range(1, self.num_panels + 1):
                if self.startingButtonlist[panel_index]:
                    for i in range(len(self.startingButtonlist[panel_index])):
                        if self.saveEntryBtn[panel_index][i].isEnabled():
                            # if self.startingTimelist[panel_index][i].text() != str(value) and self.endingTimelist[panel_index][
                            #   i].text() != str(value):
                            self.onsaveEntryBtnClicked(panel_index, i)

    def annotate(self):
        if self.image_save_directory:
            for json_file in os.listdir(self.image_save_directory):
                if json_file.endswith(".json"):
                    with open(
                        os.path.join(self.image_save_directory, json_file)
                    ) as annotation_file:
                        data = json.load(annotation_file)
                        for shape in data["shapes"]:
                            if shape["label"]:
                                if not shape["label"] in self.segmentation_labels:
                                    self.segmentation_labels.add(shape["label"])

        if self.image:
            if len(self.segmentation_labels) == 0:
                subprocess.Popen(
                    [
                        "labelme",
                        "{}".format(self.image),
                        "--output",
                        "{}".format(
                            self.image.replace(self.image.split(".")[-1], "json")
                        ),
                    ]
                )
            else:
                labels = ",".join(l for l in self.segmentation_labels)
                print(labels)
                subprocess.Popen(
                    [
                        "labelme",
                        "{}".format(self.image),
                        "--output",
                        "{}".format(
                            self.image.replace(self.image.split(".")[-1], "json")
                        ),
                        "--labels",
                        labels,
                    ]
                )

    def save_rating_entry(self, panel_index, i):
        if self.vidname:
            form_title = self.form_title[panel_index].text()
            rating_item = self.tasklist[panel_index][i].text()
            score = None

            for j in range(len(self.ratingButtonslist[panel_index][i])):
                if self.ratingButtonslist[panel_index][i][j].isChecked():
                    score = self.ratingButtonslist[panel_index][i][j].text()

            # if self.yesButtonlist[panel_index][i].isChecked():
            #     score = 'Yes'
            # elif self.noButtonlist[panel_index][i].isChecked():
            #     score = 'No'

            with open(
                "{}/{}_scores.txt".format(self.save_directory, form_title), "r"
            ) as f:
                lines = f.readlines()
                for index, line in enumerate(lines):
                    if line.startswith(rating_item):
                        lines[index] = "{} : {}\n".format(rating_item, score)

            with open(
                "{}/{}_scores.txt".format(self.save_directory, form_title), "w"
            ) as f:
                for line in lines:
                    f.write(line)

    def clearPanels(self):
        value = 0

        if self.num_panels != 0:

            for panel_index in range(1, self.num_panels + 1):

                if self.startingTimelist[panel_index]:
                    for i in range(len(self.startingTimelist[panel_index])):
                        self.startingTimelist[panel_index][i].setText(str(value))
                        self.startingTimelist[panel_index][i].setStyleSheet(
                            "color: white"
                        )
                        self.endingTimelist[panel_index][i].setText(str(value))
                        self.endingTimelist[panel_index][i].setStyleSheet(
                            "color: white"
                        )
                        self.saveEntryBtn[panel_index][i].setEnabled(False)
                        self.clearEntryBtn[panel_index][i].setEnabled(False)
                elif self.groupButtonlist[panel_index]:
                    for i in range(len(self.groupButtonlist[panel_index])):
                        self.groupButtonlist[panel_index][i].setExclusive(False)
                        for j in range(len(self.ratingButtonslist[panel_index][i])):
                            if self.ratingButtonslist[panel_index][i][j]:
                                self.ratingButtonslist[panel_index][i][j].setChecked(
                                    False
                                )
                        # self.yesButtonlist[panel_index][i].setChecked(False)
                        # self.noButtonlist[panel_index][i].setChecked(False)
                        self.groupButtonlist[panel_index][i].setExclusive(True)
                        # unchdeck all

    def close(self):
        sys.exit(app.exec_())


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = Window()
    sys.exit(app.exec_())