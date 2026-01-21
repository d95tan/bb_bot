import logging
import os
import sys

# Add project root to path
sys.path.insert(0, os.getcwd())

from src.services.image_processor import process_schedule_image

# Configure logging
logging.basicConfig(filename='debug.log', filemode='w', level=logging.DEBUG, force=True)
logging.getLogger("src.services.image_processor").setLevel(logging.DEBUG)

def test_image(image_path):
    print(f"Testing image: {image_path}")
    with open(image_path, "rb") as f:
        image_data = f.read()
    
    # Debug: OCR full image to see what's visible
    from PIL import Image
    from io import BytesIO
    import pytesseract
    img = Image.open(BytesIO(image_data))
    print("Full Image OCR Preview:")
    print(pytesseract.image_to_string(img)[:500])
    print("-" * 20)
    
    try:
        schedule = process_schedule_image(image_data)
        print(f"Result: extracted {len(schedule)} shifts")
        if not schedule:
            print("FAILURE: No schedule extracted")
        else:
            print("SUCCESS: Schedule extracted")
            for shift in schedule[:3]:
                print(f"  - {shift['date']}: {shift['shift']}")
    except Exception as e:
        print(f"EXCEPTION: {e}")

if __name__ == "__main__":
    image_path = "sample_images/photo_1_2025-12-09_18-03-49.jpg"
    test_image(image_path)
