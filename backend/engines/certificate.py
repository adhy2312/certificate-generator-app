import os
import re
import time
import logging
import qrcode
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

def generate_pdf_from_svg(name: str, event_name: str, role: str, cert_date: str = None, cert_id: str = None, cert_type: str = "Certificate of Participation") -> str:
    """
    Handles dynamic certificate generation using Pillow to stamp text over a PNG template.
    Outputs a production-grade PDF directly.
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
            raise FileNotFoundError(f"Template not found for '{cert_type}' (looked for '{filename}' in {search_dirs})")
            
        img = _get_cached_template(template_path)

        draw = ImageDraw.Draw(img)
        width, height = img.size
        
        # Setup fonts - adjust text size to be compact and elegant
        base_font_size = int(height * 0.039) # 3.9% of height (tweaked slightly larger)
        
        if base_font_size not in _font_cache:
            try:
                # Load bundled Georgia fonts from the backend/fonts directory
                font_dir = os.path.join(os.path.dirname(__file__), "..", "fonts")
                _font_cache[base_font_size] = {
                    "large": ImageFont.truetype(os.path.join(font_dir, "georgiab.ttf"), int(base_font_size * 1.4)),
                    "medium": ImageFont.truetype(os.path.join(font_dir, "georgia.ttf"), base_font_size)
                }
            except IOError:
                logger.warning("Could not load professional fonts. Using default.")
                _font_cache[base_font_size] = {
                    "large": ImageFont.load_default(),
                    "medium": ImageFont.load_default()
                }
        font_large = _font_cache[base_font_size]["large"]
        font_medium = _font_cache[base_font_size]["medium"]

        # Coordinates
        coords = config.CERT_COORDS.get(filename, config.CERT_COORDS["DEFAULT"])
        
        name_x = width * config.COORD_X
        name_y = height * coords["name_y"]
        
        event_x = width * config.COORD_X
        event_y = height * coords["event_y"]
        
        date_x = width * config.COORD_X
        date_y = height * coords["date_y"]
        
        # Clean up recipient name to proper Title Case
        clean_name = name.strip().title() if name else ""

        # Draw Text
        # We use anchor="mm" to perfectly center the text horizontally and vertically
        draw.text((name_x, name_y), clean_name, fill="black", font=font_large, anchor="mm")
        draw.text((event_x, event_y), event_name, fill="#333333", font=font_medium, anchor="mm")
        
        # Print Prize if it's a Merit certificate
        if cert_type.startswith("Certificate of Merit"):
            prize_text = cert_type.split("-", 1)[1].strip() if "-" in cert_type else "1st Prize"
            prize_x = width * coords.get("prize_x", config.COORD_X)
            prize_y = height * coords.get("prize_y", 0.54)
            draw.text((prize_x, prize_y), prize_text, fill="black", font=font_medium, anchor="mm")
        
        display_date = cert_date if cert_date else date.today().strftime('%B %d, %Y')
        draw.text((date_x, date_y), display_date, fill="#555555", font=font_medium, anchor="mm")
        
        # Generate and Stamp QR Code
        if cert_id:
            qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=20, border=2)
            qr.add_data(f"{config.PUBLIC_URL}/verify/{cert_id}")
            qr.make(fit=True)
            qr_img = qr.make_image(fill_color="#0c2340", back_color="white").convert("RGB")
            
            # Resize QR code to fit roughly 8% of the certificate width
            qr_size = int(width * 0.08)
            qr_img_resized = qr_img.resize((qr_size, qr_size), Image.Resampling.LANCZOS)
            
            qr_x = int(width * config.QR_X) - (qr_size // 2)
            qr_y = int(height * coords["qr_y"]) - (qr_size // 2)
            
            # Paste QR code onto main image
            img.paste(qr_img_resized, (qr_x, qr_y))
            
            qr_img_resized.close()
            try:
                qr_img.close()
            except AttributeError:
                pass

        # Sanitize filename cleanly
        safe_name = re.sub(r'[\\/*?:"<>|]', "", name).replace(" ", "_")
        output_filename = os.path.join(config.OUTPUT_DIR, f"{safe_name}_{cert_id or 'cert'}.pdf")
        
        # Save directly to PDF
        ts_save = time.time()
        img.save(output_filename, "PDF", resolution=100.0)
        logger.debug(f"Image saved to PDF in {time.time() - ts_save:.2f}s: {output_filename}")

        # Explicitly free memory of PIL image
        img.close()

        return output_filename
            
    except Exception as e:
        logger.error(f"Certificate generation error for {name}: {e}")
        return ""
