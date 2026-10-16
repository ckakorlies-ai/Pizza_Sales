CREATE TABLE IF NOT EXISTS pizza_sales (
    id SERIAL PRIMARY KEY,
    order_id INTEGER NOT NULL,
    order_date DATE NOT NULL,
    pizza_id VARCHAR(50),
    pizza_name VARCHAR(200),
    pizza_category VARCHAR(100),
    pizza_size VARCHAR(20),
    quantity INTEGER NOT NULL,
    unit_price NUMERIC(10,2) NOT NULL,
    total_price NUMERIC(10,2) NOT NULL,
    pizza_ingredients TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_pizza_sales_order_id ON pizza_sales(order_id);
CREATE INDEX IF NOT EXISTS idx_pizza_sales_order_date ON pizza_sales(order_date);
CREATE INDEX IF NOT EXISTS idx_pizza_sales_pizza_category ON pizza_sales(pizza_category);
CREATE INDEX IF NOT EXISTS idx_pizza_sales_pizza_name ON pizza_sales(pizza_name);
