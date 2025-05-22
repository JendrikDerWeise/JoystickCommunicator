import time
import io
from picamera2 import Picamera2, Preview
from libcamera import controls  # For autofocus modes


class RearCamera:
    def __init__(self, resolution=(640, 480), framerate=20):
        self.picam2 = None
        self.resolution = resolution
        self.framerate = framerate
        self.is_streaming = False
        self._preview_active = False  # To manage X11 preview if used for debugging

        try:
            self.picam2 = Picamera2()
            print("RearCamera: Picamera2 object created.")
        except Exception as e:
            print(f"RearCamera: Error initializing Picamera2: {e}")
            self.picam2 = None  # Ensure it's None if initialization fails

    def start_stream(self):
        if not self.picam2:
            print("RearCamera: Cannot start stream, Picamera2 not initialized.")
            return False
        if self.is_streaming:
            print("RearCamera: Stream already started.")
            return True

        try:
            # Configure for video recording, which is suitable for streaming frames
            config = self.picam2.create_video_configuration(
                main={"size": self.resolution, "format": "RGB888"},
                # MJPEG can also be an option if capturing directly to it
                controls={"FrameRate": float(self.framerate)}
            )
            self.picam2.configure(config)

            # Optional: Autofocus settings
            # self.picam2.set_controls({"AfMode": controls.AfModeEnum.Continuous, "AfSpeed": controls.AfSpeedEnum.Fast})

            self.picam2.start()
            self.is_streaming = True
            print(f"RearCamera: Stream started at {self.resolution} @ {self.framerate}fps.")
            # For local debugging on a connected display (remove for headless operation)
            # self.picam2.start_preview(Preview.QTGL) # Or Preview.DRM for console
            # self._preview_active = True
            return True
        except Exception as e:
            print(f"RearCamera: Error starting stream: {e}")
            self.is_streaming = False
            return False

    def stop_stream(self):
        if not self.picam2 or not self.is_streaming:
            # print("RearCamera: Stream not active or Picamera2 not initialized.") # Can be noisy
            return
        try:
            # if self._preview_active:
            #     self.picam2.stop_preview()
            #     self._preview_active = False
            self.picam2.stop()
            self.is_streaming = False
            print("RearCamera: Stream stopped.")
        except Exception as e:
            print(f"RearCamera: Error stopping stream: {e}")

    def get_frame(self):
        if not self.picam2 or not self.is_streaming:
            return None
        try:
            # Capture to a buffer in memory as JPEG
            # For RGB888 configured stream, you'd capture raw and then encode.
            # If configured for MJPEG, you could capture directly.
            # Let's assume RGB888 and encode manually for more control / if other formats needed.

            # For higher performance, picamera2 can encode to MJPEG directly if configured.
            # However, capturing RGB888 and then encoding to JPEG gives flexibility.
            # For simplicity and to avoid reconfiguring the stream dynamically if not needed:

            # Simplest way to get a JPEG from an RGB stream:
            buffer = io.BytesIO()
            self.picam2.capture_file(buffer, format="jpeg", quality=85)  # Capture as JPEG
            buffer.seek(0)
            return buffer.read()

            # Alternative if you need the raw array first (e.g. for OpenCV processing)
            # frame_array = self.picam2.capture_array("main") # Captures the main stream array (e.g. RGB888)
            # if frame_array is not None:
            #     # If you have OpenCV and want to encode with it:
            #     import cv2
            #     is_success, jpeg_bytes = cv2.imencode(".jpg", frame_array, [cv2.IMWRITE_JPEG_QUALITY, 85])
            #     if is_success:
            #         return jpeg_bytes.tobytes()
            # return None

        except Exception as e:
            print(f"RearCamera: Error capturing frame: {e}")
            return None

    def __del__(self):
        self.stop_stream()
        if self.picam2:
            try:
                self.picam2.close()  # Properly release the camera
                print("RearCamera: Picamera2 object closed.")
            except Exception as e:
                print(f"RearCamera: Error closing Picamera2 object: {e}")