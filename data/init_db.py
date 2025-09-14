import os
from db import Base, engine, SessionLocal, Customer, Order, OrderItem, Shipment
from datetime import datetime

# создаём папку data если её нет
os.makedirs("data", exist_ok=True)

# создаём таблицы
Base.metadata.create_all(bind=engine)

# открываем сессию
db = SessionLocal()

# создаём тестового клиента
cust = Customer(email="ivan@test.com", name="Иван Петров")
db.add(cust)
db.commit()
db.refresh(cust)

# создаём заказ
order = Order(
    customer_id=cust.id,
    external_order_no="12345",
    status="shipped",
    created_at=datetime(2025, 9, 10, 14, 30)
)
db.add(order)
db.commit()
db.refresh(order)

# добавляем товары
item1 = OrderItem(order_id=order.id, sku="PC001", title="Игровой ПК Ryzen", qty=1, price=1200)
item2 = OrderItem(order_id=order.id, sku="KB001", title="Клавиатура Redragon", qty=1, price=50)
db.add_all([item1, item2])
db.commit()

# добавляем доставку
ship = Shipment(
    order_id=order.id,
    carrier="DHL",
    tracking_no="JD014569845DE",
    last_event="Прибыло в регион доставки",
    eta_date="2025-09-15"
)
db.add(ship)
db.commit()

print("✅ База данных создана и заполнена тестовыми данными!")
