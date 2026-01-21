"""
Image processing service for extracting shift schedules from screenshots.

Uses pytesseract for OCR and PIL for image manipulation and color detection.
"""

import logging
import re
from calendar import monthrange
from datetime import date
from io import BytesIO
from typing import Optional

from PIL import Image
import pytesseract
from pytesseract import Output

from src.config import get_shift_config


logger = logging.getLogger(__name__)

# Month name to number mapping
MONTHS = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}


def process_schedule_image(image_data: bytes) -> list[dict]:
    """
    Process a schedule screenshot and extract shift information.
    
    Args:
        image_data: Raw bytes of the image file
        
    Returns:
        List of dictionaries containing:
        - date: The shift date (datetime.date)
        - shift: The shift code/type (str)
        - shift_info: Full shift configuration dict
    """
    logger.info(f"Processing schedule image ({len(image_data)} bytes)")
    
    # Load image
    image = Image.open(BytesIO(image_data))
    
    # Convert to RGB if necessary
    if image.mode != "RGB":
        image = image.convert("RGB")
    
    # Extract month and year from header
    month, year = extract_month_year(image)
    if not month or not year:
        logger.error("Could not extract month/year from image")
        return []
    
    logger.info(f"Detected schedule for {month}/{year}")
    
    # Extract schedule grid
    schedule = extract_schedule_grid(image, month, year)
    
    logger.info(f"Extracted {len(schedule)} shifts from image")
    
    return schedule


def extract_month_year(image: Image.Image) -> tuple[Optional[int], Optional[int]]:
    """
    Extract month and year from the header of the schedule image.
    
    The header contains text like "Aug 2025" or "Jul 2025" in a blue pill.
    """
    # Crop the header area (top portion of image)
    width, height = image.size
    header_region = image.crop((0, 0, width, int(height * 0.35)))
    
    # Run OCR on header
    # Use psm 6 for uniform block of text
    custom_config = r'--oem 3 --psm 6'
    header_text = pytesseract.image_to_string(header_region, config=custom_config)
    logger.debug(f"Header OCR text: {header_text}")
    
    # Look for month year pattern
    # Pattern: "Jan 2025", "January 2025", "Aug 2025", etc.
    # Allow for some noise characters and newlines
    pattern = r"([A-Za-z]+)[\s\.,_-]*(\d{4})"
    match = re.search(pattern, header_text)
    
    if match:
        month_str = match.group(1).lower()
        year = int(match.group(2))
        
        # Convert month name to number
        month = MONTHS.get(month_str[:3])  # Use first 3 chars for matching
        
        if month:
            return month, year
    
    logger.warning(f"Failed to match month/year in header text: '{header_text.strip()}'")
    return None, None


def extract_schedule_grid(image: Image.Image, month: int, year: int) -> list[dict]:
    """
    Extract shift data from the calendar grid.
    
    Strategy:
    1. Identify the grid area (below header, above footer)
    2. Divide into 7 columns (Mon-Sun) and ~5-6 rows
    3. For each cell, extract shift code and detect dominant color
    4. Map to dates based on position
    """
    width, height = image.size
    shift_config = get_shift_config()
    
    # Dynamically find grid top based on day names
    grid_top = find_grid_top(image)
    if not grid_top:
        # Fallback if detection fails
        logger.warning("Could not detect grid top dynamically, using fallback")
        grid_top = int(height * 0.38)
        
    # Define grid boundaries (approximate based on observed screenshots)
    grid_bottom = int(height * 0.85)   # Above footer navigation
    grid_left = int(width * 0.02)
    grid_right = int(width * 0.98)
    
    # Calculate cell dimensions
    grid_width = grid_right - grid_left
    grid_height = grid_bottom - grid_top
    
    col_width = grid_width // 7
    row_height = grid_height // 6  # Max 6 rows for a month
    
    # Get the first day of the month and total days
    first_weekday, num_days = monthrange(year, month)
    # Python's monthrange returns 0=Monday, 6=Sunday
    # Our grid is Mon-Sun (0-6), so this aligns
    
    schedule = []
    
    # Iterate through potential cells
    for row in range(6):  # Max 6 rows
        for col in range(7):  # 7 days per week
            # Calculate which day this cell represents
            cell_index = row * 7 + col
            day_offset = cell_index - first_weekday
            
            if day_offset < 0 or day_offset >= num_days:
                continue  # Cell is outside current month
            
            day = day_offset + 1
            
            # Calculate cell boundaries
            cell_left = grid_left + col * col_width
            cell_top = grid_top + row * row_height
            cell_right = cell_left + col_width
            cell_bottom = cell_top + row_height
            
            # Extract cell image
            cell_image = image.crop((cell_left, cell_top, cell_right, cell_bottom))
            
            # Extract shift code and color from cell
            shift_code, dominant_color = extract_cell_data(cell_image)
            
            if shift_code:
                # Look up shift info
                shift_info = shift_config.get_shift(shift_code, dominant_color)
                
                if shift_info:
                    schedule.append({
                        "date": date(year, month, day),
                        "shift": shift_code,
                        "shift_info": shift_info,
                    })
                else:
                    # Unknown shift - log and include with minimal info
                    logger.warning(f"Unknown shift code: {shift_code} on {year}-{month:02d}-{day:02d}")
                    schedule.append({
                        "date": date(year, month, day),
                        "shift": shift_code,
                        "shift_info": {
                            "name": shift_code,
                            "all_day": True,
                            "description": f"Unknown shift: {shift_code}",
                        },
                    })
    
    return schedule


def extract_cell_data(cell_image: Image.Image) -> tuple[Optional[str], Optional[tuple[int, int, int]]]:
    """
    Extract shift code and dominant color from a calendar cell.
    
    Returns:
        Tuple of (shift_code, dominant_rgb_color)
    """
    # Get dominant color from the cell (for color fallback)
    dominant_color = get_dominant_color(cell_image)
    
    # Run OCR to extract shift code
    # Use config for better text detection
    custom_config = r'--oem 3 --psm 6'
    cell_text = pytesseract.image_to_string(cell_image, config=custom_config)
    
    # Parse shift code from OCR text
    shift_code = parse_shift_code(cell_text)
    
    return shift_code, dominant_color


def parse_shift_code(text: str) -> Optional[str]:
    """
    Parse shift code from OCR text.
    
    The cell typically contains:
    - Day number (e.g., "01", "15")
    - Shift code (e.g., "E0M8", "N2111", "DO")
    - Time (e.g., "13:15:0...", "07:26:0...")
    """
    lines = text.strip().split("\n")
    
    # Known shift code patterns
    shift_patterns = [
        r"^([A-Z][A-Z0-9_]{1,5})$",  # E0M8, N2111, DO, RD, AL, etc.
        r"^([A-Z]{2,6})$",           # DO, RD, AL, MC, PH, HL, TD
        r"^(D[0O][A-Z0-9]{2,4})$",   # D0G8, D0G9, D0GG (handle O/0 confusion)
        r"^(E[0O]M\d)$",             # E0M8 (handle O/0 confusion)
        r"^(N\d{4})$",               # N2111
        r"^(TR_FD)$",                # TR_FD
        r"^(BOILU)$",                # BOILU
    ]
    
    for line in lines:
        line = line.strip().upper()
        
        # Skip empty lines and lines that look like times or dates
        # Handle day numbers with O/0 confusion (e.g., "01", "O1", "1", "31")
        if not line or re.match(r"^([O0o]?\d{1,2}|[O0o]\d?)$", line):  # Day number
            continue
        if re.match(r"^\d{2}:\d{2}", line):  # Time
            continue
        
        # Try to match shift patterns
        for pattern in shift_patterns:
            match = re.match(pattern, line)
            if match:
                code = match.group(1)
                # Normalize O/0 confusion
                code = normalize_shift_code(code)
                return code
        
        # If line looks like a shift code (letters and numbers, 2-6 chars)
        if re.match(r"^[A-Z0-9_]{2,6}$", line):
            return normalize_shift_code(line)
    
    return None


def normalize_shift_code(code: str) -> str:
    """
    Normalize shift code to handle common OCR errors.
    
    Common issues:
    - O/0 confusion (D0G8 vs DOG8)
    - I/1 confusion
    """
    # For codes starting with D followed by O or 0, normalize to D0
    if code.startswith("DO") and len(code) > 2:
        code = "D0" + code[2:]
    
    # For codes starting with E followed by O or 0, normalize to E0
    if code.startswith("EO") and len(code) > 2:
        code = "E0" + code[2:]
    
    return code


def get_dominant_color(image: Image.Image) -> tuple[int, int, int]:
    """
    Get the dominant color from an image region.
    
    Focuses on the colored shift box, ignoring white/near-white pixels.
    """
    # Resize for faster processing
    small_image = image.resize((50, 50))
    pixels = list(small_image.getdata())
    
    # Filter out white/near-white and black pixels
    colored_pixels = [
        p for p in pixels
        if isinstance(p, tuple) and len(p) >= 3
        and not (p[0] > 240 and p[1] > 240 and p[2] > 240)  # Not white
        and not (p[0] < 30 and p[1] < 30 and p[2] < 30)     # Not black
    ]
    
    if not colored_pixels:
        return (200, 200, 200)  # Default gray
    
    # Calculate average color
    avg_r = sum(p[0] for p in colored_pixels) // len(colored_pixels)
    avg_g = sum(p[1] for p in colored_pixels) // len(colored_pixels)
    avg_b = sum(p[2] for p in colored_pixels) // len(colored_pixels)
    
    return (avg_r, avg_g, avg_b)


def validate_image(image_data: bytes) -> tuple[bool, Optional[str]]:
    """
    Validate that the image is suitable for processing.
    """
    if len(image_data) < 1000:
        return False, "Image file is too small. Please send a clearer screenshot."
    
    if len(image_data) > 20 * 1024 * 1024:  # 20MB
        return False, "Image file is too large. Please compress the image."
    
    # Check for common image headers
    png_header = b'\x89PNG'
    jpeg_header = b'\xff\xd8\xff'
    
    if not (image_data[:4] == png_header or image_data[:3] == jpeg_header):
        return False, "Unsupported image format. Please send a PNG or JPEG."
    
    return True, None


def find_grid_top(image: Image.Image) -> Optional[int]:
    """
    Find the top of the schedule grid by locating the day names (Mon, Tue, etc).
    Returns the Y-coordinate of the bottom of the day headers.
    """
    # Crop top half of image to search for headers
    width, height = image.size
    search_area = image.crop((0, 0, width, int(height * 0.5)))
    
    try:
        data = pytesseract.image_to_data(search_area, output_type=Output.DICT)
        
        day_names = {"mon", "tue", "wed", "thu", "fri", "sat", "sun", 
                     "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"}
        
        found_bottoms = []
        
        n_boxes = len(data['text'])
        for i in range(n_boxes):
            text = data['text'][i].lower().strip()
            # Remove punctuation
            text = re.sub(r'[^\w\s]', '', text)
            
            if text in day_names:
                # Found a day name
                (x, y, w, h) = (data['left'][i], data['top'][i], data['width'][i], data['height'][i])
                found_bottoms.append(y + h)
        
        if found_bottoms:
            # Return the average bottom + some padding
            avg_bottom = sum(found_bottoms) // len(found_bottoms)
            padding = int(height * 0.01)  # 1% padding
            return avg_bottom + padding
            
    except Exception as e:
        logger.error(f"Error finding grid top: {e}")
    
    return None
