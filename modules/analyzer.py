"""
Nebula - Analiz ve Raporlama Modülü
Gerçek Pandas veri işleme ve Excel/CSV çıktısı
"""
import pandas as pd
import os
from datetime import datetime
import logging

logger = logging.getLogger("nebula.modules.analyzer")

REPORTS_DIR = os.path.join(os.path.dirname(__file__), "..", "outputs", "reports")


class Analyzer:
    """Ürün verilerini analiz eder ve raporlar oluşturur."""

    def __init__(self):
        os.makedirs(REPORTS_DIR, exist_ok=True)

    def process_data(self, data: list[dict]) -> pd.DataFrame:
        """Veriyi DataFrame'e çevirir, temizler ve döndürür."""
        if not data:
            logger.warning("İşlenecek veri yok")
            return pd.DataFrame()

        df = pd.DataFrame(data)

        # Fiyat sütunu varsa temizle
        if "price" in df.columns:
            df["price"] = pd.to_numeric(df["price"], errors="coerce")
            df = df.dropna(subset=["price"])
            df = df[df["price"] > 0]

        # İsim varsa temizle
        if "name" in df.columns or "item" in df.columns:
            col = "name" if "name" in df.columns else "item"
            df[col] = df[col].str.strip()
            df = df[df[col].notna() & (df[col] != "")]

        # İstatistik
        if "price" in df.columns and not df.empty:
            logger.info(
                f"Analiz sonucu: {len(df)} ürün | "
                f"Min: {df['price'].min():.2f} TL | "
                f"Max: {df['price'].max():.2f} TL | "
                f"Ort: {df['price'].mean():.2f} TL"
            )

        return df

    def save_report(self, df: pd.DataFrame, prefix: str = "rapor") -> str:
        """DataFrame'i tarih damgalı CSV olarak kaydeder."""
        if df.empty:
            logger.warning("Kaydedilecek veri yok")
            return ""

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{prefix}_{timestamp}.csv"
        filepath = os.path.join(REPORTS_DIR, filename)

        # utf-8-sig: Excel'in Türkçe karakterleri doğru okuması için
        df.to_csv(filepath, index=False, encoding="utf-8-sig")
        logger.info(f"Rapor kaydedildi: {filepath}")
        return filepath

    def get_top_cheapest(self, df: pd.DataFrame, n: int = 10) -> pd.DataFrame:
        """En ucuz n ürünü döndürür."""
        if df.empty or "price" not in df.columns:
            return pd.DataFrame()
        return df.nsmallest(n, "price").reset_index(drop=True)

    def get_price_stats(self, df: pd.DataFrame) -> dict:
        """Fiyat istatistiklerini döndürür."""
        if df.empty or "price" not in df.columns:
            return {}
        return {
            "count": int(df["price"].count()),
            "min": float(df["price"].min()),
            "max": float(df["price"].max()),
            "mean": float(df["price"].mean()),
            "median": float(df["price"].median()),
        }
