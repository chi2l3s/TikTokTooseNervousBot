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

    def _build_smooth_trajectory(self, raw_targets: list[int], fps: float, width: int, crop_w: int) -> np.ndarray:
        total_frames = len(raw_targets)
        min_x = crop_w // 2
        max_x = width - crop_w // 2
        default_x = width // 2

        if total_frames == 0:
            return np.array([default_x], dtype=int)

        sample_rate = 5
        sampled_targets = []
        for i in range(0, total_frames, sample_rate):
            chunk = [x for x in raw_targets[i:i + sample_rate] if x is not None]
            val = int(np.median(chunk)) if chunk else None
            sampled_targets.append(val)

        last_valid = default_x
        filled_anchors = []
        for val in sampled_targets:
            if val is not None:
                last_valid = val
            filled_anchors.append(last_valid)

        trajectory = np.zeros(total_frames, dtype=float)
        current_cam_x = float(filled_anchors[0])
        pan_duration_frames = int(fps * 1.0)
        deadzone_px = 65.0

        i = 0
        while i < total_frames:
            anchor_idx = min(i // sample_rate, len(filled_anchors) - 1)
            target_x = float(filled_anchors[anchor_idx])

            if abs(target_x - current_cam_x) > deadzone_px:
                start_x = current_cam_x
                end_x = target_x
                transition_len = min(pan_duration_frames, total_frames - i)

                for step in range(transition_len):
                    progress = step / max(1, transition_len - 1)
                    eased_progress = self._smootherstep(progress)
                    trajectory[i + step] = start_x + (end_x - start_x) * eased_progress

                current_cam_x = end_x
                i += transition_len
            else:
                trajectory[i] = current_cam_x
                i += 1

        clamped = np.clip(trajectory, min_x, max_x).astype(int)
        return clamped

    def crop_video_dynamic(self, input_video: str, output_video: str):
        cap = cv2.VideoCapture(input_video)
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        target_crop_width = int(height * 9 / 16)
        if target_crop_width > width:
            target_crop_width = width

        raw_targets = []
        last_detected_x = None

        frame_idx = 0
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break

            if frame_idx % 5 == 0:
                results = self.model(frame, classes=[0], verbose=False)
                boxes = results[0].boxes
                if len(boxes) > 0:
                    best_box = max(boxes, key=lambda b: (b.xyxy[0][2] - b.xyxy[0][0]) * (b.xyxy[0][3] - b.xyxy[0][1]))
                    x1, _, x2, _ = best_box.xyxy[0].cpu().numpy()
                    last_detected_x = int((x1 + x2) / 2)
                else:
                    last_detected_x = None

            raw_targets.append(last_detected_x)
            frame_idx += 1

        cap.release()

        smooth_trajectory = self._build_smooth_trajectory(
            raw_targets=raw_targets,
            fps=fps,
            width=width,
            crop_w=target_crop_width
        )

        cap = cv2.VideoCapture(input_video)
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        out = cv2.VideoWriter(output_video, fourcc, fps, (1080, 1920))

        frame_idx = 0
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break

            center_x = smooth_trajectory[min(frame_idx, len(smooth_trajectory) - 1)]
            x1 = center_x - target_crop_width // 2
            x2 = x1 + target_crop_width
            cropped = frame[0:height, x1:x2]
            resized = cv2.resize(cropped, (1080, 1920), interpolation=cv2.INTER_LANCZOS4)
            out.write(resized)
            frame_idx += 1

        cap.release()
        out.release()