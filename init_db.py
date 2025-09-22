import os
from db import Base, engine, SessionLocal, Customer, Order, OrderItem, Shipment
from datetime import datetime

# создаём папку data если её нет
os.makedirs("data", exist_ok=True)

# создаём таблицы
Base.metadata.create_all(bind=engine)

# открываем сессию
db = SessionLocal()

orders_data = [
    {
        "cust": {"email": "iva555555n@test.com", "name": "Иван Петров"},
        "order": {"external_order_no": "12345", "status": "shipped", "created_at": datetime(2025, 9, 10, 14, 30)},
        "items": [
            {"sku": "PC001", "title": "Игровой ПК Ryzen", "qty": 1, "price": 1200},
            {"sku": "KB001", "title": "Клавиатура Redragon", "qty": 1, "price": 50},
        ],
        "shipment": {"carrier": "DHL", "tracking_no": "JD014569845DE", "last_event": "Прибыло в регион доставки", "eta_date": "2025-09-15"},
    },
    {
        "cust": {"email": "maria@test.com", "name": "Мария Сидорова"},
        "order": {"external_order_no": "12346", "status": "processing", "created_at": datetime(2025, 9, 11, 9, 15)},
        "items": [
            {"sku": "NB001", "title": "Ноутбук ASUS", "qty": 1, "price": 800},
            {"sku": "MS001", "title": "Мышь Logitech", "qty": 1, "price": 40},
        ],
        "shipment": {"carrier": "UPS", "tracking_no": "1Z999AA10123456784", "last_event": "В пути в страну назначения", "eta_date": "2025-09-17"},
    },
    {
        "cust": {"email": "john@test.com", "name": "John Doe"},
        "order": {"external_order_no": "12347", "status": "delivered", "created_at": datetime(2025, 9, 9, 18, 45)},
        "items": [
            {"sku": "MB001", "title": "Монитор LG 27\"", "qty": 2, "price": 300},
        ],
        "shipment": {"carrier": "FedEx", "tracking_no": "FE123456789US", "last_event": "Доставлено", "eta_date": "2025-09-12"},
    },
    {
        "cust": {"email": "sarah@test.com", "name": "Sarah Connor"},
        "order": {"external_order_no": "12348", "status": "cancelled", "created_at": datetime(2025, 9, 8, 10, 0)},
        "items": [
            {"sku": "PR001", "title": "Принтер HP", "qty": 1, "price": 150},
            {"sku": "CR001", "title": "Картридж HP", "qty": 2, "price": 40},
        ],
        "shipment": {"carrier": "Hermes", "tracking_no": "HRM654987321", "last_event": "Заказ отменён", "eta_date": "2025-09-09"},
    },
    {
        "cust": {"email": "grossalina04@gmail.com", "name": "Alina Savchenko"},
        "order": {"external_order_no": "10102025", "status": "processing", "created_at": datetime(2025, 9, 12, 16, 20)},
        "items": [
            {"sku": "SRV001", "title": "Сервер Dell PowerEdge", "qty": 1, "price": 2500},
            {"sku": "RAM001", "title": "EheRing", "qty": 2, "price": 120},
        ],
        "shipment": {"carrier": "DHL", "tracking_no": "JD098765432DE", "last_event": "Отправлено со склада", "eta_date": "2025-10-09"},
    },
]

for data in orders_data:
    cust = Customer(**data["cust"])
    db.add(cust)
    db.commit()
    db.refresh(cust)

    order = Order(customer_id=cust.id, **data["order"])
    db.add(order)
    db.commit()
    db.refresh(order)

    items = [OrderItem(order_id=order.id, **item) for item in data["items"]]
    db.add_all(items)
    db.commit()

    ship = Shipment(order_id=order.id, **data["shipment"])
    db.add(ship)
    db.commit()

print("✅ База данных создана и заполнена 5 тестовыми заказами!")
