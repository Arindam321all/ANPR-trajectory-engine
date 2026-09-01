# ANPR Project Setup - Sample Data & Models

## ✅ Setup Complete!

Your ANPR project now has everything required to run smoothly.

## 📁 Created Files

### Sample Videos (`sample_data/`)
4 synthetic traffic videos with simulated cars:
- **cam1.mp4** (1.2 MB) - MG Road Junction
- **cam2.mp4** (1.4 MB) - Silk Board Flyover  
- **cam3.mp4** (1.1 MB) - Indiranagar 100ft Road
- **cam4.mp4** (1.4 MB) - Electronic City Toll
- **README.md** - Documentation

**Total**: ~5.3 MB of sample video data

### Models Setup (`models/`)
- **__init__.py** - Model initialization & download script
- **README.md** - Model configuration guide

## 📦 Models (Auto-Downloaded)

The following YOLO models are auto-downloaded on first run:

1. **yolov8n.pt** (6 MB)
   - Vehicle detector for identifying cars, trucks, buses, motorcycles
   - Cached at: `~/.yolo/weights/yolov8n.pt`

2. **yolov8s.pt** (22 MB)
   - License plate detector base model
   - Cached at: `~/.yolo/weights/yolov8s.pt`
   - Note: Should be fine-tuned on plate datasets for production

**Total Models**: ~28 MB (auto-cached, not in repo)

## 🚀 Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Initialize Database
```bash
python -c "from db.database import init_db; init_db()"
```

### 3. Run the System
```bash
python main.py
```

### Optional: Pre-download Models
```bash
python models/__init__.py
```

## 📹 Video Features

Each synthetic video includes:

✓ Multiple synthetic cars with realistic movement
✓ Indian-style license plates (e.g., KA05MH1234, MH02CV5678)
✓ Speed indicators (25-75 km/h range)
✓ Camera identification overlay
✓ Frame counter and timestamp
✓ Road markings and lane indicators

## 🔍 System Flow

1. **Video Input**: Loads from `sample_data/cam*.mp4`
2. **Detection**: YOLOv8 finds vehicles and plates
3. **OCR**: EasyOCR extracts plate text
4. **Database**: Logs detections with vehicle info
5. **Tracking**: Builds vehicle trajectories across cameras
6. **Analytics**: Computes speeds, detects violations

## 📊 Configuration

All cameras are configured in `config.yaml`:
- Camera IDs and names
- Video source paths (pointing to sample_data/)
- Geographic locations (lat/lon)
- Speed limits and detection parameters
- Camera connections for trajectory tracking

## ✨ Next Steps

### For Testing
- Run `python main.py` to process sample videos
- Check database: `city_anpr.db`
- Query detections table for plate readings

### For Production
1. Replace sample videos with actual camera feeds (RTSP/HTTP streams)
2. Fine-tune plate detection model on your regional dataset
3. Adjust detection thresholds in `config.yaml`
4. Deploy database to production storage
5. Set up analytics and dashboard

### Project Structure
```
anpr_engine/
├── main.py                    # Entry point
├── config.yaml               # Camera & detection config
├── requirements.txt          # Python dependencies
├── sample_data/              # ✓ Sample videos (CREATED)
│   ├── cam1.mp4
│   ├── cam2.mp4
│   ├── cam3.mp4
│   ├── cam4.mp4
│   └── README.md
├── models/                   # ✓ Model setup (CREATED)
│   ├── __init__.py
│   └── README.md
├── detection/                # Plate/vehicle detection
├── tracking/                 # Vehicle trajectory tracking
├── db/                       # Database
└── api/                      # REST API
```

## 🐛 Troubleshooting

### "Failed to open source" Error
- Check if video files exist: `sample_data/cam*.mp4`
- Verify paths in `config.yaml`
- Ensure OpenCV can read MP4 files: `pip install opencv-python`

### Model Download Issues
- Check internet connection
- Reinstall ultralytics: `pip install --upgrade ultralytics`
- Models will auto-download on first use

### OCR Not Working
- Ensure EasyOCR is installed: `pip install easyocr`
- First run will download OCR models (internet required)
- Check GPU availability for faster OCR

### Database Errors
- Delete `city_anpr.db` if corrupted
- Re-run: `python -c "from db.database import init_db; init_db()"`

## 📚 Documentation

- **Sample Data**: See `sample_data/README.md`
- **Models**: See `models/README.md`
- **API**: See `api/main.py` for REST endpoints
- **Database**: See `db/schema.sql` for data structure

---

**Status**: ✅ Ready to Run!

Run `python main.py` to start processing sample video data.
