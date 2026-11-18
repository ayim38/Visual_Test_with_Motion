from PIL import Image, ImageDraw, ImageFont
import numpy as np
import cv2
import time
import mediapipe as mp
import csv
import json
import math
from datetime import datetime
import sys, os
from pathlib import Path

FORCE_EXIT_KEYS = {27}
EXIT_HINT_TEXT = "ESCで終了"
CALIBRATION_REFERENCE_CM = 5.0
TEST_DISTANCE_M = 3.0
CALIBRATION_SETTINGS_FILE = "screen_calibration.json"
VISUAL_ACUITY_LEVELS = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
CAMERA_INDEX_CANDIDATES = [1, 0, 2, 3]

def resource_path(rel_path: str) -> str:
    """PyInstaller 実行時にも使えるようにリソースの絶対パスを返す。"""
    base = getattr(sys, "_MEIPASS", Path(__file__).parent)
    return str(Path(base) / rel_path)

def app_dir() -> Path:
    """アプリの出力先ディレクトリを返す。exe 実行時は exe と同じ場所、通常実行時はスクリプト配置先。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent

def calibration_settings_path() -> Path:
    """校正設定ファイルのパスを返す。"""
    return app_dir() / CALIBRATION_SETTINGS_FILE

def load_calibration_settings():
    """保存済みの校正設定を読み込む。"""
    path = calibration_settings_path()
    if not path.exists():
        return None

    try:
        with open(path, "r", encoding="utf-8") as file:
            settings = json.load(file)
    except (OSError, json.JSONDecodeError):
        return None

    cm_to_px = settings.get("cm_to_px")
    reference_cm = settings.get("reference_cm")
    test_distance_m = settings.get("test_distance_m")

    if not isinstance(cm_to_px, (int, float)) or cm_to_px <= 0:
        return None
    if not isinstance(reference_cm, (int, float)) or reference_cm <= 0:
        return None
    if not isinstance(test_distance_m, (int, float)) or test_distance_m <= 0:
        return None

    return settings

def save_calibration_settings(cm_to_px, reference_cm=CALIBRATION_REFERENCE_CM, test_distance_m=TEST_DISTANCE_M):
    """校正設定を JSON に保存する。"""
    settings = {
        "cm_to_px": cm_to_px,
        "reference_cm": reference_cm,
        "test_distance_m": test_distance_m,
        "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    with open(calibration_settings_path(), "w", encoding="utf-8") as file:
        json.dump(settings, file, ensure_ascii=False, indent=2)

def calculate_landolt_outer_diameter_cm(visual_acuity, test_distance_m=TEST_DISTANCE_M):
    """
    視力値と検査距離から、ランドルト環の外径 [cm] を理論式で求める。
    """
    distance_cm = test_distance_m * 100.0
    angle_deg = 5.0 / (60.0 * visual_acuity)
    return distance_cm * math.tan(math.radians(angle_deg))

def build_landolt_size_table(visual_acuity_levels=None, test_distance_m=TEST_DISTANCE_M):
    """
    検査距離に応じたランドルト環サイズ表を生成する。
    """
    levels = visual_acuity_levels or VISUAL_ACUITY_LEVELS
    return [
        (calculate_landolt_outer_diameter_cm(acuity, test_distance_m=test_distance_m), acuity)
        for acuity in levels
    ]

def calculate_landolt_display_error(visual_acuity, outer_diameter_px, cm_to_px, test_distance_m=TEST_DISTANCE_M):
    """
    理論値と実際の表示値の差を計算する。
    """
    theoretical_cm = calculate_landolt_outer_diameter_cm(visual_acuity, test_distance_m=test_distance_m)
    displayed_cm = outer_diameter_px / cm_to_px
    error_cm = displayed_cm - theoretical_cm
    error_mm = error_cm * 10.0
    error_percent = 0.0 if theoretical_cm == 0 else (error_cm / theoretical_cm) * 100.0
    return {
        "theoretical_cm": theoretical_cm,
        "displayed_cm": displayed_cm,
        "error_cm": error_cm,
        "error_mm": error_mm,
        "error_percent": error_percent,
    }

def open_available_camera(camera_indices=CAMERA_INDEX_CANDIDATES):
    """
    利用できるカメラを候補番号から順に探して開く。
    外部 Web カメラを想定し、既定では 1 番を 0 番より優先する。
    """
    for camera_index in camera_indices:
        cap = cv2.VideoCapture(camera_index)
        if cap.isOpened():
            print(f"Using camera index: {camera_index}")
            return cap, camera_index
        cap.release()

    return None, None

def force_terminate_program(cap=None, hands=None, exit_code=0):
    """Release resources and terminate the program immediately."""
    print("Force exit requested. Shutting down the program.")
    if cap is not None:
        try:
            if cap.isOpened():
                cap.release()
        except Exception:
            pass

    if hands is not None:
        try:
            hands.close()
        except Exception:
            pass

    try:
        cv2.destroyAllWindows()
    except Exception:
        pass

    raise SystemExit(exit_code)

def add_exit_hint(image, text=EXIT_HINT_TEXT):
    """Add a small exit hint to the lower-right corner of an image."""
    hinted = image.copy()
    height, width = hinted.shape[:2]
    box_width = 320
    box_height = 64
    x1 = max(0, width - box_width - 24)
    y1 = max(0, height - box_height - 24)
    x2 = width - 24
    y2 = height - 24

    overlay = hinted.copy()
    cv2.rectangle(overlay, (x1, y1), (x2, y2), (245, 245, 245), -1)
    hinted = cv2.addWeighted(overlay, 0.88, hinted, 0.12, 0)
    cv2.rectangle(hinted, (x1, y1), (x2, y2), (80, 80, 80), 2)
    hinted = display_japanese_text(
        hinted,
        text,
        (x1 + 20, y1 + 14),
        font_size=28,
        color=(20, 20, 20),
    )
    return hinted

def show_image(window_name, image, add_hint=True):
    """Display an image with the common exit hint."""
    image_to_show = add_exit_hint(image) if add_hint else image
    cv2.imshow(window_name, image_to_show)

def confirm_exit(cap=None, hands=None):
    """Ask the user to confirm exit before terminating the program."""
    screen_width, screen_height = 1920, 1080
    image = np.ones((screen_height, screen_width, 3), dtype=np.uint8) * 255
    image = display_japanese_text(
        image,
        "終了しますか？",
        (640, 320),
        font_size=88,
        color=(0, 0, 180),
    )
    image = display_japanese_text(
        image,
        "もう一度 ESC を押すと終了します",
        (430, 500),
        font_size=54,
        color=(0, 0, 0),
    )
    image = display_japanese_text(
        image,
        "Enter キーで検査に戻ります",
        (500, 610),
        font_size=54,
        color=(0, 0, 0),
    )

    cv2.namedWindow("exit_confirm", cv2.WINDOW_NORMAL)
    cv2.setWindowProperty("exit_confirm", cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
    show_image("exit_confirm", image, add_hint=False)

    while True:
        key = cv2.waitKey(50) & 0xFF
        if key == 27:
            cv2.destroyWindow("exit_confirm")
            force_terminate_program(cap=cap, hands=hands)
        if key in (13, 32):
            cv2.destroyWindow("exit_confirm")
            return

        try:
            if cv2.getWindowProperty("exit_confirm", cv2.WND_PROP_VISIBLE) < 1:
                cv2.destroyWindow("exit_confirm")
                return
        except cv2.error:
            return

def wait_with_forced_exit(delay_ms, cap=None, hands=None, watch_windows=None, step_ms=50):
    """Keep the UI responsive during waits and terminate on exit input."""
    elapsed = 0
    watch_windows = watch_windows or []

    while elapsed < delay_ms:
        current_step = min(step_ms, delay_ms - elapsed)
        key = cv2.waitKey(current_step) & 0xFF
        if key in FORCE_EXIT_KEYS:
            confirm_exit(cap=cap, hands=hands)

        for window_name in watch_windows:
            try:
                if cv2.getWindowProperty(window_name, cv2.WND_PROP_VISIBLE) < 1:
                    confirm_exit(cap=cap, hands=hands)
            except cv2.error:
                continue

        elapsed += current_step

def draw_landolt_ring(image, center, outer_diameter, thickness, direction):
    """
    ランドルト環を描画する。

    Args:
        image: 描画先の画像。
        center: ランドルト環の中心座標 (x, y)。
        outer_diameter: 外径 [px]。
        thickness: 線の太さ [px]。
        direction: 切れ目の方向。"up" / "down" / "left" / "right"。
    """
    # 外径と内径を計算する
    outer_radius = int(outer_diameter) // 2
    inner_radius = max(0, outer_radius - int(thickness))

    # 外側の黒円を描画する
    cv2.circle(image, center, outer_radius, (0, 0, 0), -1)

    # 内側を白で抜いて輪にする
    cv2.circle(image, center, inner_radius, (255, 255, 255), -1)

    # 切れ目の幅は線の太さと同じにする
    gap_size = thickness

    # 指定方向に白い切れ目を作る
    x, y = center
    if direction == "up":
        cv2.rectangle(image, (x - gap_size // 2, y - outer_radius),
                      (x + gap_size // 2, y), (255, 255, 255), -1)
    elif direction == "down":
        cv2.rectangle(image, (x - gap_size // 2, y),
                      (x + gap_size // 2, y + outer_radius), (255, 255, 255), -1)
    elif direction == "left":
        cv2.rectangle(image, (x - outer_radius, y - gap_size // 2),
                      (x, y + gap_size // 2), (255, 255, 255), -1)
    elif direction == "right":
        cv2.rectangle(image, (x, y - gap_size // 2),
                      (x + outer_radius, y + gap_size // 2), (255, 255, 255), -1)

def detect_arm_direction(results):
    """
    MediaPipe の手首と人差し指先端から腕の向きを判定する。

    Args:
        results: MediaPipe Hands の推論結果。

    Returns:
        str | None: "up" / "down" / "left" / "right" のいずれか。判定不能なら None。
    """
    if results.multi_hand_landmarks:
        for hand_landmarks in results.multi_hand_landmarks:
            wrist = hand_landmarks.landmark[mp.solutions.hands.HandLandmark.WRIST]
            index_tip = hand_landmarks.landmark[mp.solutions.hands.HandLandmark.INDEX_FINGER_TIP]

            # 手首から人差し指先端へのベクトルで方向を求める
            dx = index_tip.x - wrist.x
            dy = index_tip.y - wrist.y

            if abs(dx) > abs(dy):
                if dx > 0:
                    return "right"
                else:
                    return "left"
            else:
                if dy > 0:
                    return "down"
                else:
                    return "up"
    return None
       
def get_user_id_with_keyboard():
    """
    ソフトウェアキーボードを表示してユーザー ID を入力させる。
    """
    screen_height, screen_width = 1080, 1920
    keyboard_height = 400
    button_size = 100

    # キーボードのボタン配置
    buttons = [
        ("1", (screen_width // 2 - 150, screen_height - keyboard_height - 50)),
        ("2", (screen_width // 2 - 50, screen_height - keyboard_height - 50)),
        ("3", (screen_width // 2 + 50, screen_height - keyboard_height - 50)),
        ("4", (screen_width // 2 - 150, screen_height - keyboard_height + 50)),
        ("5", (screen_width // 2 - 50, screen_height - keyboard_height + 50)),
        ("6", (screen_width // 2 + 50, screen_height - keyboard_height + 50)),
        ("7", (screen_width // 2 - 150, screen_height - keyboard_height + 150)),
        ("8", (screen_width // 2 - 50, screen_height - keyboard_height + 150)),
        ("9", (screen_width // 2 + 50, screen_height - keyboard_height + 150)),
        ("0", (screen_width // 2 - 50, screen_height - keyboard_height + 250)),
        ("OK", (screen_width // 2 + 200, screen_height - keyboard_height + 50)),
        ("DEL", (screen_width // 2 + 300, screen_height - keyboard_height + 50))
    ]

    user_id = ""
    id_entered = False  # OK が押されたら True にする

    def draw_keyboard(image):
        for label, pos in buttons:
            cv2.rectangle(image, pos, (pos[0] + button_size, pos[1] + button_size), (200, 200, 200), -1)
            cv2.putText(image, label, (pos[0] + 20, pos[1] + 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 0), 2)

    def get_button(x, y):
        for label, pos in buttons:
            if pos[0] <= x <= pos[0] + button_size and pos[1] <= y <= pos[1] + button_size:
                return label
        return None
    
    # マウスクリックで入力を受け付ける
    def click_event(event, x, y, flags, param):
        nonlocal user_id, id_entered
        if event == cv2.EVENT_LBUTTONDOWN:
            button = get_button(x, y)
            if button == "DEL":
                user_id = user_id[:-1]  # 末尾 1 文字削除
            elif button == "OK":
                id_entered = True  # 入力確定
            elif button and button.isdigit():
                user_id += button  # 数字を追加

    # フルスクリーンで入力画面を表示する
    cv2.namedWindow("id_input", cv2.WINDOW_NORMAL)
    cv2.setWindowProperty("id_input", cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
    cv2.setMouseCallback("id_input", click_event)
    
    while True:
        # 入力画面を描画する
        image = np.ones((screen_height, screen_width, 3), dtype=np.uint8) * 255
        image = display_japanese_text(image, "視機能検査 EASY Visual Check", (50, 100), font_size=100, color=(0, 0, 0))
        image = display_japanese_text(image, "運動機能検査 and Motion Check", (50, 200), font_size=100, color=(0, 0, 0))
        image = display_japanese_text(image, "IDを入力してください:", (50, 300), font_size=100, color=(0, 0, 0))
        image = display_japanese_text(image, "Enter your ID:", (50, 400), font_size=100, color=(0, 0, 0))
        
        cv2.putText(image, user_id, (1000, 500), cv2.FONT_HERSHEY_SIMPLEX, 3, (0, 0, 255), 5)
        draw_keyboard(image)
        show_image("id_input", image)

        # 入力が確定したら画面を閉じて返す
        if id_entered:
            cv2.destroyWindow("id_input")
            return user_id

        # ESC 監視
        wait_with_forced_exit(1, watch_windows=["id_input"])

def calibrate_screen_scale(screen_width=1920, screen_height=1080, reference_cm=CALIBRATION_REFERENCE_CM):
    """
    定規を使って画面スケールを校正し、cm_to_px を返す。
    """
    button_width = 220
    button_height = 100
    bar_height = 28
    current_bar_px = 240
    calibration_done = False

    buttons = [
        ("-10", (screen_width // 2 - 380, 760)),
        ("-1", (screen_width // 2 - 140, 760)),
        ("+1", (screen_width // 2 + 100, 760)),
        ("+10", (screen_width // 2 + 340, 760)),
        ("OK", (screen_width // 2 - 110, 900)),
    ]

    def draw_buttons(image):
        for label, pos in buttons:
            cv2.rectangle(
                image,
                pos,
                (pos[0] + button_width, pos[1] + button_height),
                (220, 220, 220),
                -1,
            )
            cv2.rectangle(
                image,
                pos,
                (pos[0] + button_width, pos[1] + button_height),
                (100, 100, 100),
                2,
            )
            cv2.putText(
                image,
                label,
                (pos[0] + 55, pos[1] + 62),
                cv2.FONT_HERSHEY_SIMPLEX,
                1.4,
                (0, 0, 0),
                3,
            )

    def get_button(x, y):
        for label, pos in buttons:
            if pos[0] <= x <= pos[0] + button_width and pos[1] <= y <= pos[1] + button_height:
                return label
        return None

    def click_event(event, x, y, flags, param):
        nonlocal current_bar_px, calibration_done
        if event != cv2.EVENT_LBUTTONDOWN:
            return

        button = get_button(x, y)
        if button == "-10":
            current_bar_px = max(20, current_bar_px - 10)
        elif button == "-1":
            current_bar_px = max(20, current_bar_px - 1)
        elif button == "+1":
            current_bar_px += 1
        elif button == "+10":
            current_bar_px += 10
        elif button == "OK":
            calibration_done = True

    cv2.namedWindow("scale_calibration", cv2.WINDOW_NORMAL)
    cv2.setWindowProperty("scale_calibration", cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
    cv2.setMouseCallback("scale_calibration", click_event)

    while True:
        image = np.ones((screen_height, screen_width, 3), dtype=np.uint8) * 255
        image = display_japanese_text(
            image,
            f"検査距離 {TEST_DISTANCE_M:.1f} m 用の画面校正",
            (120, 90),
            font_size=72,
            color=(0, 0, 0),
        )
        image = display_japanese_text(
            image,
            f"定規を画面に当てて、下の黒いバーが {reference_cm:.1f} cm になるよう調整してください",
            (120, 190),
            font_size=42,
            color=(0, 0, 0),
        )
        image = display_japanese_text(
            image,
            "細かく調整して OK を押すと校正を開始します",
            (120, 255),
            font_size=42,
            color=(0, 0, 0),
        )

        bar_x1 = (screen_width - current_bar_px) // 2
        bar_x2 = bar_x1 + current_bar_px
        bar_y1 = 470
        bar_y2 = bar_y1 + bar_height
        cv2.rectangle(image, (bar_x1, bar_y1), (bar_x2, bar_y2), (0, 0, 0), -1)
        image = display_japanese_text(
            image,
            f"現在の基準バー: {current_bar_px} px = {reference_cm:.1f} cm",
            (screen_width // 2 - 260, 560),
            font_size=40,
            color=(0, 0, 160),
        )

        draw_buttons(image)
        show_image("scale_calibration", image)

        if calibration_done:
            cv2.destroyWindow("scale_calibration")
            return current_bar_px / reference_cm

        key = cv2.waitKey(50) & 0xFF
        if key in FORCE_EXIT_KEYS:
            confirm_exit()
        elif key in (ord("-"), ord("_")):
            current_bar_px = max(20, current_bar_px - 1)
        elif key in (ord("+"), ord("=")):
            current_bar_px += 1
        elif key == 13:
            cv2.destroyWindow("scale_calibration")
            return current_bar_px / reference_cm

        try:
            if cv2.getWindowProperty("scale_calibration", cv2.WND_PROP_VISIBLE) < 1:
                confirm_exit()
        except cv2.error:
            confirm_exit()

def choose_calibration_scale(screen_width=1920, screen_height=1080, reference_cm=CALIBRATION_REFERENCE_CM):
    """
    保存済み校正値を使うか、再校正するかを選ばせて cm_to_px を返す。
    """
    settings = load_calibration_settings()
    if settings is None:
        cm_to_px = calibrate_screen_scale(
            screen_width=screen_width,
            screen_height=screen_height,
            reference_cm=reference_cm,
        )
        save_calibration_settings(cm_to_px, reference_cm=reference_cm, test_distance_m=TEST_DISTANCE_M)
        return cm_to_px

    button_width = 420
    button_height = 110
    selected_mode = None
    buttons = [
        ("USE", (screen_width // 2 - 470, 700)),
        ("RECALIBRATE", (screen_width // 2 + 50, 700)),
    ]

    def draw_buttons(image):
        labels = {
            "USE": "前回の校正値を使う",
            "RECALIBRATE": "再校正する",
        }
        for key, pos in buttons:
            cv2.rectangle(
                image,
                pos,
                (pos[0] + button_width, pos[1] + button_height),
                (220, 220, 220),
                -1,
            )
            cv2.rectangle(
                image,
                pos,
                (pos[0] + button_width, pos[1] + button_height),
                (100, 100, 100),
                2,
            )
            image = display_japanese_text(
                image,
                labels[key],
                (pos[0] + 28, pos[1] + 28),
                font_size=34,
                color=(0, 0, 0),
            )
        return image

    def get_button(x, y):
        for key, pos in buttons:
            if pos[0] <= x <= pos[0] + button_width and pos[1] <= y <= pos[1] + button_height:
                return key
        return None

    def click_event(event, x, y, flags, param):
        nonlocal selected_mode
        if event != cv2.EVENT_LBUTTONDOWN:
            return
        button = get_button(x, y)
        if button is not None:
            selected_mode = button

    cv2.namedWindow("calibration_choice", cv2.WINDOW_NORMAL)
    cv2.setWindowProperty("calibration_choice", cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
    cv2.setMouseCallback("calibration_choice", click_event)

    while True:
        image = np.ones((screen_height, screen_width, 3), dtype=np.uint8) * 255
        image = display_japanese_text(
            image,
            "画面校正データが見つかりました",
            (320, 140),
            font_size=72,
            color=(0, 0, 0),
        )
        image = display_japanese_text(
            image,
            f"前回の校正値: 1 cm = {settings['cm_to_px']:.2f} px",
            (420, 290),
            font_size=48,
            color=(0, 0, 160),
        )
        image = display_japanese_text(
            image,
            f"基準バー: {settings['reference_cm']:.1f} cm    検査距離: {settings['test_distance_m']:.1f} m",
            (340, 380),
            font_size=44,
            color=(0, 0, 0),
        )
        saved_at = settings.get("saved_at", "不明")
        image = display_japanese_text(
            image,
            f"保存日時: {saved_at}",
            (520, 460),
            font_size=38,
            color=(80, 80, 80),
        )
        image = display_japanese_text(
            image,
            "前回の校正値を使うか、もう一度定規で校正するか選んでください",
            (220, 560),
            font_size=42,
            color=(0, 0, 0),
        )

        image = draw_buttons(image)
        show_image("calibration_choice", image)

        if selected_mode == "USE":
            cv2.destroyWindow("calibration_choice")
            return float(settings["cm_to_px"])
        if selected_mode == "RECALIBRATE":
            cv2.destroyWindow("calibration_choice")
            cm_to_px = calibrate_screen_scale(
                screen_width=screen_width,
                screen_height=screen_height,
                reference_cm=reference_cm,
            )
            save_calibration_settings(cm_to_px, reference_cm=reference_cm, test_distance_m=TEST_DISTANCE_M)
            return cm_to_px

        key = cv2.waitKey(50) & 0xFF
        if key in FORCE_EXIT_KEYS:
            confirm_exit()
        elif key == 13:
            selected_mode = "USE"
        elif key in (ord("r"), ord("R")):
            selected_mode = "RECALIBRATE"

        try:
            if cv2.getWindowProperty("calibration_choice", cv2.WND_PROP_VISIBLE) < 1:
                confirm_exit()
        except cv2.error:
            confirm_exit()



def apply_zoom(frame, zoom_factor):
    """
    カメラ画像の中心を拡大表示する。

    Args:
        frame: カメラ画像。
        zoom_factor: 拡大倍率。

    Returns:
        numpy.ndarray: 拡大後の画像。
    """
    h, w, _ = frame.shape
    center_x, center_y = w // 2, h // 2

    # 中心を基準に切り出し領域を計算する
    new_width = int(w / zoom_factor)
    new_height = int(h / zoom_factor)
    x1 = max(0, center_x - new_width // 2)
    y1 = max(0, center_y - new_height // 2)
    x2 = min(w, center_x + new_width // 2)
    y2 = min(h, center_y + new_height // 2)

    # 切り出した範囲を元サイズにリサイズする
    cropped = frame[y1:y2, x1:x2]
    zoomed_frame = cv2.resize(cropped, (w, h), interpolation=cv2.INTER_LINEAR)
    return zoomed_frame

def countdown_screen(seconds, screen_width, screen_height):
    # フルスクリーンのカウントダウン画面を表示する
    cv2.namedWindow("mainview", cv2.WINDOW_NORMAL)
    cv2.setWindowProperty("mainview", cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

    for i in range(seconds, 0, -1):
        # 白背景を作成する
        image = np.ones((screen_height, screen_width, 3), dtype=np.uint8) * 255

        # 数字を中央に描画する
        text = f"{i}"
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 10
        thickness = 10
        text_size = cv2.getTextSize(text, font, font_scale, thickness)[0]
        text_x = (screen_width - text_size[0]) // 2
        text_y = (screen_height + text_size[1]) // 2

        cv2.putText(image, text, (text_x, text_y), font, font_scale, (0, 0, 0), thickness)

        # カウントダウン画面を表示する
        show_image("mainview", image)

        # 1 秒待機
        wait_with_forced_exit(1000, watch_windows=["mainview"])
    return True

def show_message(message, duration, screen_width, screen_height, font_path="C:/Windows/Fonts/msgothic.ttc", font_size=50):
    """
    指定したメッセージを一定時間フルスクリーン表示する。

    Args:
        message: 表示する文字列。
        duration: 表示時間 [秒]。
        screen_width: 画面幅。
        screen_height: 画面高さ。
        font_path: 日本語フォントのパス。
        font_size: フォントサイズ。
    """
    # 白背景を作成する
    image = np.ones((screen_height, screen_width, 3), dtype=np.uint8) * 255

    # メッセージを描画する
    image = display_japanese_text(image, message, (screen_width // 4, screen_height // 2), font_path=font_path, font_size=font_size, color=(0, 0, 255))

    # 画面表示
    show_image("mainview", image)
    wait_with_forced_exit(duration * 1000, watch_windows=["mainview"])  # 指定秒数だけ待機
# 検査終了後の結果一覧を表示する
def show_results_summary(results_summary, screen_width, screen_height):
    image = np.ones((screen_height, screen_width, 3), dtype=np.uint8) * 255
    y_offset = 100
    font = cv2.FONT_HERSHEY_SIMPLEX

    for result in results_summary:
        text = (f"Test {result['test_number']}: "
                f"Correct: {result['correct_count']}, "
                f"Incorrect: {result['incorrect_count']}, "
                f"Visual Acuity: {result['visual_acuity']:.1f}")
        cv2.putText(image, text, (50, y_offset), font, 1, (0, 0, 0), 2)
        y_offset += 50

        # 途中経過も含めて画面に表示する
        show_image("mainview", image)
        wait_with_forced_exit(10000, watch_windows=["mainview"])  # 10 秒間表示
        
# CSV 保存処理
def save_results_to_csv(user_id, results_summary, filename="vision_results.csv"):
    out_path = app_dir() / filename
    write_header = not out_path.exists()
    with open(out_path, mode="a", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        if write_header:
            writer.writerow(["ID", "Date", "Test Number", "Visual Acuity"])
        current_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for result in results_summary:
            writer.writerow([user_id, current_date, result["test_number"], result["visual_acuity"]])
            
def display_japanese_text(image, text, position, font_path=None, font_size=40, color=(0, 0, 0)):
    """
    OpenCV 画像に日本語テキストを描画する。

    Args:
        image: OpenCV 形式の画像。
        text: 描画するテキスト。
        position: 描画位置 (x, y)。
        font_path: 日本語フォントのパス。
        font_size: フォントサイズ。
        color: 文字色 (B, G, R)。
    Returns:
        日本語テキスト描画後の OpenCV 画像。
    """
    font_candidates = []
    if font_path is not None:
        font_candidates.append(font_path)
    else:
        font_candidates.extend([
            resource_path("meiryo.ttc"),
            "C:/Windows/Fonts/meiryo.ttc",
            "C:/Windows/Fonts/msgothic.ttc",
        ])

    # OpenCV 画像を Pillow 画像へ変換する
    pil_image = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(pil_image)

    # フォント読み込みに失敗した場合はデフォルトフォントへフォールバックする
    font = None
    for candidate in font_candidates:
        try:
            if candidate and Path(candidate).exists():
                font = ImageFont.truetype(candidate, font_size)
                break
        except Exception:
            continue
    if font is None:
        font = ImageFont.load_default()

    # OpenCV の BGR 指定を Pillow 用の RGB に変換する
    rgb_color = (int(color[2]), int(color[1]), int(color[0]))
    draw.text(position, text, font=font, fill=rgb_color)

    # Pillow 画像を OpenCV 画像へ戻す
    return cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)

def restart_program(screen_width=1920, screen_height=1080):
    print("アプリを閉じずに最初の画面へ戻ります。")

    # 再起動画面を表示する
    image = np.ones((screen_height, screen_width, 3), dtype=np.uint8) * 255
    image = display_japanese_text(image, "最初の画面へ戻ります..", (screen_width // 3, screen_height // 2), font_size=60, color=(0, 0, 0))

    cv2.namedWindow("restart_screen", cv2.WINDOW_NORMAL)
    cv2.setWindowProperty("restart_screen", cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
    show_image("restart_screen", image)

    wait_with_forced_exit(100, watch_windows=["restart_screen"])  # 表示を確実に反映するため少し待機

    # 画面を見せたあと、ウィンドウを閉じて呼び出し元へ戻る
    time.sleep(2)
    try:
        cv2.destroyWindow("restart_screen")
    except cv2.error:
        pass
    return


def run_app_session():
    # ID を入力する
    user_id = get_user_id_with_keyboard()
    if user_id is None:
        force_terminate_program()
    else:
        print(f"入力された ID: {user_id}")

    # OpenCV のメイン画面を準備する
    cv2.namedWindow("mainview", cv2.WINDOW_NORMAL)
    cv2.setWindowProperty("mainview", cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
        
    # MediaPipe Hands を初期化する
    mp_hands = mp.solutions.hands
    hands = mp_hands.Hands(min_detection_confidence=0.7, min_tracking_confidence=0.7)
    mp_drawing = mp.solutions.drawing_utils

    # 画面サイズとランドルト環の表示中心
    screen_height, screen_width = 1080, 1920  # 想定する画面サイズ（フル HD）
    center = (screen_width // 2, screen_height // 2)  # 表示中心

    # 保存済み校正値を使うか、再校正するかを選ぶ
    cm_to_px = choose_calibration_scale(screen_width=screen_width, screen_height=screen_height)
    print(f"校正結果: 1 cm = {cm_to_px:.2f} px")

    # 検査距離に応じたランドルト環の外径 [cm] と視力値の対応表を生成する
    fixed_outer_diameters = build_landolt_size_table(test_distance_m=TEST_DISTANCE_M)
    current_index = 0
    desired_outer_diameter_cm, visual_acuity = fixed_outer_diameters[current_index]
    
    # 各検査結果の保存先
    results_summary = []

    for test_number in range(1, 3):  # 左右の目を 2 回に分けて検査する
        if test_number == 1:
            # 立ち位置の案内を表示する
            image = np.ones((screen_height, screen_width, 3), dtype=np.uint8) * 255  # 白背景
            image = display_japanese_text(image, "後ろの立ち位置まで移動してください", (100, 400), font_size=70, color=(255, 0, 0))
            image = display_japanese_text(image, "Please move to a standing position behind you.", (100, 600), font_size=70, color=(255, 0, 0))

            # 画面表示
            show_image("mainview", image)
            wait_with_forced_exit(10000, watch_windows=["mainview"])  # 10 秒間表示
            
            # 左目を隠す案内を表示する
            image = np.ones((screen_height, screen_width, 3), dtype=np.uint8) * 255  # 白背景
            image = display_japanese_text(image, "左目を隠してください", (100, 400), font_size=130, color=(255, 0, 0))
            image = display_japanese_text(image, "Cover your left eye.", (100, 600), font_size=130, color=(255, 0, 0))

            # 画面表示
            show_image("mainview", image)
            wait_with_forced_exit(10000, watch_windows=["mainview"])  # 10 秒間表示
            countdown_screen(5, screen_width, screen_height)

            # 検査開始前の短い待機
            wait_with_forced_exit(1000, watch_windows=["mainview"])


        if test_number == 2:
            print("Starting test 2.")
            # 2 回目の検査前に camera ウィンドウを閉じる
            try:
                cv2.destroyWindow("camera")
                print("camera ウィンドウを閉じました。")
            except cv2.error:
                print("camera ウィンドウは開かれていませんでした。")
            
            # mainview を再設定する
            cv2.namedWindow("mainview", cv2.WINDOW_NORMAL)
            cv2.setWindowProperty("mainview", cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
            print("mainview window configured.")
            
            # MediaPipe Hands を再初期化する
            hands = mp_hands.Hands(min_detection_confidence=0.7, min_tracking_confidence=0.7)
            print("MediaPipe Hands を再初期化しました。")
            
            # ランドルト環のサイズを最初の段階に戻す
            current_index = 0  # 最初のサイズから再開
            desired_outer_diameter_cm, visual_acuity = fixed_outer_diameters[current_index]
            print(f"2 回目の検査は外径 {desired_outer_diameter_cm} cm、視力 {visual_acuity} から開始します。")
            
            # 右目を隠す案内を表示する
            image = np.ones((screen_height, screen_width, 3), dtype=np.uint8) * 255  # 白背景
            image = display_japanese_text(image, "右目を隠してください", (100, 400), font_size=130, color=(255, 0, 0))
            image = display_japanese_text(image, "Cover your right eye.", (100, 600), font_size=130, color=(255, 0, 0))

            # 画面表示
            show_image("mainview", image)
            wait_with_forced_exit(10000, watch_windows=["mainview"])  # 10 秒間表示
            countdown_screen(5, screen_width, screen_height)
            print("Countdown completed.")

        # タイミング制御用の変数
        last_change_time = time.time()
        last_evaluation_time = None
        evaluation_time = 3.0  # 判定までの待機時間（秒）
        blank_time = 0.5      # 空白表示時間（秒）
        is_blank = True       # 初期状態は空白表示
        showing_result = False
        result_text = ""
        result_color = (0, 0, 0)

        # 正答数と誤答数
        correct_count = 0
        incorrect_count = 0

        # カメラを初期化する
        cap, camera_index = open_available_camera()
        zoom_factor = 6  # 拡大倍率
        if cap is None:
            show_message(
                "カメラを起動できません。接続を確認してください。",
                5,
                screen_width,
                screen_height,
                font_size=60,
            )
            force_terminate_program(cap=cap, hands=hands, exit_code=1)
        print(f"検査に使用するカメラ番号: {camera_index}")

        try:
            while cap.isOpened():
                ret, frame = cap.read()
                if not ret:
                    print("Failed to read frame. Exiting.")
                    show_message(
                        "カメラ映像を取得できません。接続を確認してください。",
                        5,
                        screen_width,
                        screen_height,
                        font_size=60,
                    )
                    force_terminate_program(cap=cap, hands=hands, exit_code=1)

                # カメラ画像を拡大する
                frame = apply_zoom(frame, zoom_factor)

                # MediaPipe で手の向きを推定する
                frame = cv2.flip(frame, 1)  # ミラー表示
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                results = hands.process(rgb_frame)

                # 現在の外径と線の太さをピクセルで求める
                outer_diameter_px = int(desired_outer_diameter_cm * cm_to_px)
                thickness_px = int(outer_diameter_px / 5)  # 線の太さは外径の 1/5
                size_error = calculate_landolt_display_error(
                    visual_acuity=visual_acuity,
                    outer_diameter_px=outer_diameter_px,
                    cm_to_px=cm_to_px,
                    test_distance_m=TEST_DISTANCE_M,
                )

                # 現在時刻を取得する
                current_time = time.time()

                # 空白表示と問題表示の切り替え
                if is_blank and current_time - last_change_time >= blank_time:
                    # 空白時間が終わったらランドルト環を表示する
                    is_blank = False
                    showing_result = False
                    last_change_time = current_time
                    current_direction = np.random.choice(["up", "down", "left", "right"])
                    last_evaluation_time = current_time
                elif not is_blank and current_time - last_evaluation_time >= evaluation_time:
                    # 表示時間が経過したら向きを判定する
                    arm_direction = detect_arm_direction(results)
                    if arm_direction == current_direction:
                        correct_count += 1
                        if correct_count >= 2:
                            current_index = min(current_index + 1, len(fixed_outer_diameters) - 1)
                            desired_outer_diameter_cm, visual_acuity = fixed_outer_diameters[current_index]
                            if visual_acuity == 1.0:
                                result_text = "Visual Acuity : 1.0"
                                result_color = (0, 255, 0)  # 緑色
                                image = np.ones((screen_height, screen_width, 3), dtype=np.uint8) * 255
                                font = cv2.FONT_HERSHEY_SIMPLEX
                                font_scale = 3
                                thickness = 5
                                text_size = cv2.getTextSize(result_text, font, font_scale, thickness)[0]
                                x = (image.shape[1] - text_size[0]) // 2
                                y = screen_height * 2 // 3
                                cv2.putText(image, result_text, (x, y), font, font_scale, result_color, thickness)
                                show_image("mainview", image)
                                wait_with_forced_exit(5000, cap=cap, hands=hands, watch_windows=["mainview", "camera"])
                                break
                            correct_count = 0  # 次の段階へ進むので正答数をリセット
                            incorrect_count = 0  # 誤答数もリセット
                            result_text = "PASS"
                            result_color = (0, 255, 0)  # 緑色
                            showing_result = True
                    else:
                        incorrect_count += 1
                        if incorrect_count >= 2:
                            result_text = "NO RESPONSE" if arm_direction is None else "FAIL"
                            result_color = (0, 0, 255)
                            if current_index > 0:
                                previous_diameter, previous_acuity = fixed_outer_diameters[current_index - 1]
                                image = np.ones((screen_height, screen_width, 3), dtype=np.uint8) * 255
                                font = cv2.FONT_HERSHEY_SIMPLEX
                                font_scale = 2
                                thickness = 5
                                text_size = cv2.getTextSize(f"Previous Diameter: {previous_diameter:.2f} cm, Visual Acuity: {previous_acuity:.1f}", font, font_scale, thickness)[0]
                                x = (image.shape[1] - text_size[0]) // 2
                                y = screen_height * 2 // 3
                                cv2.putText(image, f"Previous Diameter: {previous_diameter:.2f} cm, Visual Acuity: {previous_acuity:.1f}", (x, y), font, font_scale, (0, 0, 255), thickness)
                                show_image("mainview", image)
                                wait_with_forced_exit(5000, cap=cap, hands=hands, watch_windows=["mainview", "camera"])  # 5 秒間待機
                            showing_result = True
                            break

                    if showing_result:
                        # 結果表示用の画面を作成する
                        image = np.ones((screen_height, screen_width, 3), dtype=np.uint8) * 255
                        font = cv2.FONT_HERSHEY_SIMPLEX
                        font_scale = 3
                        thickness = 5
                        text_size = cv2.getTextSize(result_text, font, font_scale, thickness)[0]
                        x = (image.shape[1] - text_size[0]) // 2
                        y = screen_height // 2
                        cv2.putText(image, result_text, (x, y), font, font_scale, result_color, thickness)

                        # 正答数・誤答数と現在設定を表示する
                        cv2.putText(image, f"Correct: {correct_count}", (50, 100), font, 1.5, (0, 255, 0), 2)
                        cv2.putText(image, f"Incorrect: {incorrect_count}", (50, 200), font, 1.5, (0, 0, 255), 2)
                        cv2.putText(image, f"Outer Diameter: {desired_outer_diameter_cm:.2f} cm", (50, 300), font, 1.5, (0, 0, 0), 2)
                        cv2.putText(image, f"Visual Acuity: {visual_acuity:.1f}", (50, 400), font, 1.5, (0, 0, 255), 2)
                        cv2.putText(image, f"Theory: {size_error['theoretical_cm']:.3f} cm", (50, 500), font, 1.1, (0, 0, 0), 2)
                        cv2.putText(image, f"Display: {size_error['displayed_cm']:.3f} cm", (50, 560), font, 1.1, (0, 0, 0), 2)
                        cv2.putText(image, f"Error: {size_error['error_mm']:+.2f} mm ({size_error['error_percent']:+.2f}%)", (50, 620), font, 1.1, (180, 0, 0), 2)

                        # 結果を短時間表示する
                        show_image("mainview", image)
                        wait_with_forced_exit(1000, cap=cap, hands=hands, watch_windows=["mainview", "camera"])
                        is_blank = True
                        last_change_time = current_time

                    is_blank = True
                    last_change_time = current_time

                # 毎フレームの表示用背景を作成する
                image = np.ones((screen_height, screen_width, 3), dtype=np.uint8) * 255

                if not is_blank:
                    # 問題表示中はランドルト環を描画する
                    draw_landolt_ring(image, center, outer_diameter_px, thickness_px, current_direction)

                # 画面左上に正答数と誤答数を表示する
                font = cv2.FONT_HERSHEY_SIMPLEX
                cv2.putText(image, f"Correct: {correct_count}", (50, 100), font, 1.5, (0, 255, 0), 2)
                cv2.putText(image, f"Incorrect: {incorrect_count}", (50, 200), font, 1.5, (0, 0, 255), 2)
                cv2.putText(image, f"Theory {size_error['theoretical_cm']:.3f} cm / Display {size_error['displayed_cm']:.3f} cm", (50, 300), font, 1.0, (0, 0, 0), 2)
                cv2.putText(image, f"Error {size_error['error_mm']:+.2f} mm ({size_error['error_percent']:+.2f}%)", (50, 350), font, 1.0, (180, 0, 0), 2)

                # 問題画面を表示する
                show_image("mainview", image)

                # カメラ画像上に MediaPipe のランドマークを重ねる
                if results.multi_hand_landmarks:
                    for hand_landmarks in results.multi_hand_landmarks:
                        mp_drawing.draw_landmarks(frame, hand_landmarks, mp_hands.HAND_CONNECTIONS)

                # カメラ画面を表示する
                cv2.putText(frame, "ESC: Exit", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
                cv2.imshow("camera", frame)

                # 終了キーを監視する
                wait_with_forced_exit(1, cap=cap, hands=hands, watch_windows=["mainview", "camera"])


        finally:
            # リソースを解放する
            try:
                cap.release()
            except Exception:
                pass
            try:
                hands.close()
            except Exception:
                pass
            try:
                cv2.destroyAllWindows()
            except cv2.error:
                pass
    
        # この回の検査結果を保存する
        results_summary.append({
            "test_number": test_number,
            "correct_count": correct_count,
            "incorrect_count": incorrect_count,
            "visual_acuity": visual_acuity
        })
    


    # 両眼の検査が終わったら結果を表示する
    if len(results_summary) == 2:
        show_results_summary(results_summary, screen_width, screen_height)
    
        print("All tests completed. Saving results.")
        
        # CSV に保存する
        save_results_to_csv(user_id, results_summary)
        print("Results saved to CSV.")
        
        # 最後にプログラムを再スタートする
        restart_program(screen_width, screen_height)
        return True

    return True


if __name__ == "__main__":
    while True:
        run_app_session()
