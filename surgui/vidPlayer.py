#### Without VLC

import sys
import os
import platform
import cv2
import subprocess
import json
import time
from functools import partial

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
    QGroupBox,
    QScrollArea,
    QMenuBar,
    QComboBox,
    QFormLayout,
    QRadioButton,
    QButtonGroup,
)
from PyQt5.QtMultimedia import QMediaContent, QMediaPlayer
from PyQt5.QtMultimediaWidgets import QVideoWidget
from PyQt5.QtGui import QIcon, QPalette, QFont
from PyQt5.QtCore import Qt, QUrl, QTimer

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



class VideoPlayerWindow(QWidget):
    """A custom video player widget with annotation panels."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Surgical Video Player")
        self.setWindowIcon(QIcon("player.png"))  # Make sure you have a 'player.png' icon file
        self.setGeometry(100, 100, 1000, 600)

        # Set dark theme
        p = self.palette()
        p.setColor(QPalette.Window, Qt.black)
        self.setPalette(p)
        self.setFocusPolicy(Qt.StrongFocus)

        self.num_panels = 0
        self.mediaPlayer = None
        self.cap = None
        self.parrentDirectory = os.path.join(os.path.expanduser("~"), "outputs")
        self.save_directory = None
        self.vidname = None
        self.image_save_directory = None
        self.last_snapshot_path = None

        # self.timer = QTimer(self)
        # self.timer.setInterval(100)
        # self.timer.timeout.connect(self.update_ui)
        
        # Initialize lists for dynamic widgets
        self._init_widget_lists()
        # Setup the user interface
        self.init_ui()
        self.show()

    def _init_widget_lists(self):
        """Initializes lists to hold references to dynamically created widgets."""
        max_panels = 10
        self.groupbox = [None] * max_panels
        self.formLayout = [None] * max_panels
        self.form_title = [None] * max_panels
        self.scroll = [None] * max_panels
        self.tasklist = [None] * max_panels
        self.startingButtonlist = [None] * max_panels
        self.startingTimelist = [None] * max_panels
        self.endingButtonlist = [None] * max_panels
        self.endingTimelist = [None] * max_panels
        self.saveEntryBtn = [None] * max_panels
        self.clearEntryBtn = [None] * max_panels
        self.ratingButtonslist = [None] * max_panels
        self.groupButtonlist = [None] * max_panels

    def init_ui(self):
        """Initializes the UI components."""
        self._create_media_player()
        self._create_widgets()
        self._create_layouts()
        self._create_menu_bar()

    def _create_media_player(self):
        """Sets up the QMediaPlayer."""
        self.mediaPlayer = QMediaPlayer(self, QMediaPlayer.VideoSurface)
        self.videoWidget = QVideoWidget()
        self.mediaPlayer.setVideoOutput(self.videoWidget)

        # Connect signals
        self.mediaPlayer.stateChanged.connect(self._update_play_button_icon)
        self.mediaPlayer.positionChanged.connect(self._update_slider_position)
        self.mediaPlayer.durationChanged.connect(self._update_slider_range)

    def _create_widgets(self):
        """Creates all the static widgets for the player."""
        self.openBtn = QPushButton("Open Video")
        self.openBtn.clicked.connect(self.open_video)

        self.snapBtn = QPushButton("Snapshot (Save Frame)")
        self.snapBtn.clicked.connect(self.take_snapshot)

        self.labelmeBtn = QPushButton("Annotate (labelme)")
        self.labelmeBtn.clicked.connect(self.annotate_image)
        self.labelmeBtn.setEnabled(False)

        self.playBtn = QPushButton()
        self.playBtn.setEnabled(False)
        self.playBtn.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
        self.playBtn.clicked.connect(self.play_video)

        self.playbackSpeedBtn = QComboBox()
        self.playbackSpeedBtn.addItems(["1X", "1.5X", "2X", "3X"])
        self.playbackSpeedBtn.currentIndexChanged.connect(self.set_speed)

        # self.slider = QSlider(Qt.Horizontal)
        # self.slider.setRange(0, 0)
        # self.slider.sliderMoved.connect(self.set_position)
        # Create slider
        self.slider = Slider()
        self.slider.setup_preview(self)
        self.slider.setMaximum(100000)
        self.slider.sliderMoved.connect(self.position_changed)
        self.slider.sliderPressed.connect(self.position_changed)
        
        
        self.currentTimeLabel = QLabel("00:00:00")
        self.currentTimeLabel.setStyleSheet("color: white;")
        self.totalDurationLabel = QLabel("00:00:00")
        self.totalDurationLabel.setStyleSheet("color: white;")

        self.errorLabel = QLabel()
        self.errorLabel.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)

    def _create_layouts(self):
        """Creates and arranges the layouts."""
        controlLayout = QHBoxLayout()
        controlLayout.setContentsMargins(0, 0, 0, 0)
        controlLayout.addWidget(self.playBtn)
        controlLayout.addWidget(self.playbackSpeedBtn)
        controlLayout.addWidget(self.currentTimeLabel)
        controlLayout.addWidget(self.slider)
        controlLayout.addWidget(self.totalDurationLabel)

        bottomLayout = QHBoxLayout()
        bottomLayout.addWidget(self.openBtn)
        bottomLayout.addWidget(self.snapBtn)
        bottomLayout.addWidget(self.labelmeBtn)

        videoLayout = QVBoxLayout()
        videoLayout.addWidget(self.videoWidget)
        videoLayout.addLayout(controlLayout)
        videoLayout.addLayout(bottomLayout)
        videoLayout.addWidget(self.errorLabel)

        self.mainLayout = QHBoxLayout(self)
        self.mainLayout.addLayout(videoLayout)

    def _create_menu_bar(self):
        """Creates the main menu bar."""
        menuBar = QMenuBar(self)
        fileMenu = menuBar.addMenu("&File")

        actions = {
            "Open Video": ("Ctrl+O", self.open_video),
            "Add Timestamping Panel": (None, self.add_time_panel_from_file),
            "Add Rating Panel": (None, self.add_rating_panel_from_file),
            "Change Save Directory": (None, self.change_directory),
            "Save All": ("Ctrl+S", self.save_all),
            "Clear All Panels": ("Ctrl+C", self.clear_panels),
            "Exit": ("Ctrl+Q", self.close),
        }

        for text, (shortcut, slot) in actions.items():
            action = QAction(f"&{text}", self)
            if shortcut:
                action.setShortcut(shortcut)
            action.triggered.connect(slot)
            fileMenu.addAction(action)

        self.mainLayout.setMenuBar(menuBar)

    def open_video(self):
        """Opens a video file and prepares for playback."""
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Open Video",
            os.path.expanduser("~"),
            "Video Files (*.mp4 *.avi *.mov *.mpg)",
        )

        if filename:
            self.mediaPlayer.setMedia(QMediaContent(QUrl.fromLocalFile(filename)))
            self.playBtn.setEnabled(True)
            self.vidname = os.path.basename(filename)
            self.setWindowTitle(f"Surgical Video Player - {self.vidname}")

            # Release previous capture if any
            if self.cap:
                self.cap.release()
            self.cap = cv2.VideoCapture(filename)

            self._setup_save_directories()
            self.clear_panels()
            self.play_video()

    def _setup_save_directories(self):
        """Creates directories for saving outputs if they don't exist."""
        if not os.path.exists(self.parrentDirectory):
            os.makedirs(self.parrentDirectory)

        self.save_directory = os.path.join(self.parrentDirectory, self.vidname)
        if not os.path.exists(self.save_directory):
            os.makedirs(self.save_directory)

        self.image_save_directory = os.path.join(self.save_directory, "images")
        if not os.path.exists(self.image_save_directory):
            os.makedirs(self.image_save_directory)
        
        print(f"Output will be saved to: {self.save_directory}")


    def play_video(self):
        """Toggles between play and pause states."""
        if self.mediaPlayer.state() == QMediaPlayer.PlayingState:
            self.mediaPlayer.pause()
        else:
            self.mediaPlayer.play()

    def _update_play_button_icon(self, state):
        """Updates the play/pause button icon based on the player state."""
        if state == QMediaPlayer.PlayingState:
            self.playBtn.setIcon(self.style().standardIcon(QStyle.SP_MediaPause))
        else:
            self.playBtn.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))

    def _update_slider_position(self, position):
        """Updates the slider's value as the video plays."""
        self.slider.setValue(position)
        self.currentTimeLabel.setText(self._format_time(position))

    def _update_slider_range(self, duration):
        """Sets the slider's maximum value based on video duration."""
        self.slider.setRange(0, duration)
        self.totalDurationLabel.setText(self._format_time(duration))

    def set_position(self, position):
        """Sets the media player's position."""
        self.mediaPlayer.setPosition(position)

    def set_speed(self, index):
        """Sets the playback speed."""
        speed_text = self.playbackSpeedBtn.itemText(index).replace("X", "")
        rate = float(speed_text)
        self.mediaPlayer.setPlaybackRate(rate)
    def position_changed(self):
        pos = self.slider.value()
        duration = self.mediaPlayer.duration()
        if duration > 0:
            self.mediaPlayer.setPosition(int(pos * duration / 1000))

    def take_snapshot(self):
        """Takes a snapshot of the current frame and saves it as an image."""
        if not self.cap or not self.vidname:
            self.errorLabel.setText("Please open a video first.")
            return

        current_time_ms = self.mediaPlayer.position()
        self.cap.set(cv2.CAP_PROP_POS_MSEC, current_time_ms)
        ret, frame = self.cap.read()

        if ret:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            snapshot_name = f"snapshot_{timestamp}.jpg"
            self.last_snapshot_path = os.path.join(self.image_save_directory, snapshot_name)
            cv2.imwrite(self.last_snapshot_path, frame)
            self.errorLabel.setText(f"Snapshot saved to {self.last_snapshot_path}")
            self.labelmeBtn.setEnabled(True)
        else:
            self.errorLabel.setText("Could not grab frame for snapshot.")
            self.labelmeBtn.setEnabled(False)


    def annotate_image(self):
        """Opens the last saved snapshot in the labelme annotation tool."""
        if not self.last_snapshot_path:
            self.errorLabel.setText("No snapshot taken yet to annotate.")
            return
        try:
            # Check if labelme is available in the system path
            subprocess.Popen(["labelme", self.last_snapshot_path])
        except FileNotFoundError:
            self.errorLabel.setText("Error: 'labelme' is not installed or not in your system's PATH.")
        except Exception as e:
            self.errorLabel.setText(f"Failed to open labelme: {e}")


    def add_time_panel_from_file(self):
        """Adds a timestamping panel from a text file."""
        if not self.vidname:
            self.errorLabel.setText("Please open a video before adding a panel.")
            return

        filename, _ = QFileDialog.getOpenFileName(self, "Open Timestamp File", "", "Text files (*.txt)")
        if not filename:
            return

        with open(filename, 'r') as f:
            lines = f.read().splitlines()
        
        title = os.path.splitext(os.path.basename(filename))[0]
        self._create_panel("time", title, lines)


    def add_rating_panel_from_file(self):
        """Adds a rating panel from a text file."""
        if not self.vidname:
            self.errorLabel.setText("Please open a video before adding a panel.")
            return

        filename, _ = QFileDialog.getOpenFileName(self, "Open Rating File", "", "Text files (*.txt)")
        if not filename:
            return

        with open(filename, 'r') as f:
            lines = f.read().splitlines()

        title = os.path.splitext(os.path.basename(filename))[0]
        self._create_panel("rating", title, lines)
        self._load_existing_ratings(self.num_panels, title)


    def _create_panel(self, panel_type, title, lines):
        """Generic factory for creating annotation panels."""
        self.num_panels += 1
        panel_index = self.num_panels

        self.groupbox[panel_index] = QGroupBox()
        self.formLayout[panel_index] = QFormLayout()
        
        self.form_title[panel_index] = QLabel(title)
        self.form_title[panel_index].setStyleSheet("color: white; font-weight: bold; font-size: 12pt;")
        self.form_title[panel_index].setAlignment(Qt.AlignCenter)
        self.formLayout[panel_index].addRow(self.form_title[panel_index])

        if panel_type == "time":
            self._populate_time_panel(panel_index, lines)
        elif panel_type == "rating":
            self._populate_rating_panel(panel_index, lines)

        self.groupbox[panel_index].setLayout(self.formLayout[panel_index])
        self.scroll[panel_index] = QScrollArea()
        self.scroll[panel_index].setWidget(self.groupbox[panel_index])
        self.scroll[panel_index].setWidgetResizable(True)
        self.scroll[panel_index].setFixedWidth(350)
        self.mainLayout.addWidget(self.scroll[panel_index])

    def _populate_time_panel(self, panel_index, lines):
        """Populates a panel with timestamping widgets."""
        self.tasklist[panel_index] = []
        self.startingButtonlist[panel_index] = []
        self.startingTimelist[panel_index] = []
        self.endingButtonlist[panel_index] = []
        self.endingTimelist[panel_index] = []

        for i, line_text in enumerate(lines):
            task_label = QLabel(line_text.split('#')[0])
            task_label.setStyleSheet("color: white;")
            task_label.setWordWrap(True)
            self.tasklist[panel_index].append(task_label)

            start_btn = QPushButton("Start")
            start_btn.clicked.connect(partial(self._set_timestamp, self.startingTimelist[panel_index][i]))
            self.startingButtonlist[panel_index].append(start_btn)

            start_time = QLabel("00:00:00")
            start_time.setStyleSheet("color: #4CAF50;") # Green
            self.startingTimelist[panel_index].append(start_time)
            
            end_btn = QPushButton("End")
            end_btn.clicked.connect(partial(self._set_timestamp, self.endingTimelist[panel_index][i]))
            self.endingButtonlist[panel_index].append(end_btn)

            end_time = QLabel("00:00:00")
            end_time.setStyleSheet("color: #F44336;") # Red
            self.endingTimelist[panel_index].append(end_time)

            h_layout1 = QHBoxLayout()
            h_layout1.addWidget(start_btn)
            h_layout1.addWidget(start_time)
            
            h_layout2 = QHBoxLayout()
            h_layout2.addWidget(end_btn)
            h_layout2.addWidget(end_time)

            self.formLayout[panel_index].addRow(task_label)
            self.formLayout[panel_index].addRow(h_layout1)
            self.formLayout[panel_index].addRow(h_layout2)


    def _populate_rating_panel(self, panel_index, lines):
        """Populates a panel with rating widgets."""
        self.tasklist[panel_index] = []
        self.ratingButtonslist[panel_index] = []
        self.groupButtonlist[panel_index] = []

        for i, line_text in enumerate(lines):
            parts = line_text.split('#')
            task_text = parts[0]
            num_scores = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 5

            task_label = QLabel(task_text)
            task_label.setStyleSheet("color: white;")
            task_label.setWordWrap(True)
            self.tasklist[panel_index].append(task_label)
            
            button_group = QButtonGroup(self)
            self.groupButtonlist[panel_index].append(button_group)
            
            h_layout = QHBoxLayout()
            radio_buttons = []
            for j in range(1, num_scores + 1):
                radio_btn = QRadioButton(str(j))
                radio_btn.setStyleSheet("color: white;")
                h_layout.addWidget(radio_btn)
                button_group.addButton(radio_btn, j)
                radio_buttons.append(radio_btn)

            self.ratingButtonslist[panel_index].append(radio_buttons)
            button_group.buttonClicked.connect(partial(self.save_all))
            
            self.formLayout[panel_index].addRow(task_label, h_layout)
    
    def _set_timestamp(self, label_to_update):
        """Sets the current video time on a label."""
        current_time_ms = self.mediaPlayer.position()
        label_to_update.setText(self._format_time(current_time_ms))
        self.save_all() # Auto-save on change

    def _load_existing_ratings(self, panel_index, title):
        """Loads previously saved ratings from a file."""
        save_file = os.path.join(self.save_directory, f"{title}.json")
        if not os.path.exists(save_file):
            return

        with open(save_file, 'r') as f:
            try:
                ratings_data = json.load(f)
                for i, task_label in enumerate(self.tasklist[panel_index]):
                    task_text = task_label.text()
                    if task_text in ratings_data:
                        score = ratings_data[task_text]
                        button_group = self.groupButtonlist[panel_index][i]
                        for button in button_group.buttons():
                            if button.text() == str(score):
                                button.setChecked(True)
                                break
            except json.JSONDecodeError:
                print(f"Warning: Could not parse ratings file: {save_file}")


    def save_all(self):
        """Saves all annotations from all active panels to files."""
        if not self.save_directory:
            self.errorLabel.setText("Cannot save. No video opened or save directory not set.")
            return

        for i in range(1, self.num_panels + 1):
            if self.scroll[i] is None: continue # Skip cleared panels

            title = self.form_title[i].text()
            data_to_save = {}

            # Check if it's a rating panel
            if self.groupButtonlist[i]:
                for j, task_label in enumerate(self.tasklist[i]):
                    task_text = task_label.text()
                    checked_button = self.groupButtonlist[i][j].checkedButton()
                    if checked_button:
                        data_to_save[task_text] = checked_button.text()
                
                # Save as JSON
                save_file = os.path.join(self.save_directory, f"{title}.json")
                with open(save_file, 'w') as f:
                    json.dump(data_to_save, f, indent=4)

            # Check if it's a time panel
            elif self.startingTimelist[i]:
                for j, task_label in enumerate(self.tasklist[i]):
                    task_text = task_label.text()
                    start_time = self.startingTimelist[i][j].text()
                    end_time = self.endingTimelist[i][j].text()
                    data_to_save[task_text] = {"start": start_time, "end": end_time}
                
                # Save as JSON
                save_file = os.path.join(self.save_directory, f"{title}.json")
                with open(save_file, 'w') as f:
                    json.dump(data_to_save, f, indent=4)
        
        self.errorLabel.setText(f"Annotations saved to {self.save_directory}")


    def clear_panels(self):
        """Removes all annotation panels from the UI."""
        for i in range(1, self.num_panels + 1):
            if self.scroll[i]:
                self.scroll[i].deleteLater()
                self.scroll[i] = None
        self._init_widget_lists() # Reset all widget lists
        self.num_panels = 0

    def change_directory(self):
        """Allows the user to change the main save directory."""
        new_dir = QFileDialog.getExistingDirectory(self, "Select Save Directory")
        if new_dir:
            self.parrentDirectory = new_dir
            if self.vidname:
                self._setup_save_directories()
            self.errorLabel.setText(f"Save directory changed to: {new_dir}")

    def _format_time(self, ms):
        """Converts milliseconds to a HH:MM:SS string."""
        s = ms // 1000
        m, s = divmod(s, 60)
        h, m = divmod(m, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"

    def keyPressEvent(self, event):
        """Handles keyboard shortcuts."""
        if event.key() == Qt.Key_Space:
            self.play_video()
        elif event.key() == Qt.Key_Right:
            self.mediaPlayer.setPosition(self.mediaPlayer.position() + 5000)  # Seek 5s forward
        elif event.key() == Qt.Key_Left:
            self.mediaPlayer.setPosition(self.mediaPlayer.position() - 5000)  # Seek 5s backward
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event):
        """Clean up resources on close."""
        if self.mediaPlayer:
            self.mediaPlayer.stop()
        if self.cap:
            self.cap.release()
        event.accept()

if __name__ == "__main__":
    # Ensure GStreamer is available on Linux
    if platform.system() == "Linux":
        if os.system("which gst-inspect-1.0 > /dev/null") != 0:
            print(
                "\nWarning: GStreamer not found. "
                "PyQt5.QtMultimedia on Linux requires it for video playback.\n"
                "Please install it using: sudo apt-get install libgstreamer1.0-0 gstreamer1.0-plugins-base gstreamer1.0-plugins-good gstreamer1.0-plugins-bad gstreamer1.0-libav\n"
            )

    app = QApplication(sys.argv)
    window = VideoPlayerWindow()
    sys.exit(app.exec_())