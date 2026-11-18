# Visual Test with Motion

OpenCV and MediaPipe based visual acuity and motion check app.

## Download For Users

For normal use, download `HM_VA_v06.exe` from the GitHub Releases page and run it.

The app uses a camera and searches camera indices in this order:

```text
1, 0, 2, 3
```

External USB cameras are preferred when they are detected as camera `1`.

## Run From Source

Use Python 3.10.x.

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python HM_VA_v06.py
```

## Build EXE

```powershell
python -m pip install pyinstaller
python -m PyInstaller HM_VA_v06.spec --clean --noconfirm
```

Or double-click:

```text
BUILD_EXE_HM_VA_v06.bat
```

The output file is:

```text
dist\HM_VA_v06.exe
```

## Calibration And Results

`screen_calibration.json` and `vision_results.csv` are local files and are not tracked by git.

Calibrate again when using a different monitor, display scaling, or PC.
