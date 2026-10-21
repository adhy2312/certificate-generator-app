import os
import re
import time
import uuid
import logging
from PIL import Image, ImageDraw, ImageFont
import config
from datetime import date

logger = logging.getLogger(__name__)

# Cache to prevent memory leaks and speed up bulk processing
_font_cache = {}
_template_cache = {}

def _get_cached_template(template_path: str) -> Image.Image:
    mtime = os.path.getmtime(template_path)
    if template_path in _template_cache:
        cached_mtime, cached_img = _template_cache[template_path]
        if cached_mtime == mtime:
            return cached_img.copy()
            
    with Image.open(template_path) as raw_img:
        img = raw_img.convert("RGB")
        _template_cache[template_path] = (mtime, img)
        return img.copy()

def _get_font(font_path: str, size: int) -> ImageFont.ImageFont:
    key = (font_path, size)
    if key not in _font_cache:
        try:
            _font_cache[key] = ImageFont.truetype(font_path, size)
        except Exception:
            _font_cache[key] = ImageFont.load_default()
    return _font_cache[key]

def _get_fitted_font(font_path: str, initial_size: int, text: str, max_width: float, draw: ImageDraw.ImageDraw, min_scale: float = 0.5) -> ImageFont.ImageFont:
    """Dynamically scales down font size if text overflows max_width to prevent canvas clipping."""
    if not text:
        return _get_font(font_path, initial_size)
    
    current_size = initial_size
    min_size = max(12, int(initial_size * min_scale))
    font = _get_font(font_path, current_size)
    
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        while text_width > max_width and current_size > min_size:
            current_size -= 2
            font = _get_font(font_path, current_size)
            bbox = draw.textbbox((0, 0), text, font=font)
            text_width = bbox[2] - bbox[0]
    except Exception as e:
        logger.warning(f"Error fitting font: {e}")
        
    return font

def generate_pdf_from_svg(name: str, event_name: str, role: str, cert_date: str = None, cert_id: str = None, cert_type: str = "Certificate of Participation") -> str:
    """
    Handles dynamic certificate generation using Pillow to stamp text over a PNG template.
    Outputs a production-grade PDF directly.
    Features:
      - Dynamic font auto-scaling to prevent long student names or event titles from clipping
      - Windows MAX_PATH (260 char) limit prevention and safe filename sanitization
      - In-memory template and font caching for ultra-fast bulk dispatch
    """
    try:
        # Normalize legacy constant CERT_Template to clean Certificate of Participation
        if cert_type == "CERT_Template":
            cert_type = "Certificate of Participation"

        # Load the base PNG template
        filename_map = {
            "Certificate of Participation": "CERT TEMPLATE.png",
            "Certificate of Appreciation": "Certificate Of  Appreciation.png",
            "Certificate of Recognition": "Certificate Of  Recognition.png",
            "Certificate of Volunteering": "Certificate Of  Volunteering.png",
        }
        
        if cert_type.startswith("Certificate of Merit"):
            filename = "Certificate Of  Merit.png"
        else:
            filename = filename_map.get(cert_type, "CERT TEMPLATE.png")
            
        # Search multiple directories for template files
        search_dirs = [
            os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")),
            os.path.abspath(os.path.join(os.path.dirname(__file__), "..")),
            os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "templates")),
            os.getcwd()
        ]
        template_path = None
        for sdir in search_dirs:
            candidate = os.path.join(sdir, filename)
            if os.path.exists(candidate):
                template_path = candidate
                break
        
        if not template_path:
            # Try case-insensitive matching in search dirs
            for sdir in search_dirs:
                if os.path.exists(sdir):
                    for f in os.listdir(sdir):
                        if f.lower() == filename.lower() or f.lower().replace("  ", " ") == filename.lower().replace("  ", " "):
                            template_path = os.path.join(sdir, f)
                            break
                if template_path:
                    break
                    
        if not template_path:
            raise FileNotFoundError(f"Template not found for '{cert_type}' (looked for '{filename}')")
            
        img = _get_cached_template(template_path)

        draw = ImageDraw.Draw(img)
        width, height = img.size
        
        # Setup fonts path
        font_dir = os.path.join(os.path.dirname(__file__), "..", "fonts")
        georgia_bold_path = os.path.join(font_dir, "georgiab.ttf")
        georgia_reg_path = os.path.join(font_dir, "georgia.ttf")

        base_font_size = int(height * 0.039)
        large_size = int(base_font_size * 1.4)

        # Coordinates
        coords = config.CERT_COORDS.get(filename, config.CERT_COORDS["DEFAULT"])
        
        name_x = width * config.COORD_X
        name_y = height * coords["name_y"]
        
        event_x = width * config.COORD_X
        event_y = height * coords["event_y"]
        
        date_x = width * config.COORD_X
        date_y = height * coords["date_y"]
        
        # Clean up text inputs: strip control characters and normalize
        clean_name = re.sub(r'[\r\n\t]+', ' ', name or '').strip().title()
        clean_event = re.sub(r'[\r\n\t]+', ' ', event_name or '').strip()

        # Dynamic Auto-Scaling Fonts (prevent overflow)
        font_large = _get_fitted_font(georgia_bold_path, large_size, clean_name, width * 0.78, draw)
        font_medium = _get_fitted_font(georgia_reg_path, base_font_size, clean_event, width * 0.82, draw)
        font_date = _get_font(georgia_reg_path, base_font_size)

        # Draw Text
        # We use anchor="mm" to perfectly center the text horizontally and vertically
        draw.text((name_x, name_y), clean_name, fill="black", font=font_large, anchor="mm")
        draw.text((event_x, event_y), clean_event, fill="#333333", font=font_medium, anchor="mm")
        
        # Print Prize if it's a Merit certificate
        if cert_type.startswith("Certificate of Merit"):
            prize_text = cert_type.split("-", 1)[1].strip() if "-" in cert_type else "1st Prize"
            prize_x = width * coords.get("prize_x", config.COORD_X)
            prize_y = height * coords.get("prize_y", 0.54)
            font_prize = _get_fitted_font(georgia_bold_path, base_font_size, prize_text, width * 0.5, draw)
            draw.text((prize_x, prize_y), prize_text, fill="black", font=font_prize, anchor="mm")
        
        display_date = cert_date if cert_date else date.today().strftime('%B %d, %Y')
        draw.text((date_x, date_y), display_date, fill="#555555", font=font_date, anchor="mm")

        # Sanitize filename cleanly - truncate prefix to 35 chars to prevent Windows MAX_PATH (260 char) overflow and path traversal
        clean_file_prefix = re.sub(r'[^a-zA-Z0-9_\-]', '_', clean_name)[:35].strip('_')
        if not clean_file_prefix:
            clean_file_prefix = "cert"
        short_id = (cert_id or uuid.uuid4().hex)[:8]
        output_filename = os.path.join(config.OUTPUT_DIR, f"{clean_file_prefix}_{short_id}.pdf")
        
        # Save directly to PDF
        ts_save = time.time()
        img.save(output_filename, "PDF", resolution=100.0)
        logger.debug(f"Image saved to PDF in {time.time() - ts_save:.2f}s: {output_filename}")

        # Explicitly free memory of PIL image
        img.close()

        return output_filename
            
    except Exception as e:
        logger.error(f"Certificate generation error for '{name}': {e}")
        raise RuntimeError(f"Certificate generation error: {e}")
