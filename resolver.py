# resolver.py
import re
from sqlalchemy import select, desc
from db import SessionLocal, Customer, Order, OrderItem, Shipment

# какие номера считаем «похожими на номер заказа»
ORDER_PATTERNS = [r"#(\d{4,10})", r"\bORD[-\s_]?(\d{3,12})\b"]

def extract_order_no(text: str) -> str | None:
    for pat in ORDER_PATTERNS:
        m = re.search(pat, text or "", flags=re.IGNORECASE)
        if m:
            return m.group(1)
    return None

def get_order_context(sender_email: str, subject: str, body: str) -> dict | None:
    order_no = extract_order_no(f"{subject}\n{body}")
    with SessionLocal() as s:
        if order_no:
            order = s.execute(select(Order).where(Order.external_order_no==order_no)).scalar_one_or_none()
        else:
            cust = s.execute(select(Customer).where(Customer.email==(sender_email or "").strip().lower())).scalar_one_or_none()
            if not cust:
                return None
            order = s.execute(
                select(Order).where(Order.customer_id==cust.id).order_by(desc(Order.created_at))
            ).scalars().first()

        if not order:
            return None

        items = s.execute(select(OrderItem).where(OrderItem.order_id==order.id)).scalars().all()
        ship  = s.execute(select(Shipment).where(Shipment.order_id==order.id)).scalars().first()

        return {
            "order_no": order.external_order_no,
            "status": order.status,
            "created_at": order.created_at,
            "items": [{"sku": i.sku, "title": i.title, "qty": i.qty} for i in items],
            "shipment": ({"carrier": ship.carrier, "tracking_no": ship.tracking_no,
                          "last_event": ship.last_event, "eta_date": ship.eta_date} if ship else None)
        }
