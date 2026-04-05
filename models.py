"""
Nebula Enterprise - SQLAlchemy ORM Modelleri
Tablolar: categories, brands, products, price_history
"""
from sqlalchemy import (
    Column, Integer, String, Float, ForeignKey,
    JSON, DateTime, Text, Boolean, Index
)
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base


class Category(Base):
    __tablename__ = "categories"
    __table_args__ = (
        Index("ix_categories_slug", "slug", unique=True),
        Index("ix_categories_name", "name"),
    )

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    slug = Column(String(255), nullable=False)
    url = Column(String(512), nullable=True)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    products = relationship("Product", back_populates="category", lazy="select")

    def __repr__(self) -> str:
        return f"<Category(id={self.id}, name='{self.name}')>"


class Brand(Base):
    __tablename__ = "brands"
    __table_args__ = (
        Index("ix_brands_name", "name", unique=True),
    )

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    logo_url = Column(String(512), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    products = relationship("Product", back_populates="brand", lazy="select")

    def __repr__(self) -> str:
        return f"<Brand(id={self.id}, name='{self.name}')>"


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        Index("ix_products_url", "url", unique=True),
        Index("ix_products_name", "name"),
        Index("ix_products_category_id", "category_id"),
        Index("ix_products_brand_id", "brand_id"),
        Index("ix_products_price", "price"),
    )

    id = Column(Integer, primary_key=True)
    name = Column(String(512), nullable=False)
    url = Column(String(512), nullable=False)
    price = Column(Float, nullable=True)
    old_price = Column(Float, nullable=True)
    image_url = Column(String(512), nullable=True)
    description = Column(Text, nullable=True)
    specs = Column(JSON, nullable=True)         # {"ram": "16GB", "storage": "512GB", ...}
    in_stock = Column(Boolean, default=True, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    category_id = Column(Integer, ForeignKey("categories.id", ondelete="SET NULL"), nullable=True)
    brand_id = Column(Integer, ForeignKey("brands.id", ondelete="SET NULL"), nullable=True)

    category = relationship("Category", back_populates="products")
    brand = relationship("Brand", back_populates="products")
    price_history = relationship(
        "PriceHistory",
        back_populates="product",
        cascade="all, delete-orphan",
        lazy="select",
    )

    def __repr__(self) -> str:
        return f"<Product(id={self.id}, name='{self.name[:40]}', price={self.price})>"


class PriceHistory(Base):
    __tablename__ = "price_history"
    __table_args__ = (
        Index("ix_price_history_product_id", "product_id"),
        Index("ix_price_history_recorded_at", "recorded_at"),
    )

    id = Column(Integer, primary_key=True)
    product_id = Column(
        Integer,
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
    )
    price = Column(Float, nullable=False)
    recorded_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    source = Column(String(100), default="akakce", nullable=False)

    product = relationship("Product", back_populates="price_history")

    def __repr__(self) -> str:
        return f"<PriceHistory(product_id={self.product_id}, price={self.price}, at={self.recorded_at})>"
