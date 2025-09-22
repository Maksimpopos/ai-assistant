# resolver.py
from sqlalchemy import select
from db import SessionLocal, Customer, Order, OrderItem, Shipment

def get_order_context(sender_email: str, subject: str, body: str):
    """
    Пытается найти заказ либо по email клиента, либо по номеру заказа в теме/тексте.
    Возвращает dict с данными или None.
    """
    session = SessionLocal()
    try:
        # 1) пробуем вытащить номер заказа из темы/текста
        import re
        m = re.search(r"\b\d{5,}\b", subject + " " + body)
        order_no = m.group(0) if m else None

        q = None
        if order_no:
            q = select(Order).where(Order.external_order_no == order_no)
        else:
            # ищем по email клиента
            q = (
                select(Order)
                .join(Customer, Order.customer_id == Customer.id)
                .where(Customer.email == sender_email)
            )

        order = session.execute(q).scalars().first()
        if not order:
            return None

        # подтянем customer
        customer = order.customer

        # подтянем items
        items = session.execute(
            select(OrderItem).where(OrderItem.order_id == order.id)
        ).scalars().all()

        # подтянем shipment
        shipment = session.execute(
            select(Shipment).where(Shipment.order_id == order.id)
        ).scalars().first()

        return {
            "order_no": order.external_order_no,
            "status": order.status,
            "created_at": order.created_at.strftime("%Y-%m-%d %H:%M"),
            "customer": {"name": customer.name, "email": customer.email},
            "items": [{"sku": it.sku, "title": it.title, "qty": it.qty, "price": it.price} for it in items],
            "shipment": {
                "carrier": shipment.carrier,
                "tracking_no": shipment.tracking_no,
                "last_event": shipment.last_event,
                "eta_date": shipment.eta_date,
            } if shipment else None,
        }
    finally:
        session.close()

