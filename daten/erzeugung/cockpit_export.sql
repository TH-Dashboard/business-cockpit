-- Cockpit-Export: eine Zeile pro Bestellposition (alle 9.997), nur lesend
SELECT od.order_details_id, od.order_id, o.order_date, o.shipping_date, o.shipping_mode,
       o.shipping_region, o.shipping_state, o.shipping_city, c.customer_id,
       TRIM(c.customer_name) AS customer_name, c.customer_segment, p.product_id, p.product_name,
       p.product_category, p.product_subcategory, od.quantity, od.order_discount,
       od.order_sales, od.order_profits
FROM order_details od
JOIN orders o    ON od.order_id = o.order_id
JOIN customers c ON o.customer_id = c.customer_id
JOIN product p   ON od.product_id = p.product_id
ORDER BY od.order_details_id;
