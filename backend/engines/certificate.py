import os
import re
import logging
import qrcode
from PIL import Image, ImageDraw, ImageFont
import config
from datetime import date

logger = logging.getLogger(__name__)

def generate_pdf_from_svg(name: str, event_name: str, role: str, cert_date: str = None, cert_id: str = None) -> str:
    """
    Handles dynamic certificate generation using Pillow to stamp text over a PNG template.
    Outputs a production-grade PDF directly.
    """
    try:
        # Load the base PNG template
        template_path = os.path.join(os.path.dirname(__file__), "..", "..", "CERT TEMPLATE.png")
        template_path = os.path.abspath(template_path)
        
        if not os.path.exists(template_path):
            raise FileNotFoundError(f"Template not found: {template_path}")
            
        with Image.open(template_path) as img:
            # We want to work in RGB for saving to PDF
            img = img.convert("RGB")
            draw = ImageDraw.Draw(img)
            width, height = img.size
            
            # Setup fonts - drastically increase text size for the massive 10K resolution PNG
            base_font_size = int(height * 0.045) # 4.5% of height
            
            try:
                # Load bundled Georgia fonts from the backend/fonts directory
                font_dir = os.path.join(os.path.dirname(__file__), "..", "fonts")
                font_large = ImageFont.truetype(os.path.join(font_dir, "georgiab.ttf"), int(base_font_size * 1.6))
                font_medium = ImageFont.truetype(os.path.join(font_dir, "georgia.ttf"), base_font_size)
            except IOError:
                logger.warning("Could not load professional fonts. Using default.")
                font_large = ImageFont.load_default()
                font_medium = ImageFont.load_default()

            # Coordinates
            name_x = width * config.COORD_NAME_X
            name_y = height * config.COORD_NAME_Y
            
            event_x = width * config.COORD_EVENT_X
            event_y = height * config.COORD_EVENT_Y
            
            date_x = width * config.COORD_DATE_X
            date_y = height * config.COORD_DATE_Y
            
            # Draw Text
            # We use anchor="mm" to perfectly center the text horizontally and vertically at the coordinate
            draw.text((name_x, name_y), name, fill="black", font=font_large, anchor="mm")
            draw.text((event_x, event_y), event_name, fill="#333333", font=font_medium, anchor="mm")
            
            display_date = cert_date if cert_date else date.today().strftime('%B %d, %Y')
            draw.text((date_x, date_y), display_date, fill="#555555", font=font_medium, anchor="mm")
            
            # Generate and Stamp QR Code
            if cert_id:
                qr = qrcode.QRCode(box_size=20, border=2)
                qr.add_data(f"{config.PUBLIC_URL}/verify/{cert_id}")
                qr.make(fit=True)
                try:
                    from qrcode.image.styledpil import StyledPilImage
                    from qrcode.image.styles.moduledrawers.pil import RoundedModuleDrawer
                    from qrcode.image.styles.colormasks import SolidFillColorMask
                    qr_img = qr.make_image(
                        image_factory=StyledPilImage,
                        module_drawer=RoundedModuleDrawer(),
                        color_mask=SolidFillColorMask(front_color=(12, 35, 64)) # Deep elegant indigo
                    )
                except ImportError:
                    qr_img = qr.make_image(fill_color="#0c2340", back_color="white")
                
                # Resize QR code to fit roughly 8% of the certificate width
                qr_size = int(width * 0.08)
                qr_img = qr_img.resize((qr_size, qr_size), Image.Resampling.LANCZOS)
                
                qr_x = int(width * config.COORD_QR_X) - (qr_size // 2)
                qr_y = int(height * config.COORD_QR_Y) - (qr_size // 2)
                
                # Paste QR code onto main image
                img.paste(qr_img, (qr_x, qr_y))

            # Sanitize filename cleanly
            safe_name = re.sub(r'[\\/*?:"<>|]', "", name).replace(" ", "_")
            output_filename = os.path.join(config.OUTPUT_DIR, f"{safe_name}_{cert_id or 'cert'}.pdf")
            
            # Save directly to PDF
            # Downscaling to save disk space without losing quality for printing (e.g., 2000px width)
            target_width = 2400
            scale_factor = target_width / width
            target_height = int(height * scale_factor)
            
            img_resized = img.resize((target_width, target_height), Image.Resampling.LANCZOS)
            img_resized.save(output_filename, "PDF", resolution=100.0)

            return output_filename
            
    except Exception as e:
        logger.error(f"Certificate generation error for {name}: {e}")
        return ""
