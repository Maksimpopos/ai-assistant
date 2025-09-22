from sqlalchemy import (create_engine, Column, Integer, String, ForeignKey,
                        DateTime, Text, Float)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from datetime import datetime
import os

# путь до базы (в папке data)
DB_PATH = os.path.join(os.path.dirname(__file__), "data", "orders.db")

# движок SQLite
engine = create_engine(f"sqlite:///{DB_PATH}", future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()

class Customer(Base):
    __tablename__ = "customers"
    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, index=True, nullable=False)
    name  = Column(String)

class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), index=True)
    external_order_no = Column(String, unique=True, index=True)
    status = Column(String, index=True, default="processing")
    created_at = Column(DateTime, default=datetime.utcnow)
    customer = relationship("Customer", backref="orders")

class OrderItem(Base):
    __tablename__ = "order_items"
    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id"), index=True)
    sku = Column(String, index=True)
    title = Column(Text)
    qty = Column(Float)
    price = Column(Float)

class Shipment(Base):
    __tablename__ = "shipments"
    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id"), index=True)
    carrier = Column(String)
    tracking_no = Column(String, index=True)
    last_event = Column(Text)
    eta_date = Column(String)
