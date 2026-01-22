"""
Test script for image processing without running the Telegram bot.

Usage:
    python test_ocr.py                           # Process all images in sample_images/
    python test_ocr.py path/to/image.jpg         # Process a single image
    python test_ocr.py path/to/folder/           # Process all images in a folder
"""

import sys
import logging
from pathlib import Path

# Setup logging - use DEBUG level to see OCR details
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.DEBUG,
)
logger = logging.getLogger(__name__)

# Reduce noise from other libraries
logging.getLogger("PIL").setLevel(logging.WARNING)
logging.getLogger("pytesseract").setLevel(logging.WARNING)

# Import after logging setup
from src.services.image_processor import process_schedule_image


def process_single_image(image_path: Path) -> None:
    """Process a single image and print results."""
    print(f"\n{'='*60}")
    print(f"Processing: {image_path.name}")
    print('='*60)
    
    # Read image bytes
    image_bytes = image_path.read_bytes()
    
    # Process
    try:
        schedule = process_schedule_image(image_bytes)
        
        if schedule:
            print(f"\n✅ Found {len(schedule)} shifts:")
            for entry in schedule:
                shift_date = entry["date"]
                shift_code = entry["shift"]
                shift_info = entry.get("shift_info", {})
                shift_name = shift_info.get("name", "?")
                print(f"  • {shift_date.strftime('%a %d %b')}: {shift_code} ({shift_name})")
        else:
            print("\n❌ No shifts found in image")
            
    except Exception as e:
        print(f"\n❌ Error processing image: {e}")
        logger.exception("Full traceback:")


def main() -> None:
    """Main entry point."""
    # Determine input path
    if len(sys.argv) > 1:
        input_path = Path(sys.argv[1])
    else:
        input_path = Path("sample_images")
    
    if not input_path.exists():
        print(f"❌ Path not found: {input_path}")
        print("\nUsage:")
        print("  python test_ocr.py                    # Process all in sample_images/")
        print("  python test_ocr.py image.jpg          # Process single image")
        print("  python test_ocr.py folder/            # Process all in folder")
        sys.exit(1)
    
    # Collect images to process
    image_extensions = {".jpg", ".jpeg", ".png", ".webp"}
    
    if input_path.is_file():
        images = [input_path]
    else:
        images = [
            f for f in input_path.iterdir()
            if f.suffix.lower() in image_extensions
        ]
        images.sort()
    
    if not images:
        print(f"❌ No images found in: {input_path}")
        sys.exit(1)
    
    print(f"Found {len(images)} image(s) to process")
    
    # Process each image
    for image_path in images:
        process_single_image(image_path)
    
    print(f"\n{'='*60}")
    print("Done!")
    print(f"Check debug/ folder for cell images (if DEBUG_SAVE_CELLS=true)")


if __name__ == "__main__":
    main()
