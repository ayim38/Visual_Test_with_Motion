# Setup On Another PC

## Requirements

- Windows PC
- Python 3.10.x
- Web camera

## Steps

1. Copy this whole `Visual_Test_with_Motion` folder to the other PC.

2. Open PowerShell in the copied folder.

3. Create a virtual environment.

```powershell
py -3.10 -m venv .venv
```

4. Activate the virtual environment.

```powershell
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation, run this once and activate again.

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

5. Install packages.

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

6. Run the app.

```powershell
python HM_VA_v06.py
```

## Camera

The script searches camera indices in this order:

```text
1, 0, 2, 3
```

This means an external USB camera is preferred when it is detected as camera `1`.

The startup log shows the selected camera index.

```text
Using camera index: 1
```

## Files To Copy

- `HM_VA_v06.py`
- `requirements.txt`
- `meiryo.ttc`, if this file exists in the folder
- `screen_calibration.json`, only if you want to reuse the same calibration

If the other PC has a different monitor size or display scaling, do not copy
`screen_calibration.json`. Calibrate again on the other PC.
