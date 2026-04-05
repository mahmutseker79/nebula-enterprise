"""
Nebula - WebP Dönüştürücü Modülü
Pillow ile PNG/JPG → WebP dönüşümü
"""
import os
from PIL import Image
import logging

logger = logging.getLogger("nebula.modules.webp")

IMAGES_DIR = os.path.join(os.path.dirname(__file__), "..", "images")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "outputs", "webp_images")

SUPPORTED_FORMATS = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".gif"}


class WebPConverter:
    """Resimleri WebP formatına dönüştürür."""

    def __init__(self, input_folder: str = IMAGES_DIR, output_folder: str = OUTPUT_DIR):
        self.input_folder = input_folder
        self.output_folder = output_folder
        os.makedirs(self.output_folder, exist_ok=True)

    def convert_all(self, quality: int = 85) -> dict:
        """input_folder'daki tüm uygun resimleri WebP'ye dönüştürür."""
        results = {"success": [], "failed": [], "skipped": []}

        if not os.path.isdir(self.input_folder):
            logger.error(f"Input klasörü bulunamadı: {self.input_folder}")
            return results

        files = [
            f for f in os.listdir(self.input_folder)
            if os.path.splitext(f)[1].lower() in SUPPORTED_FORMATS
        ]

        if not files:
            logger.info("Dönüştürülecek resim bulunamadı")
            return results

        logger.info(f"{len(files)} resim dönüştürülüyor...")

        for filename in files:
            src_path = os.path.join(self.input_folder, filename)
            stem = os.path.splitext(filename)[0]
            out_path = os.path.join(self.output_folder, f"{stem}.webp")

            if os.path.exists(out_path):
                results["skipped"].append(filename)
                continue

            try:
                with Image.open(src_path) as img:
                    # RGBA → RGB dönüşümü (JPEG uyumu için)
                    if img.mode in ("RGBA", "P"):
                        img = img.convert("RGB")
                    img.save(out_path, "WEBP", quality=quality, optimize=True)
                results["success"].append(filename)
                logger.debug(f"OK: {filename} → {stem}.webp")

            except Exception as exc:
                results["failed"].append(filename)
                logger.error(f"HATA: {filename} | {exc}")

        logger.info(
            f"Dönüşüm tamamlandı: "
            f"{len(results['success'])} başarılı, "
            f"{len(results['failed'])} hatalı, "
            f"{len(results['skipped'])} atlandı"
        )
        return results

    def convert_single(self, src_path: str, quality: int = 85) -> str:
        """Tek bir resmi WebP'ye dönüştürür, çıktı yolunu döndürür."""
        stem = os.path.splitext(os.path.basename(src_path))[0]
        out_path = os.path.join(self.output_folder, f"{stem}.webp")
        try:
            with Image.open(src_path) as img:
                if img.mode in ("RGBA", "P"):
                    img = img.convert("RGB")
                img.save(out_path, "WEBP", quality=quality)
            return out_path
        except Exception as exc:
            logger.error(f"Dönüşüm hatası: {exc}")
            return ""
