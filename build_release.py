"""
ParqBench Release Builder
Automates:
  1. Icon generation
  2. Test suite validation
  3. PyInstaller executable build (windowed, no console)
  4. Portable ZIP release archive packaging
  5. Inno Setup non-admin installer compilation (if iscc is available)
"""
import os
import sys
import shutil
import zipfile
import subprocess
from src import __version__, __app_name__

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))


def run_cmd(cmd, cwd=REPO_ROOT):
    print(f"--> Running: {' '.join(cmd) if isinstance(cmd, list) else cmd}")
    res = subprocess.run(cmd, cwd=cwd, shell=isinstance(cmd, str))
    if res.returncode != 0:
        print(f"Error: command failed with return code {res.returncode}")
        sys.exit(res.returncode)


def main():
    print(f"==================================================")
    print(f" Building Release for {__app_name__} v{__version__}")
    print(f"==================================================")

    # 1. Assets
    print("\n[Step 1/5] Ensuring icons & assets exist...")
    run_cmd([sys.executable, "generate_assets.py"])

    # 2. Automated Tests
    print("\n[Step 2/5] Running automated test suite...")
    run_cmd([sys.executable, "-m", "pytest"])

    # 3. PyInstaller
    print("\n[Step 3/5] Building standalone executable with PyInstaller...")
    dist_dir = os.path.join(REPO_ROOT, "dist")
    build_dir = os.path.join(REPO_ROOT, "build")
    
    run_cmd([sys.executable, "-m", "PyInstaller", "--clean", "-y", "ParqBench.spec"])

    output_folder = os.path.join(dist_dir, "ParqBench")
    exe_file = os.path.join(output_folder, "ParqBench.exe")
    if not os.path.isfile(exe_file):
        print(f"Error: Executable was not created at {exe_file}")
        sys.exit(1)
    print(f"Executable verified at: {exe_file}")

    # Ensure assets directory is present in root distribution folder
    dest_assets = os.path.join(output_folder, "assets")
    src_assets = os.path.join(REPO_ROOT, "assets")
    if os.path.exists(src_assets):
        shutil.copytree(src_assets, dest_assets, dirs_exist_ok=True)

    # 4. Create Portable ZIP
    print("\n[Step 4/5] Creating portable distribution ZIP...")
    zip_name = f"ParqBench-v{__version__}-windows-x64-portable.zip"
    zip_path = os.path.join(dist_dir, zip_name)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(output_folder):
            for file in files:
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, output_folder)
                zf.write(full_path, os.path.join("ParqBench", rel_path))
    print(f"Portable release archive created: {zip_path}")

    # 5. Inno Setup Compiler (if available)
    print("\n[Step 5/5] Checking for Inno Setup compiler (iscc.exe)...")
    iscc_candidates = [
        r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        r"C:\Program Files\Inno Setup 6\ISCC.exe",
        shutil.which("iscc"),
    ]
    iscc_path = next((p for p in iscc_candidates if p and os.path.isfile(p)), None)

    if iscc_path:
        print(f"Found Inno Setup at: {iscc_path}")
        iss_path = os.path.join(REPO_ROOT, "installer", "parqbench_setup.iss")
        run_cmd([iscc_path, iss_path])
        print("Non-admin Windows Installer successfully generated in dist/installer/")
    else:
        print("Note: Inno Setup (ISCC.exe) not found on PATH or standard program directories.")
        print("To build the installer executable, install Inno Setup and run:")
        print(f"  ISCC.exe {os.path.join(REPO_ROOT, 'installer', 'parqbench_setup.iss')}")
        print("Or distribute the portable ZIP generated in Step 4.")

    print(f"\n==================================================")
    print(f" Build complete! Release artifacts ready in dist/")
    print(f"==================================================")


if __name__ == "__main__":
    main()
