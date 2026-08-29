import os
import re
import logging
import qrcode
from PIL import Image, ImageDraw, ImageFont
import config
from datetime import date

logger = logging.getLogger(__name__)

# Cache to prevent memory leaks and speed up bulk processing
_font_cache = {}

def generate_pdf_from_svg(name: str, event_name: str, role: str, cert_date: str = None, cert_id: str = None, cert_type: str = "CERT_Template") -> str:
    """
    Handles dynamic certificate generation using Pillow to stamp text over a PNG template.
    Outputs a production-grade PDF directly.
    """
    try:
        # Load the base PNG template
        filename_map = {
            "CERT_Template": "CERT TEMPLATE.png",
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
            
        with Image.open(template_path) as raw_img:
            # Downsample ultra high-res templates immediately to max 2800px width to prevent OOM on 512MB RAM servers
            if raw_img.width > 2800:
                target_w = 2800
                target_h = int(raw_img.height * (2800 / raw_img.width))
                img = raw_img.resize((target_w, target_h), Image.Resampling.LANCZOS).convert("RGB")
            else:
                img = raw_img.convert("RGB")

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
            
            # Draw Text
            # We use anchor="mm" to perfectly center the text horizontally and vertically
            draw.text((name_x, name_y), name, fill="black", font=font_large, anchor="mm")
            draw.text((event_x, event_y), event_name, fill="#333333", font=font_medium, anchor="mm")
            
            # Print Prize if it's a Merit certificate
            logger.debug(f"cert_type: '{cert_type}'")
            
            if cert_type.startswith("Certificate of Merit"):
                prize_text = cert_type.split("-", 1)[1].strip() if "-" in cert_type else "1st Prize"
                prize_x = width * coords.get("prize_x", config.COORD_X)
                prize_y = height * coords.get("prize_y", 0.54)
                
                logger.debug(f"Drawing prize: '{prize_text}' at ({prize_x}, {prize_y})")
                    
                # Drawing prize compactly to avoid overflowing over the surrounding text
                draw.text((prize_x, prize_y), prize_text, fill="black", font=font_medium, anchor="mm")
            
            display_date = cert_date if cert_date else date.today().strftime('%B %d, %Y')
            draw.text((date_x, date_y), display_date, fill="#555555", font=font_medium, anchor="mm")
            
            # Generate and Stamp QR Code
            if cert_id:
                qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=20, border=2)
                qr.add_data(f"{config.PUBLIC_URL}/verify/{cert_id}")
                qr.make(fit=True)
                try:
                    from qrcode.image.styledpil import StyledPilImage
                    from qrcode.image.styles.moduledrawers.pil import RoundedModuleDrawer
                    from qrcode.image.styles.colormasks import SolidFillColorMask
                    logo_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "public", "logo.png"))
                    qr_img = qr.make_image(
                        image_factory=StyledPilImage,
                        module_drawer=RoundedModuleDrawer(),
                        color_mask=SolidFillColorMask(front_color=(12, 35, 64)), # Deep elegant indigo
                        embeded_image_path=logo_path if os.path.exists(logo_path) else None
                    )
                except Exception as qr_err:
                    logger.warning(f"Styled QR generation fallback due to: {qr_err}")
                    qr_img = qr.make_image(fill_color="#0c2340", back_color="white")
                
                # Resize QR code to fit roughly 8% of the certificate width
                qr_size = int(width * 0.08)
                qr_img_resized = qr_img.resize((qr_size, qr_size), Image.Resampling.LANCZOS)
                
                qr_x = int(width * config.QR_X) - (qr_size // 2)
                qr_y = int(height * coords["qr_y"]) - (qr_size // 2)
                
                # Paste QR code onto main image
                img.paste(qr_img_resized, (qr_x, qr_y))
                
                # Free QR image memory
                qr_img_resized.close()
                try:
                    qr_img.close()  # qrcode image objects may not have .close() on older versions
                except AttributeError:
                    pass

            # Sanitize filename cleanly
            safe_name = re.sub(r'[\\/*?:"<>|]', "", name).replace(" ", "_")
            output_filename = os.path.join(config.OUTPUT_DIR, f"{safe_name}_{cert_id or 'cert'}.pdf")
            
            # Save directly to PDF
            img.save(output_filename, "PDF", resolution=100.0)

            # Explicitly free memory of PIL image
            img.close()

            return output_filename
            
    except Exception as e:
        logger.error(f"Certificate generation error for {name}: {e}")
        return ""
