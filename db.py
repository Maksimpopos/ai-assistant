from sqlalchemy import (
    create_engine, Column, Integer, String, ForeignKey,
    DateTime, Text, Float
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from datetime import datetime
import os

# ── Настройки подключения ─────────────────────────────────────────────
# Рекоммендую хранить в переменных окружения, но можно и захардкодить.
MYSQL_USER = os.getenv("MYSQL_USER", "maksim")
MYSQL_PASS = os.getenv("MYSQL_PASS", "1234")
MYSQL_HOST = os.getenv("MYSQL_HOST", "127.0.0.1")
MYSQL_PORT = os.getenv("MYSQL_PORT", "3306")
MYSQL_DB   = os.getenv("MYSQL_DB",   "assistant_mysql")

DB_URL = f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASS}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DB}?charset=utf8mb4"

# ── Движок/сессия ─────────────────────────────────────────────────────
engine = create_engine(
    DB_URL,
    future=True,
    pool_pre_ping=True,       # стабильные коннекты
    echo=False                # поставь True для отладки
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()

# ── Модели ────────────────────────────────────────────────────────────
class Customer(Base):
    __tablename__ = "customers"
    id    = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    name  = Column(String(255))

class Order(Base):
    __tablename__ = "orders"
    id              = Column(Integer, primary_key=True)
    customer_id     = Column(Integer, ForeignKey("customers.id"), index=True, nullable=True)
    external_order_no = Column(String(100), unique=True, index=True, nullable=False)
    status          = Column(String(50), index=True, default="processing")
    created_at      = Column(DateTime, default=datetime.utcnow, nullable=False)
    customer        = relationship("Customer", backref="orders")

class OrderItem(Base):
    __tablename__ = "order_items"
    id       = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id"), index=True, nullable=False)
    sku      = Column(String(100), index=True)
    title    = Column(Text)
    qty      = Column(Float)
    price    = Column(Float)

class Shipment(Base):
    __tablename__ = "shipments"
    id         = Column(Integer, primary_key=True)
    order_id   = Column(Integer, ForeignKey("orders.id"), index=True, nullable=False)
    carrier    = Column(String(100))
    tracking_no= Column(String(100), index=True)
    last_event = Column(Text)
    eta_date   = Column(String(50))

