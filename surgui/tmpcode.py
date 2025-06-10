from PyQt5.QtWidgets import QSlider, QLabel, QVBoxLayout, QWidget
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QPixmap, QPainter, QFont
import cv2

class VideoSlider(QSlider):
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
        self.preview_label.setFixedSize(200, 150)
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
        # if hasattr(self.window, 'current_video_path'):
        #     cap = cv2.VideoCapture(self.window.current_video_path)
        #     fps = cap.get(cv2.CAP_PROP_FPS)
        #     frame_number = int(position_seconds * fps)
        #     cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
        #     ret, frame = cap.read()
        #     cap.release()
        #     return frame if ret else None
        
        return None

    def position_preview(self, global_pos):
        """Position preview near mouse cursor"""
        if self.preview_label:
            self.preview_label.move(
                global_pos.x() - self.preview_label.width() // 2,
                global_pos.y() - self.preview_label.height() - 20
            )


# Alternative: Extra Wide Slider with Timeline Marks
class TimelineSlider(VideoSlider):
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


# Usage example:
"""
# In your main window class:
def setup_slider(self):
    self.slider = VideoSlider(self)  # or TimelineSlider(self)
    self.slider.setup_preview(self)
    
    # Connect to your existing signal handlers
    self.slider.valueChanged.connect(self.on_slider_changed)
    
    # Add to your layout
    self.layout.addWidget(self.slider)
"