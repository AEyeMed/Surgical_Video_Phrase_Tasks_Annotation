### Working 
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


QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

USE_VLC = True
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
                self.window.mediaPlayer.set_position(value / 100000)
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
                self.window.mediaPlayer.set_position(value / 100000)
            
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
            duration = self.window.mediaPlayer.get_length() / 1000.0  # Convert to seconds
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
                total_time = self.window.mediaPlayer.get_length() / 1000.0
                current_time = (i / 10.0) * total_time
                time_text = f"{int(current_time//60):02d}:{int(current_time%60):02d}"
                painter.drawText(x - 15, self.height() - 20, time_text)
                
################### Slider end ####################              
                
       
            

class Window(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Surgical Video Player")
        self.setGeometry(350, 100, 700, 500)
        self.setWindowIcon(QIcon("player.png"))

        p = self.palette()
        p.setColor(QPalette.Window, Qt.black)
        self.setPalette(p)

        self.setFocusPolicy(Qt.StrongFocus)

        self.num_panels = 0

        self.is_paused = False

        qApp.installEventFilter(self)
        self.init_ui()

        self.showMaximized()
        
        if not USE_VLC:
            self.mediaPlayer = QMediaPlayer(None, QMediaPlayer.VideoSurface)
            self.videowidget = QVideoWidget()
            self.mediaPlayer.setVideoOutput(self.videowidget)
        
    def createMenuBar(self):

        # Create menu bar
        menuBar = QMenuBar(self)


        # Set a light background for the menu bar itself
        menuBar.setStyleSheet("""
            QMenuBar {
                background-color: lightgray; /* Or any color you prefer */
                color: black; /* Ensure text is visible */
                min-height: 20px; /* Set your desired minimum height */
                max-height: 30px; /* Set your desired maximum height, often same as min-height */
            }
            QMenuBar::item {
                spacing: 3px; /* space between menu bar items */
                padding: 1px 4px;
                background: transparent;
                color: black;
            }
            QMenuBar::item:selected { /* when selected using keyboard or mouse */
                background: #a8a8a8;
            }
            QMenuBar::item:pressed {
                background: #888888;
            }
            QMenu {
                background-color: white; /* Background for dropdown menus */
                border: 1px solid #888;
                color: black; /* Ensure text is visible */
            }
            QMenu::item {
                padding: 2px 25px 2px 20px;
                border: 1px solid transparent; /* reserve space for selection border */
            }
            QMenu::item:selected {
                border-color: darkblue;
                background-color: #f0f0f0; /* Light highlight on hover */
            }
            QMenu::item:disabled {
                color: #b0b0b0;
            }
        """)
        # menuBar.setStyleSheet("color: white")
        fileMenu = menuBar.addMenu("&File")
        HelpMenu = menuBar.addMenu("&Help")

        openVideoAction = QAction("&Open Video", self)
        openVideoAction.setShortcut("Ctrl+O")
        openVideoAction.setStatusTip("Open Video")
        openVideoAction.triggered.connect(self.open_video)

        addPanelAction = QAction("&Add Panel", self)
        addPanelAction.setStatusTip("Add Panel")
        addPanelAction.triggered.connect(self.add_panel)

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

        # fileMenu.addAction(addPanelAction)
        fileMenu.addAction(openVideoAction)
        fileMenu.addAction(addTimePanelFileAction)
        fileMenu.addAction(addRatingPanelFileAction)
        fileMenu.addAction(changeSaveDirectoryAction)
        fileMenu.addAction(saveEntriesAction)
        fileMenu.addAction(clearPanelsAction)
        fileMenu.addAction(exitAction)
        
        
        
        return menuBar
    
    def init_ui(self):
        # create the directory where the outputs for all videos are saved

        if USE_VLC:
            self.instance = vlc.Instance()
            self.media = None
            # create media player object
            self.mediaPlayer = (
                self.instance.media_player_new()
            )  # QMediaPlayer(None, QMediaPlayer.VideoSurface)

        # In this widget, the video will be drawn
        if platform.system() == "Darwin":  # for MacOS
            self.videowidget = QtWidgets.QMacCocoaViewContainer(0)
        elif platform.system() == "Windows":
            self.videowidget = QtWidgets.QFrame()
        else:
            # self.videowidget = QtWidgets.QMacCocoaViewContainer(0)
            self.videowidget = QtWidgets.QFrame()
        # create videowidget object
        # self.videowidget = QVideoWidget()
        self.videowidget_g = QVideoWidget()

        # create open button
        openBtn = QPushButton("Open Video")
        openBtn.clicked.connect(self.open_video)

        # create button for taking a snapshot
        snapBtn = QPushButton("snapshot (save the image)")
        snapBtn.clicked.connect(self.screenshotCall)
        # snapBtn.setEnabled(True)
        self.ImagesBuffer = None

        labelmeBtn = QPushButton("Annotate (labelme)")
        labelmeBtn.clicked.connect(self.annotate)

        # create button for playing
        self.playBtn = QPushButton()
        self.playBtn.setEnabled(False)
        self.playBtn.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
        self.playBtn.clicked.connect(self.play_video)

        self.playbackspeedBtn = QComboBox()  # QPushButton('2X')
        self.playbackspeedBtn.addItems(["1X", "1.5X", "2X", "3X"])
        self.playbackspeedBtn.currentIndexChanged.connect(self.set_speed)

        # create slider
        # self.slider = QSlider(Qt.Horizontal)
        # #### Custom Slider
        self.slider = Slider()
        self.slider.setup_preview(self)
        # ############################
        # self.slider.setRange(0, 0)
        # self.slider.setSingleStep(5000)
        self.slider.setMaximum(100000)
        self.slider.sliderMoved.connect(self.position_changed)
        # self.slider.valueChanged.connect(self.set_position)
        self.slider.sliderPressed.connect(self.position_changed)

        # create LCD for displaying the position of the slider
        # self.lcd = QLCDNumber(self)
        self.l = QLabel("0:00:00")
        self.l.setStyleSheet("color: white")
        self.slider.valueChanged.connect(self.display_time)  # (self.lcd.display)
        self.d = QLabel("0:00:00")
        self.d.setStyleSheet("color: white")

        # create label
        self.label = QLabel()
        self.label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)

        # create hbox layout
        hboxLayout = QHBoxLayout()
        hboxLayout.setContentsMargins(0, 0, 0, 0)
        # set widgets to the hbox layout
        # hboxLayout.addWidget(openBtn)
        hboxLayout.addWidget(self.playBtn)
        hboxLayout.addWidget(self.playbackspeedBtn)
        hboxLayout.addWidget(self.l)
        hboxLayout.addWidget(self.slider)
        hboxLayout.addWidget(self.d)
        hboxLayout.addWidget(self.playBtn)

        bottomLayout = QHBoxLayout()
        bottomLayout.addWidget(openBtn)
        bottomLayout.addWidget(snapBtn)
        bottomLayout.addWidget(labelmeBtn)


        # menuLayout = self.createMenuBar()
        menuBar = self.createMenuBar()
        
        
        # create vbox layout
        vboxLayout = QVBoxLayout()
        # vboxLayout.setMenuBar(menuBar) 
        # set widgets to the vbox layout
        # vboxLayout.addWidget(openBtn)
        # vboxLayout.addLayout(menuLayout)
        vboxLayout.addWidget(menuBar)
        vboxLayout.addWidget(self.videowidget)
        vboxLayout.addLayout(hboxLayout)
        vboxLayout.addLayout(bottomLayout)
        vboxLayout.addWidget(self.label)

        self.mainLayout = QHBoxLayout()
        # self.mainLayout.addLayout(menuLayout)
        self.mainLayout.addLayout(vboxLayout)

        # create empty lists for the panels to be added
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

        # create menu bar
        # menuBar = QMenuBar(self)
        
        self.setup_video_click()
        # self.setFocusPolicy(Qt.StrongFocus)
        # self.setFocus()
        # self.installEventFilter(self)

        
        self.add_time_panel_from_file_predefined("samples/phase.txt")
        self.add_time_panel_from_file_predefined("samples/task.txt")
        # self.add_rating_panel_from_file_predefined("path/to/rating_panel1.txt")
        # self.add_rating_panel_from_file_predefined("path/to/rating_panel2.txt")
                

        
    def setup_video_click(self):
        """Setup video widget to respond to mouse clicks"""
        self.videowidget.mousePressEvent = self.video_clicked

    def video_clicked(self, event):
        """Handle video widget mouse clicks"""
        if event.button() == Qt.LeftButton:
            self.play_video()
    def eventFilter(self, obj, event):
        # 1) catch Space-down
        if event.type() == QEvent.KeyPress and event.key() == Qt.Key_Space:
            self.play_video()    # toggle play/pause
            return True          # STOP propagation to focused widget

        # 2) otherwise default
        return super().eventFilter(obj, event)


    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Space:
            self.play_video()
            event.accept()  # Prevent further propagation
            return
        elif event.key() == Qt.Key_Right:
            p = self.slider.value()
            p = p + int(500000000 / self.media.get_duration())
            self.set_position(p)

        elif event.key() == Qt.Key_Left:

            p = self.slider.value()
            p = p - int(500000000 / self.media.get_duration())
            self.set_position(p)

        elif event.key() == Qt.Key_F5:

            self.close()
        else:

            super().keyPressEvent(event)

    def open_video(self):
        # opens video file, create the directory for the videos outputs, play the video
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Open Video",
            os.path.expanduser("~"),
            "Video Files (*.mp4 *.avi *.mov *.mpg)",
        )

        if filename != "":
            # self.mediaPlayer.setMedia(QMediaContent(QUrl.fromLocalFile(filename)))
            self.vid_path = filename
            self.media = self.instance.media_new(filename)
            self.mediaPlayer.set_media(self.media)
            self.media.parse()
            self.setWindowTitle(self.media.get_meta(0))

            self.playBtn.setEnabled(True)

            if platform.system() == "Linux":  # for Linux using the X Server
                self.mediaPlayer.set_xwindow(int(self.videowidget.winId()))
            elif platform.system() == "Windows":  # for Windows
                self.mediaPlayer.set_hwnd(int(self.videowidget.winId()))
            else:  # if platform.system() == "Darwin":  # for MacOS
                self.mediaPlayer.set_nsobject(int(self.videowidget.winId()))

            self.cap = cv2.VideoCapture(filename)
            self.play_video()

            self.d.setText(str(self.getDurationValue()))

            if not self.parrentDirectory:
                self.parrentDirectory = "./outputs"
                if not os.path.exists(self.parrentDirectory):
                    os.mkdir(self.parrentDirectory)

            self.vidname = os.path.basename(filename)
            print("Saving directory: ", self.parrentDirectory + "/" + self.vidname)
            if not os.path.exists(self.parrentDirectory + "/" + self.vidname):
                os.mkdir(self.parrentDirectory + "/" + self.vidname)
            self.save_directory = self.parrentDirectory + "/" + self.vidname

            if not os.path.exists(
                self.parrentDirectory + "/" + self.vidname + "/images"
            ):
                os.mkdir(self.parrentDirectory + "/" + self.vidname + "/images")
            self.image_save_directory = (
                self.parrentDirectory + "/" + self.vidname + "/images"
            )

            # clear panels
            if self.num_panels > 0:
                self.clearPanels()
                for panel_index in range(1, self.num_panels + 1):
                    if self.groupButtonlist[panel_index]:
                        if not os.path.exists(
                            self.save_directory
                            + "/"
                            + self.form_title[panel_index].text()
                            + "_scores.txt"
                        ):
                            with open(
                                "{}/{}_scores.txt".format(
                                    self.save_directory,
                                    self.form_title[panel_index].text(),
                                ),
                                "a",
                            ) as out:
                                for i in range(len(self.groupButtonlist[panel_index])):
                                    out.write(
                                        "{} \n".format(
                                            self.tasklist[self.panel_index][i].text()
                                        )
                                    )
                        else:
                            with open(
                                "{}/{}_scores.txt".format(
                                    self.save_directory,
                                    self.form_title[panel_index].text(),
                                ),
                                "r",
                            ) as f:
                                lines = f.readlines()
                                for line in lines:
                                    rating_item = line.split(" : ")[0]

                                    if len(line.split(" : ")) == 2:
                                        score = line.split(" : ")[1]

                                        for i in range(
                                            len(self.groupButtonlist[panel_index])
                                        ):
                                            if (
                                                self.tasklist[panel_index][i].text()
                                                == rating_item
                                            ):
                                                for j in range(
                                                    len(
                                                        self.ratingButtonslist[
                                                            panel_index
                                                        ][i]
                                                    )
                                                ):
                                                    print(
                                                        self.ratingButtonslist[
                                                            panel_index
                                                        ][i][j].text(),
                                                        score,
                                                    )
                                                    if int(
                                                        self.ratingButtonslist[
                                                            panel_index
                                                        ][i][j].text()
                                                    ) == int(score):
                                                        self.ratingButtonslist[
                                                            panel_index
                                                        ][i][j].setChecked(True)

                                                # if score == 'Yes\n':
                                                #     self.yesButtonlist[panel_index][i].setChecked(True)
                                                # elif score == 'No\n':
                                                #     self.noButtonlist[panel_index][i].setChecked(True)
                                    # load existing annotations

    def play_video(self):
        if self.mediaPlayer.is_playing():
            self.mediaPlayer.pause()
            self.is_paused = True
            ##self.mediaPlayer_g.pause()
            self.playBtn.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
            self.timer.stop()

        else:
            self.mediaPlayer.play()
            ##self.mediaPlayer_g.play()
            self.timer.start()
            self.is_paused = False
            self.playBtn.setIcon(self.style().standardIcon(QStyle.SP_MediaPause))

    def changeDirectory(self):
        self.parrentDirectory = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Select Folder"
        )

        if self.vidname:
            if not os.path.exists(self.parrentDirectory + "/" + self.vidname):
                os.mkdir(self.parrentDirectory + "/" + self.vidname)
            self.save_directory = self.parrentDirectory + "/" + self.vidname

            if not os.path.exists(
                self.parrentDirectory + "/" + self.vidname + "/images"
            ):
                os.mkdir(self.parrentDirectory + "/" + self.vidname + "/images")
            self.image_save_directory = (
                self.parrentDirectory + "/" + self.vidname + "/images"
            )

            print("Saving directory: ", self.parrentDirectory + "/" + self.vidname)

    def display_time(self):

        time = self.getSliderValue()
        self.l.setText("{}".format(str(time)))

    def add_panel(self):
        # for manually added panels
        pass

    def onpanelRemoveBtnClicked(self, panel_index):
        pass
        # self.mainLayout.removeWidget(self.scroll[panel_index]) deleteLater()

    def add_time_panel_from_file_predefined(self, filepath):
        if os.path.exists(filepath):
            self.load_panel_from_file(filepath, self.add_time_panel_from_file)

    def add_rating_panel_from_file_predefined(self, filepath):
        if os.path.exists(filepath):
            self.load_panel_from_file(filepath, self.add_rating_panel_from_file)

    def load_panel_from_file(self, filepath, add_func):
        # temporarily override QFileDialog for programmatic loading
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
            self.form_title[self.panel_index].setFont(
                QFont("Times", 12, weight=QFont.Bold)
            )
            self.panelRemoveBtn[self.panel_index] = QPushButton("Exit")
            self.panelRemoveBtn[self.panel_index].clicked.connect(
                partial(self.onpanelRemoveBtnClicked, self.panel_index)
            )

            self.formLayout[self.panel_index].addRow(
                self.form_title[self.panel_index]
            )  # , self.panelRemoveBtn[self.panel_index])

            # panel_width = 200
            for i, line in enumerate(lines):
                line = line.split("#")

                self.tasklist[self.panel_index].append(QLabel(line[0]))
                self.tasklist[self.panel_index][i].setStyleSheet(
                    "background-color: black ; color: white"
                )
                self.tasklist[self.panel_index][i].setFont(
                    QFont("Times", 10, weight=QFont.Bold)
                )
                self.tasklist[self.panel_index][i].setWordWrap(True)
                # self.tasklist[self.panel_index][i].setFixedWidth(panel_width)
                self.startingButtonlist[self.panel_index].append(QPushButton("starts"))
                self.startingButtonlist[self.panel_index][i].setFixedWidth(50)
                self.startingTimelist[self.panel_index].append(QLabel("0"))
                self.startingTimelist[self.panel_index][i].setStyleSheet("color: white")
                self.startingButtonlist[self.panel_index][i].clicked.connect(
                    partial(self.onstartbuttonClicked, self.panel_index, i)
                )
                self.endingButtonlist[self.panel_index].append(QPushButton("ends"))
                self.endingButtonlist[self.panel_index][i].setFixedWidth(50)
                self.endingTimelist[self.panel_index].append(QLabel("0"))
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

                self.formLayout[self.panel_index].addRow(
                    self.tasklist[self.panel_index][i]
                )
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
            # —————— Add “Save All” button for this time panel ——————
            saveAllBtn = QPushButton("Save All")
            # saveAllBtn.setFixedWidth(100) 
            # when clicked, call our helper save_panel(panel_index)
            saveAllBtn.clicked.connect(lambda _, idx=self.panel_index: self.save_panel(idx))
            self.formLayout[self.panel_index].addRow(saveAllBtn)

            self.groupbox[self.panel_index].setLayout(self.formLayout[self.panel_index])

            self.scroll[self.panel_index] = QScrollArea()
            self.scroll[self.panel_index].setWidget(self.groupbox[self.panel_index])
            self.scroll[self.panel_index].setWidgetResizable(True)
            self.scroll[self.panel_index].setFixedWidth(150)
            self.scroll[self.panel_index].setFocusPolicy(Qt.StrongFocus)
            
            # Calculate content-based width
            # content_width = self.groupbox[self.panel_index].sizeHint().width()
            # scrollbar_width = self.scroll[self.panel_index].verticalScrollBar().sizeHint().width()
            # self.scroll[self.panel_index].setMinimumWidth(200 )

            self.mainLayout.addWidget(self.scroll[self.panel_index])

    def add_rating_panel_from_file(self):
        filename, _ = QFileDialog.getOpenFileName(
            self, "Open Text", filter="Text files (*.txt)"
        )

        if filename != "" and str(filename).endswith(".txt"):
            title = str(os.path.basename(filename)).split(".")[0]

            with open(filename) as f:
                lines = f.read().splitlines()
                # with open('{}/{}_scores.txt'.format(self.save_directory, title), 'w') as out:
                #     for line in lines:
                #         out.write(line + '\n')
            print("Opened rating panel:", title)

            self.num_panels += 1

            self.panel_index = self.num_panels

            self.tasklist[self.panel_index] = []

            self.yesButtonlist[self.panel_index] = []
            self.noButtonlist[self.panel_index] = []
            self.ratingButtonslist[self.panel_index] = []
            self.groupButtonlist[self.panel_index] = []

            self.yes_label = QLabel("Yes")
            self.yes_label.setStyleSheet("color: white")
            # self.yes_label.setAlignment(Qt.AlignRight)
            self.no_label = QLabel("No")
            self.no_label.setStyleSheet("color: white")
            # self.no_label.setAlignment(Qt.AlignRight)

            self.groupbox[self.panel_index] = QGroupBox()
            self.formLayout[self.panel_index] = QFormLayout()
            # self.formLayout[self.panel_index].setContentsMargins(0,0,0,0)
            self.formLayout[self.panel_index].setVerticalSpacing(10)
            self.form_title[self.panel_index] = QLabel(title)
            self.form_title[self.panel_index].setStyleSheet("color: white")
            self.form_title[self.panel_index].setAlignment(Qt.AlignCenter)
            self.form_title[self.panel_index].setFont(
                QFont("Times", 12, weight=QFont.Bold)
            )
            self.panelRemoveBtn[self.panel_index] = QPushButton("Exit")
            self.panelRemoveBtn[self.panel_index].clicked.connect(
                partial(self.onpanelRemoveBtnClicked, self.panel_index)
            )

            # firstline_empty = QLabel().setFixedWidth(100)
            # hbLayout1 = QHBoxLayout()
            # hbLayout1.addWidget(self.yes_label)
            # hbLayout1.addWidget(self.no_label)
            # hbLayout1.setContentsMargins(0, 0, 0, 0)
            #
            # container1 = QWidget()
            # container1.setLayout(hbLayout1)

            self.formLayout[self.panel_index].addRow(
                self.form_title[self.panel_index]
            )  # , self.panelRemoveBtn[self.panel_index])
            # self.formLayout[self.panel_index].addRow(firstline_empty, container1)
            for i, line in enumerate(lines):
                line = line.split("#")

                num_scores = 2
                if len(line) > 1:
                    try:
                        num_scores = int(line[1])
                    except:
                        num_scores = 2

                self.tasklist[self.panel_index].append(QLabel(line[0]))
                self.tasklist[self.panel_index][i].setStyleSheet(
                    "background-color: black ; color: white"
                )
                self.tasklist[self.panel_index][i].setFont(
                    QFont("Times", 10, weight=QFont.Bold)
                )
                self.tasklist[self.panel_index][i].setWordWrap(True)
                self.tasklist[self.panel_index][i].setFixedWidth(100)

                self.ratingButtonslist[self.panel_index].append([])

                for j in range(num_scores):
                    self.ratingButtonslist[self.panel_index][i].append(
                        QRadioButton(str(j))
                    )
                    self.ratingButtonslist[self.panel_index][i][j].setStyleSheet(
                        "background-color: black ; color: white"
                    )

                # self.yesButtonlist[self.panel_index].append(QRadioButton())
                # self.yesButtonlist[self.panel_index][i].clicked.connect()
                # self.noButtonlist[self.panel_index].append(QRadioButton())

                self.groupButtonlist[self.panel_index].append(QButtonGroup())
                for j in range(num_scores):
                    self.groupButtonlist[self.panel_index][i].addButton(
                        self.ratingButtonslist[self.panel_index][i][j]
                    )
                # self.groupButtonlist[self.panel_index][i].addButton(self.yesButtonlist[self.panel_index][i])
                # self.groupButtonlist[self.panel_index][i].addButton(self.noButtonlist[self.panel_index][i])
                self.groupButtonlist[self.panel_index][i].buttonClicked.connect(
                    partial(self.save_rating_entry, self.panel_index, i)
                )

                hbLayout = QHBoxLayout()
                for j in range(num_scores):
                    hbLayout.addWidget(self.ratingButtonslist[self.panel_index][i][j])
                # hbLayout.addWidget(self.yesButtonlist[self.panel_index][i])
                # hbLayout.addWidget(self.noButtonlist[self.panel_index][i])
                hbLayout.setContentsMargins(0, 0, 0, 0)
                container = QWidget()
                container.setLayout(hbLayout)
                self.formLayout[self.panel_index].addRow(
                    self.tasklist[self.panel_index][i], container
                )
                # self.formLayout[self.panel_index].addRow(self.startingButtonlist[self.panel_index][i],
                #                                          self.startingTimelist[self.panel_index][i])
                # self.formLayout[self.panel_index].addRow(self.endingButtonlist[self.panel_index][i],
                #                                          self.endingTimelist[self.panel_index][i])
                # self.formLayout[self.panel_index].addRow(self.saveEntryBtn[self.panel_index][i],
                #                                          self.clearEntryBtn[self.panel_index][i])

            # —————— Add “Save All Ratings” button for this rating panel ——————
            saveAllRatingsBtn = QPushButton("Save All Ratings")
            saveAllRatingsBtn.clicked.connect(
                lambda _, idx=self.panel_index: self.save_all_ratings(idx)
            )
            self.formLayout[self.panel_index].addRow(saveAllRatingsBtn)

            self.groupbox[self.panel_index].setLayout(self.formLayout[self.panel_index])
            
            
            self.scroll[self.panel_index] = QScrollArea()
            self.scroll[self.panel_index].setWidget(self.groupbox[self.panel_index])
            self.scroll[self.panel_index].setWidgetResizable(True)
            self.scroll[self.panel_index].setFixedWidth(300)
            self.scroll[self.panel_index].setFocusPolicy(Qt.StrongFocus)
            self.mainLayout.addWidget(self.scroll[self.panel_index])

            if self.save_directory:
                if os.path.exists(
                    self.save_directory
                    + "/"
                    + self.form_title[self.panel_index].text()
                    + "_scores.txt"
                ):
                    # load previous ratings
                    with open(
                        "{}/{}_scores.txt".format(
                            self.save_directory,
                            self.form_title[self.panel_index].text(),
                        ),
                        "r",
                    ) as f:
                        lines = f.readlines()
                        for line in lines:
                            rating_item = line.split(" : ")[0]

                            if len(line.split(" : ")) == 2:
                                score = line.split(" : ")[1]

                                for i in range(
                                    len(self.groupButtonlist[self.panel_index])
                                ):
                                    if (
                                        self.tasklist[self.panel_index][i].text()
                                        == rating_item
                                    ):
                                        for j in range(
                                            len(
                                                self.ratingButtonslist[
                                                    self.panel_index
                                                ][i]
                                            )
                                        ):
                                            if int(
                                                self.ratingButtonslist[
                                                    self.panel_index
                                                ][i][j].text()
                                            ) == int(score):
                                                self.ratingButtonslist[
                                                    self.panel_index
                                                ][i][j].setChecked(True)
                else:
                    if self.save_directory:
                        with open(
                            "{}/{}_scores.txt".format(
                                self.save_directory,
                                self.form_title[self.panel_index].text(),
                            ),
                            "a",
                        ) as out:
                            for i in range(len(self.groupButtonlist[self.panel_index])):
                                out.write(
                                    "{} \n".format(
                                        self.tasklist[self.panel_index][i].text()
                                    )
                                )

    def position_changed(self):
        self.timer.stop()
        pos = self.slider.value()

        self.mediaPlayer.set_position(pos / 100000)
        self.timer.start()
        # self.slider.setValue(pos)

    def get_position(self):
        p = self.mediaPlayer.position()

    def duration_changed(self, duration):
        self.slider.setRange(0, duration)

    def set_position(self, position):

        # self.slider.setValue(position)
        self.timer.stop()
        pos = self.slider.value()

        self.mediaPlayer.set_position(
            position / 100000
        )  # / (self.media.get_duration()))
        self.timer.start()

    def handle_errors(self):
        # TODO : create error handlers
        self.playBtn.setEnabled(False)
        self.label.setText("Error: " + self.mediaPlayer.errorString())

    def getSliderValue(self):

        value = int(self.mediaPlayer.get_position() * (self.media.get_duration()))
        value = value // 1000
        min, sec = divmod(value, 60)
        hour, min = divmod(min, 60)

        return "%d:%02d:%02d" % (hour, min, sec)

    def getDurationValue(self):

        value = int(self.media.get_duration())
        value = value // 1000
        min, sec = divmod(value, 60)
        hour, min = divmod(min, 60)

        return "%d:%02d:%02d" % (hour, min, sec)

    def onstartbuttonClicked(self, panel_index, i):
        value = self.getSliderValue()

        self.startingTimelist[panel_index][i].setText(str(value))
        self.startingTimelist[panel_index][i].setStyleSheet("color: white")
        self.saveEntryBtn[panel_index][i].setEnabled(False)
        self.clearEntryBtn[panel_index][i].setEnabled(True)

    def onendbuttonClicked(self, panel_index, i):
        value = self.getSliderValue()

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
        with open("{}/{}.txt".format(self.save_directory, form_title), "a") as f:
            f.write("{} : ({},{})\n".format(task_name, starting_time, ending_time))

        # self.startingTimelist[panel_index][i].setText('0')
        # self.endingTimelist[panel_index][i].setText('0')
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
        if self.mediaPlayer.is_playing():
            # self.set_speed(0)
            self.mediaPlayer.pause()
            self.is_paused = True
            ##self.mediaPlayer_g.pause()
            self.playBtn.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
            self.timer.stop()

        if self.vidname:
            frame_num = int(
                self.mediaPlayer.get_position() * (self.media.get_duration())
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

    def buffer_frame(self, image):
        self.ImagesBuffer = image

    def update_ui(self):

        media_pos = int(self.mediaPlayer.get_position() * 100000)
        self.slider.setValue(media_pos)
        # No need to call this function if nothing is played
        if not self.mediaPlayer.is_playing():
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