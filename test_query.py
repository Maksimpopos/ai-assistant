from db import SessionLocal, Customer, Order, OrderItem, Shipment
from sqlalchemy import select

def main():
    session = SessionLocal()

    # 1. Проверим клиентов
    print("=== Customers ===")
    customers = session.execute(select(Customer)).scalars().all()
    for c in customers:
        print(f"ID={c.id}, Email={c.email}, Name={c.name}")

    # 2. Проверим заказы
    print("\n=== Orders ===")
    orders = session.execute(select(Order)).scalars().all()
    for o in orders:
        print(f"OrderNo={o.external_order_no}, Status={o.status}, CustomerID={o.customer_id}, Date={o.created_at}")

    # 3. Проверим товары
    print("\n=== Order Items ===")
    items = session.execute(select(OrderItem)).scalars().all()
    for i in items:
        print(f"OrderID={i.order_id}, SKU={i.sku}, Title={i.title}, Qty={i.qty}, Price={i.price}")

    # 4. Проверим доставку
    print("\n=== Shipments ===")
    shipments = session.execute(select(Shipment)).scalars().all()
    for s in shipments:
        print(f"OrderID={s.order_id}, Carrier={s.carrier}, Tracking={s.tracking_no}, LastEvent={s.last_event}, ETA={s.eta_date}")

    session.close()

if __name__ == "__main__":
    main()
