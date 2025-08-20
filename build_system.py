#!/usr/bin/env python3
"""
Gangware Build System
Handles building executable distributions with different configurations.
"""

import shutil
import subprocess
import sys
import time
from pathlib import Path

class GangwareBuildSystem:
    EXECUTABLE_NAME = "Gangware.exe"

    def __init__(self):
        self.project_root = Path.cwd()
        self.dist_dir = self.project_root / "dist"
        self.build_dir = self.project_root / "build"
        self.venv_python = self.project_root / ".venv" / "Scripts" / "python.exe"

    def clean_build_dirs(self):
        """Remove previous build artifacts"""
        print("🧹 Cleaning build directories...")
        for dir_path in [self.dist_dir, self.build_dir]:
            if dir_path.exists():
                shutil.rmtree(dir_path)
                print(f"   Removed {dir_path}")

    def check_environment(self):
        """Verify build environment is ready"""
        print("🔍 Checking build environment...")

        # Check virtual environment
        if not self.venv_python.exists():
            print("❌ Virtual environment not found!")
            print("   Please run: python -m venv .venv")
            return False

        # Check required packages
        try:
            result = subprocess.run([
                str(self.venv_python), "-c",
                "import PyQt6, cv2, numpy, mss, pydirectinput, pyinstaller"
            ], capture_output=True, text=True)

            if result.returncode != 0:
                print("❌ Missing required packages!")
                print("   Please run: pip install -r requirements.txt pyinstaller")
                return False

        except Exception as e:
            print(f"❌ Environment check failed: {e}")
            return False

        print("✅ Environment ready!")
        return True

    def run_tests(self):
        """Run quick tests before building"""
        print("🧪 Running tests...")
        try:
            result = subprocess.run([
                str(self.venv_python), "-m", "pytest",
                "tests/test_smoke.py", "-v", "--tb=short"
            ], cwd=self.project_root)

            if result.returncode == 0:
                print("✅ Tests passed!")
                return True
            else:
                print("⚠️  Some tests failed, continuing anyway...")
                return True  # Continue even if tests fail

        except Exception as e:
            print(f"⚠️  Test execution failed: {e}")
            return True  # Continue anyway

    def build_executable(self, config="release"):
        """Build the executable using PyInstaller"""
        print(f"🔨 Building Gangware executable ({config} mode)...")

        spec_file = self.project_root / "gangware.spec"
        if not spec_file.exists():
            print("❌ gangware.spec not found!")
            return False

        # Modify spec for debug vs release
        if config == "debug":
            print("   Building with console output enabled...")
            # Could modify spec file here for debug mode

        try:
            start_time = time.time()
            result = subprocess.run([
                str(self.venv_python), "-m", "PyInstaller",
                "--clean", str(spec_file)
            ], cwd=self.project_root)

            build_time = time.time() - start_time

            if result.returncode == 0:
                exe_path = self.dist_dir / self.EXECUTABLE_NAME
                if exe_path.exists():
                    size_mb = exe_path.stat().st_size / 1024 / 1024
                    print(f"✅ Build successful! ({build_time:.1f}s)")
                    print(f"   Executable: {exe_path}")
                    print(f"   Size: {size_mb:.1f} MB")
                    return True
                else:
                    print("❌ Build completed but executable not found!")
                    return False
            else:
                print("❌ Build failed!")
                return False

        except Exception as e:
            print(f"❌ Build error: {e}")
            return False

    def create_release_package(self):
        """Create a complete release package"""
        print("📦 Creating release package...")

        exe_path = self.dist_dir / self.EXECUTABLE_NAME
        if not exe_path.exists():
            print("❌ Executable not found!")
            return False

        # Create release directory
        release_dir = self.project_root / "release"
        if release_dir.exists():
            shutil.rmtree(release_dir)
        release_dir.mkdir()

        # Copy executable
        shutil.copy2(exe_path, release_dir / self.EXECUTABLE_NAME)

        # Copy essential files
        essential_files = [
            "README.md",
            "config/config.ini",
        ]

        for file_path in essential_files:
            src = self.project_root / file_path
            if src.exists():
                if src.is_file():
                    dst = release_dir / src.name
                    shutil.copy2(src, dst)
                else:
                    dst = release_dir / src.name
                    shutil.copytree(src, dst)

        # Create user guide
        user_guide = release_dir / "QUICK_START.txt"
        user_guide.write_text("""
GANGWARE - Quick Start Guide
============================

1. INSTALLATION:
   - Extract all files to a folder (e.g., C:\\Gangware\\)
   - Run Gangware.exe as Administrator for best compatibility

2. FIRST RUN:
   - The overlay will appear in the top-right corner
   - Press F7 to open calibration menu
   - Follow the calibration steps to set up your inventory hotkey and search bar

3. HOTKEYS:
   - F1: Toggle overlay visibility
   - F2: Equip Flak armor set
   - F3: Equip Tek armor set
   - F4: Equip Mixed armor set
   - F5: Medbrew burst heal
   - F6: Manual ROI capture
   - F7: Recalibrate settings
   - F10: Exit application

4. TROUBLESHOOTING:
   - If hotkeys don't work, run as Administrator
   - If armor detection fails, recalibrate with F7
   - For issues, check the logs in %APPDATA%\\Gangware\\logs\\

5. ANTIVIRUS:
   - Add Gangware.exe to your antivirus exclusions
   - Some automation tools may trigger false positives

Enjoy using Gangware!
""")

        print(f"✅ Release package created: {release_dir}")
        return True

    def build_all(self):
        """Complete build process"""
        print("🚀 Starting Gangware build process...")
        print("=" * 50)

        if not self.check_environment():
            return False

        self.clean_build_dirs()

        if not self.run_tests():
            print("⚠️  Proceeding despite test issues...")

        if not self.build_executable():
            return False

        if not self.create_release_package():
            return False

        print("=" * 50)
        print("🎉 Build process completed successfully!")
        print("\nNext steps:")
        print("1. Test the executable in /release/")
        print("2. Consider code signing for distribution")
        print("3. Create installer with NSIS or similar")

        return True

if __name__ == "__main__":
    builder = GangwareBuildSystem()

    if len(sys.argv) > 1 and sys.argv[1] == "debug":
        success = builder.build_executable("debug")
    else:
        success = builder.build_all()

    sys.exit(0 if success else 1)
