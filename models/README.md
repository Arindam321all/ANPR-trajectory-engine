# YOLO Models for ANPR System

This directory contains configuration and setup code for the YOLO models required by the ANPR system.

## Models Required

The ANPR pipeline uses two YOLOv8 models:

### 1. Vehicle Detector (yolov8n.pt)
- **Purpose**: Detect vehicles in frames (cars, trucks, buses, motorcycles)
- **Model Size**: YOLOv8 Nano (~6 MB)
- **Training Data**: COCO dataset (general object detection)
- **Classes Detected**: Car, Motorcycle, Bus, Truck
- **Auto-downloaded**: Yes, on first use

### 2. Plate Detector (yolov8s.pt or plate_yolov8.pt)
- **Purpose**: Localize license plates within vehicle images
- **Model Size**: YOLOv8 Small (~22 MB) - base model
- **Note**: The base yolov8s.pt should be replaced with a fine-tuned model trained on license plate datasets for production use
- **Training Data Recommendation**: 
  - CCPD (Chinese City Parking Dataset)
  - OpenALPR dataset
  - Indian plate dataset (for regional deployment)
- **Auto-downloaded**: Yes, on first use

## Setup

### Automatic Setup (Recommended)
Models are automatically downloaded and cached by ultralytics on first run:

```bash
python main.py
```

The system will detect missing models and download them to:
- Linux/Mac: `~/.yolo/weights/`
- Windows: `C:\Users\<username>\.yolo\weights\`

### Manual Setup
To pre-download models before running the system:

```bash
python models/__init__.py
```

## Configuration

Model paths are configured in `config.yaml`:

```yaml
detection:
  plate_model_path: "models/plate_yolov8.pt"
  vehicle_model_path: "yolov8n.pt"
  confidence_threshold: 0.45
  ocr_confidence_threshold: 0.35
```

## Production Deployment

### For Best Accuracy:
1. **Fine-tune plate detector** on your regional license plate dataset
   - Use YOLOv8 training on annotated plate images
   - Test on local traffic samples
   - Update `plate_model_path` in config.yaml

2. **Benchmark performance**
   - Test detection/OCR on your camera feeds
   - Adjust confidence thresholds in config.yaml
   - Optimize frame_skip for your hardware

3. **Consider model size vs speed**
   - nano (yolov8n): ~6 MB, fastest
   - small (yolov8s): ~22 MB, good accuracy
   - medium (yolov8m): ~49 MB, better accuracy
   - large (yolov8l): ~100 MB, best accuracy

## Troubleshooting

### Models Not Downloading
```bash
# Check ultralytics installation
pip list | grep ultralytics

# Reinstall if needed
pip install --upgrade ultralytics

# Manual download (if auto-download fails)
python -c "from ultralytics import YOLO; YOLO('yolov8n.pt'); YOLO('yolov8s.pt')"
```

### Storage Issues
- Default cache: `~/.yolo/weights/` (~30-40 MB for both models)
- To change cache location:
```python
import os
os.environ['YOLOv8_WEIGHTS'] = '/path/to/custom/cache'
```

### Performance Issues
- Reduce model size (use nano instead of medium/large)
- Increase frame_skip in config.yaml
- Use GPU acceleration if available
- Consider multiprocessing for multiple cameras

## References

- **YOLOv8 Docs**: https://docs.ultralytics.com/
- **CCPD Dataset**: https://github.com/PKLDoc/CCPD
- **OpenALPR**: https://github.com/openalpr/openalpr
- **EasyOCR**: https://github.com/JaidedAI/EasyOCR

## License

- YOLOv8: AGPL-3.0 (use for non-commercial), or commercial license
- Sample detection models: Trained on COCO (CC BY 4.0)
- Ensure compliance with your regional deployment
