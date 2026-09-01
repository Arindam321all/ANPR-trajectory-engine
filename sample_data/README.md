# Sample Data for ANPR System

## Video Files

This directory contains 4 synthetic sample videos for testing the ANPR (Automatic Number Plate Recognition) system:

### Videos
- **cam1.mp4** - CAM_001: MG Road Junction
  - 300 frames @ 30 fps (~10 seconds)
  - Multiple synthetic cars with Indian license plates
  - Speed variations: 25-75 km/h

- **cam2.mp4** - CAM_002: Silk Board Flyover
  - 300 frames @ 30 fps (~10 seconds)
  - Synthetic traffic with realistic vehicle movements
  - License plates in Indian format (e.g., KA05MH1234)

- **cam3.mp4** - CAM_003: Indiranagar 100ft Road
  - 300 frames @ 30 fps (~10 seconds)
  - Multiple vehicle trajectories
  - Speed indicators displayed above each vehicle

- **cam4.mp4** - CAM_004: Electronic City Toll
  - 300 frames @ 30 fps (~10 seconds)
  - Synthetic road scene with toll gate simulation
  - License plates with varying speeds

## Video Contents

Each video includes:
- **Vehicle Visualization**: Simulated cars with:
  - Body color (varies by vehicle)
  - Windows
  - License plates (white rectangle at bottom)
  - Indian-style registration numbers

- **Speed Information**: Speed indicator above each vehicle
  - Displays current speed in km/h
  - Used for analytics and speed violation detection

- **Timing Information**: Frame counter and camera name

## Generated Synthetic Data

Sample license plates used in videos:
- KA05MH1234 (Karnataka, Bangalore)
- MH02CV5678 (Maharashtra, Mumbai)
- DL01AB9012 (Delhi)
- GJ01CK3456 (Gujarat)
- TN01CD7890 (Tamil Nadu)
- And more...

Sample speeds demonstrated:
- 25, 35, 45, 55, 65, 75 km/h

## Usage

These videos are referenced in `config.yaml`:
```yaml
cameras:
  - id: CAM_001
    source: "sample_data/cam1.mp4"
    ...
```

To run the system with sample data:
```bash
python main.py
```

The system will:
1. Load each video from sample_data/
2. Detect plates using YOLOv8 model
3. OCR the plate text using EasyOCR
4. Log detections to the database
5. Track vehicles across cameras
6. Calculate speeds and detect violations

## Model Requirements

The ANPR system requires:
- **yolov8n.pt** - Vehicle detector (COCO nano model)
- **yolov8s.pt** - Plate detection (base model, should be fine-tuned on plate dataset in production)

These are auto-downloaded by the system on first use via ultralytics.

To pre-download models:
```bash
python models/__init__.py
```

## Notes

- Videos are synthetic and created with OpenCV for demonstration purposes
- Real-world deployment requires fine-tuned plate detection models trained on actual license plate datasets
- Video format: MP4 with mp4v codec, 1280x720 resolution, 30 fps
- Total size: ~5.3 MB for all 4 videos
