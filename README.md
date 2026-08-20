# ParqBench (Parquet Editor) 📊

A lightweight, desktop-based Excel-like spreadsheet editor and analytical workspace for Apache Parquet files. Built for speed and safety using **Python 3.11**, **PySide6 (Qt6)**, **Pandas**, and **PyArrow**.

---

## 🚀 Quick Start

### 1. Environment Activation (Windows)

Using **PowerShell**:
`.\.venv\Scripts\Activate.ps1`

Using **Command Prompt (CMD)**:
`.\.venv\Scripts\activate.bat`

### 2. Launch the Application

`python main.py`

Or open a file directly:
`python main.py sample_data\sales_orders.parquet`

---

## 🌟 Current Features

### 🗂️ 1. Filtered Workspace Explorer
- Live directory tree view filtered strictly to folders and `.parquet` files.
- Context menu: Open file, Reveal in Windows File Explorer, Copy Absolute Path.

### 📈 2. Excel-like Data Grid
- **Inline Cell Editing**: Type-aware editing (integers, floats, booleans, timestamps, strings, nulls) with amber highlight tracking for unsaved changes.
- **Excel Integration**: Full `Ctrl+C` / `Ctrl+V` support (TSV format) for seamless copying to/from Excel and Google Sheets.
- **Status Metrics**: Real-time **Count**, **Sum**, **Average**, **Min**, and **Max** on selected cells.
- **Row Operations & Search**: Instant search (`Ctrl+F`), row jumping, and insert/delete row capabilities.
- **Schema & Types Dialog**: Inspect PyArrow types, Pandas dtypes, null statistics, and metadata.

### 🔍 3. Visual Parquet Diff Tool
- Compare two Parquet files side-by-side or match by primary key.
- Color-coded grid highlighting added rows, deleted rows, and modified cells.
- Detailed schema drift summary and CSV export.

### 🛡️ 4. Non-Destructive Save Engine
- Intercepts standard save actions (`Ctrl+S`) to force a **"Save As"** dialog (e.g., `<filename>_edited.parquet`).
- Guarantees original source files remain entirely untouched.
- Serializes data back to `.parquet` using PyArrow with snappy compression and strict type preservation. 

### 🧱 5: Core Editing & Schema Mutations (Next Up)
- **Undo/Redo Command Stack**: Full `Ctrl+Z` and `Ctrl+Y` support for all cell, row, and bulk paste edits.
- **Schema Operations**: Add, rename, or delete columns directly from the grid header.
- **Formula Engine**: Calculate new columns using expressions (e.g., `col('price') * col('qty')`).

### 📂 6: Workspace & Storage Engine
- **Multi-Tab Interface**: Open, edit, and compare multiple Parquet files concurrently.
- **Hive Partition Support**: Automatically scan and load directory trees organized by partition keys (e.g., `/year=2025/month=08/*.parquet`).

### 🔬 7: Analytics & Advanced Tooling
- **Embedded DuckDB SQL Console**: Run blazing-fast SQL queries directly on in-memory Arrow tables.
- **Data Profiler**: Visual sidebars displaying column distributions, histograms, null percentages, and min/max ranges.

---

## 🧪 Testing

To run the automated engine and UI test suite:
`.\.venv\Scripts\python.exe -m unittest discover tests`

**⚠️ Disclaimer:** This software is in active development, has not been thoroughly tested, and may contain bugs. Please back up your critical data before use.