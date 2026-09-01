"""
Generate sample videos and download YOLO models for testing the ANPR system.
Creates 4 synthetic videos with simulated cars, license plates, and speed info.
"""
import os
import cv2
import numpy as np
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
logger = logging.getLogger(__name__)

# Indian license plate formats and sample data
SAMPLE_PLATES = [
    "KA05MH1234",
    "MH02CV5678",
    "DL01AB9012",
    "GJ01CK3456",
    "TN01CD7890",
    "KA01XY2345",
    "MH07BK6789",
    "UP14BD0123",
    "HR26GA4567",
    "PB01OP8901",
]

SAMPLE_SPEEDS = [25, 35, 45, 55, 65, 75]
VEHICLE_COLORS = [
    (200, 100, 50),    # Blue car
    (50, 100, 200),    # Red car
    (100, 200, 100),   # Green car
    (150, 150, 50),    # Cyan car
]


def draw_car(frame, x, y, width, height, color, plate_text, speed_kmph):
    """Draw a car with license plate and speed on the frame."""
    # Draw car body (rectangle)
    cv2.rectangle(frame, (x, y), (x + width, y + height), color, -1)
    
    # Draw car outline
    cv2.rectangle(frame, (x, y), (x + width, y + height), (0, 0, 0), 2)
    
    # Draw windows
    window_h = height // 3
    cv2.rectangle(frame, (x + 5, y + 5), (x + width - 5, y + window_h + 5), (100, 150, 200), -1)
    
    # Draw license plate (white rectangle at bottom)
    plate_y = y + height - 15
    plate_h = 12
    cv2.rectangle(frame, (x + 5, plate_y), (x + width - 5, plate_y + plate_h), (255, 255, 255), -1)
    cv2.rectangle(frame, (x + 5, plate_y), (x + width - 5, plate_y + plate_h), (0, 0, 0), 1)
    
    # Write plate text (white background, black text)
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 0.35
    thickness = 1
    text_size = cv2.getTextSize(plate_text, font, font_scale, thickness)[0]
    text_x = x + (width - text_size[0]) // 2
    text_y = plate_y + 10
    cv2.putText(frame, plate_text, (text_x, text_y), font, font_scale, (0, 0, 0), thickness)
    
    # Draw speed indicator above car
    speed_text = f"{speed_kmph} km/h"
    font_scale_speed = 0.4
    text_size_speed = cv2.getTextSize(speed_text, font, font_scale_speed, thickness)[0]
    speed_x = x + (width - text_size_speed[0]) // 2
    speed_y = y - 5
    cv2.rectangle(frame, (speed_x - 2, speed_y - 12), (speed_x + text_size_speed[0] + 2, speed_y + 2), (200, 200, 0), -1)
    cv2.putText(frame, speed_text, (speed_x, speed_y), font, font_scale_speed, (0, 0, 0), thickness)


def create_video(output_path, video_name, num_frames=300, fps=30):
    """Create a synthetic video with moving cars."""
    logger.info(f"Creating {video_name} ({num_frames} frames @ {fps} fps)...")
    
    # Video properties
    width, height = 1280, 720
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))
    
    if not out.isOpened():
        logger.error(f"Failed to create video writer for {output_path}")
        return False
    
    # Generate cars with trajectories
    cars = []
    for i in range(np.random.randint(3, 6)):  # 3-5 cars per video
        car = {
            'plate': SAMPLE_PLATES[i % len(SAMPLE_PLATES)],
            'speed': SAMPLE_SPEEDS[np.random.randint(0, len(SAMPLE_SPEEDS))],
            'color': VEHICLE_COLORS[i % len(VEHICLE_COLORS)],
            'start_x': np.random.randint(-100, width - 100),
            'y': np.random.randint(height // 4, height - 120),
            'width': np.random.randint(80, 120),
            'height': np.random.randint(50, 80),
        }
        cars.append(car)
    
    # Generate frames
    for frame_idx in range(num_frames):
        # Create background (road scene)
        frame = np.ones((height, width, 3), dtype=np.uint8) * 150  # Gray background
        
        # Draw road markings
        for i in range(0, width, 40):
            if (frame_idx // 2 + i) % 80 < 40:
                cv2.line(frame, (i, height // 2), (i + 40, height // 2), (255, 255, 255), 2)
        
        # Draw lane markers
        cv2.line(frame, (0, height // 3), (width, height // 3), (200, 200, 100), 2)
        cv2.line(frame, (0, 2 * height // 3), (width, 2 * height // 3), (200, 200, 100), 2)
        
        # Draw camera info
        camera_text = f"{video_name}"
        cv2.putText(frame, camera_text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 2)
        
        # Draw timestamp
        timestamp = f"Frame: {frame_idx}"
        cv2.putText(frame, timestamp, (width - 200, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 1)
        
        # Draw and animate cars
        for car in cars:
            # Calculate position (move left to right across screen)
            x = car['start_x'] + (frame_idx * car['speed'] // 10)
            
            # Only draw if car is within frame
            if -car['width'] < x < width:
                draw_car(frame, x, car['y'], car['width'], car['height'], 
                        car['color'], car['plate'], car['speed'])
        
        out.write(frame)
    
    out.release()
    logger.info(f"✓ Created {output_path}")
    return True


def download_yolo_models(models_dir):
    """Download YOLO models using ultralytics."""
    logger.info("Downloading YOLO models...")
    
    try:
        from ultralytics import YOLO
    except ImportError:
        logger.error("ultralytics not installed. Install it with: pip install ultralytics")
        return False
    
    os.makedirs(models_dir, exist_ok=True)
    
    # Download vehicle detector (COCO nano model)
    logger.info("Downloading YOLOv8 nano (vehicle detector)...")
    try:
        vehicle_model = YOLO('yolov8n.pt')  # Auto-downloads to ~/.yolo/
        logger.info("✓ YOLOv8 nano model ready")
    except Exception as e:
        logger.error(f"Failed to download vehicle model: {e}")
        return False
    
    # For plate detection, we'll use yolov8s as a placeholder
    # In production, this should be a fine-tuned model on plate dataset
    logger.info("Downloading YOLOv8 small (plate detector base)...")
    try:
        plate_model = YOLO('yolov8s.pt')  # This should be replaced with fine-tuned model
        # Copy to models directory
        plate_path = os.path.join(models_dir, 'plate_yolov8.pt')
        import shutil
        
        # Ultralytics stores models in ~/.yolo/weights/
        yolo_cache = os.path.expanduser('~/.yolo/weights/yolov8s.pt')
        if os.path.exists(yolo_cache):
            shutil.copy(yolo_cache, plate_path)
            logger.info(f"✓ Copied model to {plate_path}")
        else:
            logger.warning(f"Model cache not found at {yolo_cache}, YOLO will auto-download on first use")
    except Exception as e:
        logger.error(f"Failed to set up plate model: {e}")
        return False
    
    return True


def main():
    """Generate all sample data."""
    project_root = Path(__file__).parent
    sample_data_dir = project_root / "sample_data"
    models_dir = project_root / "models"
    
    # Create directories
    sample_data_dir.mkdir(exist_ok=True)
    models_dir.mkdir(exist_ok=True)
    
    logger.info(f"Project root: {project_root}")
    logger.info(f"Creating sample data in: {sample_data_dir}")
    logger.info(f"Creating models in: {models_dir}")
    
    # Create 4 sample videos
    videos = [
        ("cam1.mp4", "CAM_001: MG Road Junction", 300),
        ("cam2.mp4", "CAM_002: Silk Board Flyover", 300),
        ("cam3.mp4", "CAM_003: Indiranagar 100ft Road", 300),
        ("cam4.mp4", "CAM_004: Electronic City Toll", 300),
    ]
    
    for filename, display_name, frames in videos:
        video_path = sample_data_dir / filename
        create_video(str(video_path), display_name, num_frames=frames, fps=30)
    
    # Download YOLO models
    logger.info("\n" + "="*60)
    success = download_yolo_models(str(models_dir))
    
    if success:
        logger.info("="*60)
        logger.info("✓ All sample data created successfully!")
        logger.info(f"✓ Videos: {sample_data_dir}")
        logger.info(f"✓ Models: {models_dir}")
    else:
        logger.warning("Models download had issues, but videos were created.")
        logger.info("Try running: python -m pip install ultralytics")


if __name__ == "__main__":
    main()
