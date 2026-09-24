# ParqBench 📊

A high-performance, desktop-based Excel-like spreadsheet editor and analytical workbench for Apache Parquet files. Built for speed, safety, and non-destructive workflows using **Python 3.11**, **PySide6 (Qt6)**, **Pandas**, **PyArrow**, and **DuckDB**.

---

## 🌟 Key Features

### 🗂️ 1. Workspace Explorer & Hive Partitions
- Filtered directory tree view strictly listing folders and `.parquet` files.
- Drag-and-drop `.parquet` files and directories directly into the window.
- **Hive Partition Loader**: Scan and load partitioned datasets as unified DataFrames.
- Resizable explorer columns with auto-fit, column visibility toggles, and context menus.

### 📈 2. Excel-like Data Grid & Editing
- **Type-Aware In-Place Editing**: Integers, floats, decimals, booleans, timestamps, strings, and nulls with amber highlight tracking for modified cells.
- **Full Undo / Redo**: Unlimited command stack (`Ctrl+Z` / `Ctrl+Y`) for cell edits, row inserts/deletes, and bulk paste operations.
- **Excel & Sheets Interop**: Seamless copy/paste (`Ctrl+C` / `Ctrl+V`) via standard TSV.
- **Instant Search**: Find toolbar (`Ctrl+F`) with real-time match cycling and occurrence counts.
- **Spark / Excel Style Filtering**: Categorical checkboxes + numeric conditions (`>`, `<`, `=`, `between`, `is null`).
- **Live Aggregation Metrics**: Real-time **Count**, **Sum**, **Average**, **Min**, and **Max** on multi-cell selections.

### 🧮 3. Formula Builder & Schema Ops
- **Dynamic Formula Engine**: Compute new columns or mutate existing ones via expressions (e.g. `col('price') * col('qty')`, `to_numeric(c('tax'))`, `where(cond, x, y)`).
- **Safe Type Coercion**: Handles mixed `Decimal`, `float`, and `int` types automatically.
- **Schema Management**: Add, rename, or delete columns with live schema inspection.

### 🦆 4. DuckDB SQL Console & Data Profiler
- **Embedded DuckDB SQL Console**: Run SQL queries (`SELECT * FROM current_table WHERE ...`) directly on loaded Parquet data in a non-blocking background thread.
- **Visual Data Profiler**: Instant column distributions, null percentages, quantiles, and ASCII histograms.

### 🔍 5. Visual Parquet Diff & Working Copy Inspector
- Side-by-side file comparison or primary key matching with color-coded additions, deletions, and cell edits.
- **Working Copy Diff (`Ctrl+Shift+D`)**: Git-style diff inspector comparing your current unsaved edits against the original baseline.

### 🛡️ 6. Non-Destructive Save Engine
- Intercepts standard save actions (`Ctrl+S`) to protect original files and force a safe save workflow.
- High-fidelity serialization using PyArrow with Snappy compression and strict schema preservation.
- Export to CSV, Excel (`.xlsx`), and JSON.

---

## 🚀 Quick Start (Development)

### 1. Requirements
- Python 3.11+
- Install dependencies:
  ```bash
  pip install -r requirements.txt
  ```

### 2. Launch Application
```bash
python main.py
```
Or open a file or directory directly:
```bash
python main.py sample_data\sales_orders.parquet
```

### 3. Run Automated Tests
```bash
python -m pytest
```

---

## 📦 Building & Non-Admin Installation

ParqBench supports complete **non-administrator installation** on Windows — no UAC prompts or elevated permissions are required.

### 1. Build Executable & Portable Package
Run the automated release build script:
```bash
python build_release.py
```
This produces:
- `dist/ParqBench/`: Standalone folder distribution containing `ParqBench.exe`.
- `dist/ParqBench-v1.0.0-windows-x64-portable.zip`: Portable ZIP archive that runs from any folder.

### 2. Non-Admin User Installation Options

#### Option A: Inno Setup Installer (`.exe`)
The installer is configured with `PrivilegesRequired=lowest`:
- Installs to `%LOCALAPPDATA%\Programs\ParqBench`
- Creates Start Menu & Desktop shortcuts
- Registers `.parquet` file association under `HKCU`
- Never asks for Administrator permissions or UAC elevation
- Compile script: `installer\parqbench_setup.iss` (requires Inno Setup)

#### Option B: One-Click PowerShell User Installer
Run from PowerShell:
```powershell
.\installer\install_user.ps1
```
This automatically deploys ParqBench to `%LOCALAPPDATA%\Programs\ParqBench`, creates Start Menu shortcuts, and registers `.parquet` file associations without administrator rights.

---

## 📄 License
MIT License.