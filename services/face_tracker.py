import cv2
import numpy as np
from ultralytics import YOLO

class SmartCropper:
    def __init__(self):
        self.model = YOLO("yolov8n.pt")

    @staticmethod
    def _smootherstep(t: float) -> float:
        t = max(0.0, min(1.0, t))
        return t * t * t * (t * (t * 6.0 - 15.0) + 10.0)

    def _get_target_dimensions(self, width: int, height: int, aspect_ratio: str) -> tuple[int, int]:
        if aspect_ratio == "9:16":
            target_w = int(height * 9 / 16)
            return min(target_w, width), height
        elif aspect_ratio == "4:3":
            target_w = int(height * 4 / 3)
            return min(target_w, width), height
        else:
            return width, height

    def _build_smooth_trajectory(
        self,
        raw_targets: list[int | None],
        fps: float,
        width: int,
        crop_w: int,
    ) -> np.ndarray:
        total_frames = len(raw_targets)
        min_x = crop_w // 2
        max_x = width - crop_w // 2
        default_x = width // 2

        if total_frames == 0:
            return np.array([default_x], dtype=int)

        anchors = []
        current_focus = default_x
        lost_count = 0
        hold_counter = 0
        min_hold_frames = int(fps * 2.5)

        for target in raw_targets:
            if target is not None:
                lost_count = 0
                if hold_counter >= min_hold_frames:
                    if abs(target - current_focus) > 90:
                        current_focus = target
                        hold_counter = 0
                else:
                    if abs(target - current_focus) < 60:
                        current_focus = int(0.9 * current_focus + 0.1 * target)
            else:
                lost_count += 1
                if lost_count > int(fps * 2.0):
                    current_focus = default_x

            hold_counter += 1
            anchors.append(current_focus)

        trajectory = np.zeros(total_frames, dtype=float)
        current_cam_x = float(anchors[0])
        pan_duration = int(fps * 1.0)
        i = 0

        while i < total_frames:
            target_x = float(anchors[i])
            if abs(target_x - current_cam_x) > 30.0:
                start_x = current_cam_x
                end_x = target_x
                trans_len = min(pan_duration, total_frames - i)

                for step in range(trans_len):
                    progress = step / max(1, trans_len - 1)
                    trajectory[i + step] = start_x + (end_x - start_x) * self._smootherstep(progress)

                current_cam_x = end_x
                i += trans_len
            else:
                trajectory[i] = current_cam_x
                i += 1

        return np.clip(trajectory, min_x, max_x).astype(int)

    def crop_video(
        self,
        input_video: str,
        output_video: str,
        aspect_ratio: str = "9:16",
        enable_tracking: bool = True,
        progress_callback=None,
    ):
        cap = cv2.VideoCapture(input_video)
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        target_w, target_h = self._get_target_dimensions(width, height, aspect_ratio)

        if aspect_ratio == "9:16":
            final_w, final_h = 1080, 1920
        elif aspect_ratio == "4:3":
            final_w, final_h = 1440, 1080
        else:
            final_w, final_h = 1920, 1080

        if not enable_tracking or aspect_ratio == "16:9" or target_w >= width:
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            out = cv2.VideoWriter(output_video, fourcc, fps, (final_w, final_h))
            center_x = width // 2
            x1 = max(0, center_x - target_w // 2)
            x2 = min(width, x1 + target_w)

            frame_idx = 0
            while cap.isOpened():
                ret, frame = cap.read()
                if not ret:
                    break
                cropped = frame[0:target_h, x1:x2]
                resized = cv2.resize(cropped, (final_w, final_h), interpolation=cv2.INTER_LANCZOS4)
                out.write(resized)
                frame_idx += 1
                if progress_callback and frame_idx % 25 == 0:
                    progress_callback(frame_idx, total_frames)

            cap.release()
            out.release()
            return

        raw_targets = []
        last_tracked_x = None
        frame_idx = 0

        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break

            if frame_idx % 4 == 0:
                results = self.model(frame, classes=[0], verbose=False)
                boxes = results[0].boxes
                if len(boxes) > 0:
                    if last_tracked_x is not None:
                        best_box = min(
                            boxes,
                            key=lambda b: abs(((b.xyxy[0][0] + b.xyxy[0][2]) / 2).item() - last_tracked_x),
                        )
                    else:
                        best_box = max(
                            boxes,
                            key=lambda b: (b.xyxy[0][2] - b.xyxy[0][0]) * (b.xyxy[0][3] - b.xyxy[0][1]),
                        )

                    x1, _, x2, _ = best_box.xyxy[0].cpu().numpy()
                    last_tracked_x = int((x1 + x2) / 2)
                else:
                    last_tracked_x = None

            raw_targets.append(last_tracked_x)
            frame_idx += 1

        cap.release()

        trajectory = self._build_smooth_trajectory(raw_targets, fps, width, target_w)

        cap = cv2.VideoCapture(input_video)
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        out = cv2.VideoWriter(output_video, fourcc, fps, (final_w, final_h))

        frame_idx = 0
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break

            c_x = trajectory[min(frame_idx, len(trajectory) - 1)]
            x1 = c_x - target_w // 2
            x2 = x1 + target_w
            cropped = frame[0:target_h, x1:x2]
            resized = cv2.resize(cropped, (final_w, final_h), interpolation=cv2.INTER_LANCZOS4)
            out.write(resized)

            frame_idx += 1
            if progress_callback and frame_idx % 25 == 0:
                progress_callback(frame_idx, total_frames)

        cap.release()
        out.release()