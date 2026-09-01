"""
Download and setup YOLO models for the ANPR system.
Run this to pre-download models, or they will auto-download on first use.
"""
import os
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
logger = logging.getLogger(__name__)


def setup_models():
    """Setup YOLO models for the project."""
    try:
        from ultralytics import YOLO
        logger.info("ultralytics found, downloading models...")
    except ImportError:
        logger.error("❌ ultralytics not installed!")
        logger.info("Install it with: pip install ultralytics opencv-python easyocr")
        return False
    
    models_dir = Path(__file__).parent / "models"
    models_dir.mkdir(exist_ok=True)
    
    try:
        # Load and download vehicle detector (COCO nano - ~6MB)
        logger.info("📥 Downloading yolov8n.pt (vehicle detector, ~6MB)...")
        vehicle_model = YOLO('yolov8n.pt')
        logger.info("✓ Vehicle detector ready")
        
        # Load and download plate detector base model (COCO small - ~22MB)
        # Note: This should be fine-tuned on plate dataset in production
        logger.info("📥 Downloading yolov8s.pt (plate detector base, ~22MB)...")
        plate_model = YOLO('yolov8s.pt')
        logger.info("✓ Plate detector ready")
        
        # Try to copy to models directory for reference
        try:
            import shutil
            yolo_cache = Path.home() / ".yolo" / "weights"
            if yolo_cache.exists():
                src_yolov8s = yolo_cache / "yolov8s.pt"
                if src_yolov8s.exists():
                    dest = models_dir / "plate_yolov8.pt"
                    if not dest.exists():
                        shutil.copy(src_yolov8s, dest)
                        logger.info(f"✓ Copied model to {dest}")
        except Exception as e:
            logger.debug(f"Could not copy model to models dir: {e}")
        
        logger.info("\n" + "="*60)
        logger.info("✓ Models setup complete!")
        logger.info("  - yolov8n.pt: Vehicle detector (auto-located by ultralytics)")
        logger.info("  - yolov8s.pt: Plate detector (auto-located by ultralytics)")
        logger.info("="*60)
        return True
        
    except Exception as e:
        logger.error(f"❌ Model download failed: {e}")
        logger.info("\nTroubleshooting:")
        logger.info("1. Check internet connection")
        logger.info("2. Try: pip install --upgrade ultralytics")
        logger.info("3. Models will auto-download on first run if this fails")
        return False


if __name__ == "__main__":
    setup_models()
