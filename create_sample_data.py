"""
Generates rich sample Parquet files with diverse data types for testing and demoing the editor.
"""
import os
import pandas as pd
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq


def generate_sample_data():
    samples_dir = os.path.join(os.getcwd(), "sample_data")
    os.makedirs(samples_dir, exist_ok=True)

    # 1. Sales Dataset
    np.random.seed(42)
    n_sales = 250
    products = ["Laptop Pro 16", "Wireless Mouse", "4K Monitor 27\"", "Mechanical Keyboard", "USB-C Hub", "Noise Cancelling Headphones"]
    regions = ["North America", "Europe", "Asia-Pacific", "Latin America"]

    dates = pd.date_range(start="2025-01-01", periods=n_sales, freq="12h")
    prod_choices = np.random.choice(products, size=n_sales)
    quantities = np.random.randint(1, 15, size=n_sales)
    prices = {"Laptop Pro 16": 1299.99, "Wireless Mouse": 29.99, "4K Monitor 27\"": 399.50, "Mechanical Keyboard": 89.00, "USB-C Hub": 39.95, "Noise Cancelling Headphones": 199.00}
    unit_prices = np.array([prices[p] for p in prod_choices])
    totals = quantities * unit_prices

    ratings = np.random.choice([1.0, 2.0, 3.0, 4.0, 5.0, np.nan], size=n_sales, p=[0.05, 0.05, 0.15, 0.35, 0.30, 0.10])
    is_shipped = np.random.choice([True, False], size=n_sales, p=[0.85, 0.15])

    df_sales = pd.DataFrame({
        "order_id": np.arange(1001, 1001 + n_sales, dtype=np.int64),
        "order_date": dates,
        "region": np.random.choice(regions, size=n_sales),
        "product": prod_choices,
        "quantity": quantities.astype(np.int32),
        "unit_price": unit_prices.astype(np.float64),
        "total_amount": totals.round(2).astype(np.float64),
        "is_shipped": is_shipped,
        "customer_rating": ratings,
    })

    sales_path = os.path.join(samples_dir, "sales_orders.parquet")
    table_sales = pa.Table.from_pandas(df_sales)
    pq.write_table(table_sales, sales_path, compression="snappy")
    print(f"Generated {sales_path} ({len(df_sales)} rows)")

    # 2. Employees Dataset
    n_emp = 120
    departments = ["Engineering", "Product", "Sales", "Design", "Human Resources", "Finance"]
    first_names = ["Emma", "Liam", "Olivia", "Noah", "Ava", "Ethan", "Sophia", "Lucas", "Mia", "Jackson"]
    last_names = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", "Rodriguez", "Martinez"]

    full_names = [f"{np.random.choice(first_names)} {np.random.choice(last_names)}" for _ in range(n_emp)]
    salaries = np.random.randint(55000, 185000, size=n_emp)
    hire_dates = pd.date_range(start="2018-03-01", periods=n_emp, freq="15D")

    df_emp = pd.DataFrame({
        "emp_id": np.arange(5001, 5001 + n_emp, dtype=np.int64),
        "full_name": full_names,
        "department": np.random.choice(departments, size=n_emp),
        "salary": salaries.astype(np.float64),
        "hire_date": hire_dates,
        "is_remote": np.random.choice([True, False], size=n_emp, p=[0.6, 0.4]),
        "performance_score": np.random.choice(["Exceeds", "Meets", "Needs Improvement", None], size=n_emp, p=[0.3, 0.55, 0.1, 0.05]),
    })

    emp_path = os.path.join(samples_dir, "company_employees.parquet")
    table_emp = pa.Table.from_pandas(df_emp)
    pq.write_table(table_emp, emp_path, compression="snappy")
    print(f"Generated {emp_path} ({len(df_emp)} rows)")


if __name__ == "__main__":
    generate_sample_data()
