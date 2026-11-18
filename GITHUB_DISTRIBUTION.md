# GitHub Distribution Guide

## Recommended Method

Use GitHub like this:

1. Put source files in the repository.
2. Do not commit `dist/HM_VA_v06.exe`.
3. Create a GitHub Release.
4. Upload `dist/HM_VA_v06.exe` as a release asset.
5. Tell users to download the EXE from Releases.

`HM_VA_v06.exe` is about 330 MB, so it should not be pushed as a normal git file.

## Files To Commit

Recommended files:

```text
HM_VA_v06.py
HM_VA_v06.spec
BUILD_EXE_HM_VA_v06.bat
START_HM_VA_v06.bat
requirements.txt
README.md
SETUP_OTHER_PC.md
GITHUB_DISTRIBUTION.md
.gitignore
```

Optional:

```text
HM_VA_v01.py ... HM_VA_v05.py
visual_test*.py
motion.py
```

Do not commit:

```text
dist/
build/
venv/
.venv/
__pycache__/
vision_results.csv
screen_calibration.json
*.exe
```

## Basic Git Commands

```powershell
git add HM_VA_v06.py HM_VA_v06.spec BUILD_EXE_HM_VA_v06.bat START_HM_VA_v06.bat requirements.txt README.md SETUP_OTHER_PC.md GITHUB_DISTRIBUTION.md .gitignore
git commit -m "Prepare HM_VA_v06 for GitHub distribution"
git branch -M main
git remote add origin https://github.com/YOUR_NAME/YOUR_REPO.git
git push -u origin main
```

If `origin` already exists:

```powershell
git remote set-url origin https://github.com/YOUR_NAME/YOUR_REPO.git
git push -u origin main
```

## Create A Release

1. Open the repository on GitHub.
2. Go to Releases.
3. Click "Draft a new release".
4. Create a tag such as `v0.6.0`.
5. Upload `dist/HM_VA_v06.exe`.
6. Publish the release.

Users can then download the EXE without installing Python.
