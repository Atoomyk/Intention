"""
Intention — спокойная игра на интуицию.
Режимы: Цвета и Цифры. Доверься ощущению — затем узнай, верно ли.
"""

from __future__ import annotations

import array
import json
import math
import random
from pathlib import Path

import pygame

# ---------------------------------------------------------------------------
# Paths & constants
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent
SAVE_PATH = ROOT / "save.json"

WIDTH, HEIGHT = 900, 640
FPS = 60
BALL_SIZE = 140

BG_TOP = (18, 28, 36)
BG_BOTTOM = (32, 48, 58)
ACCENT = (140, 178, 168)
ACCENT_DIM = (88, 120, 112)
TEXT = (220, 230, 228)
TEXT_DIM = (140, 158, 156)
GOOD = (152, 198, 168)
MISS = (198, 158, 148)
NUMBER_BALL = (52, 72, 82)

COLOR_DEFS = {
    "black": {"rgb": (28, 30, 34), "ru": "Чёрный", "en": "Black"},
    "white": {"rgb": (236, 240, 238), "ru": "Белый", "en": "White"},
    "gray": {"rgb": (128, 138, 142), "ru": "Серый", "en": "Gray"},
}

TEXTS = {
    "title": {"ru": "Intention", "en": "Intention"},
    "subtitle": {"ru": "Доверься интуиции", "en": "Trust your intuition"},
    "play": {"ru": "Играть", "en": "Play"},
    "settings": {"ru": "Настройки", "en": "Settings"},
    "quit": {"ru": "Выход", "en": "Quit"},
    "back": {"ru": "Назад", "en": "Back"},
    "mode": {"ru": "Режим", "en": "Mode"},
    "mode_colors": {"ru": "Цвета", "en": "Colors"},
    "mode_numbers": {"ru": "Цифры", "en": "Numbers"},
    "colors": {"ru": "Цвета", "en": "Colors"},
    "colors_2": {"ru": "2 цвета", "en": "2 colors"},
    "colors_3": {"ru": "3 цвета", "en": "3 colors"},
    "number_max": {"ru": "Диапазон", "en": "Range"},
    "language": {"ru": "Язык", "en": "Language"},
    "sound": {"ru": "Звук", "en": "Sound"},
    "on": {"ru": "Вкл", "en": "On"},
    "off": {"ru": "Выкл", "en": "Off"},
    "prompt_color": {"ru": "Какого цвета шарик?", "en": "What color is the ball?"},
    "prompt_number": {"ru": "Какая цифра?", "en": "What number?"},
    "hint": {"ru": "Почувствуй — и выбери", "en": "Feel it — then choose"},
    "match": {"ru": "Верно!", "en": "Correct!"},
    "no_match": {"ru": "Не верно!", "en": "Wrong!"},
    "streak": {"ru": "Серия", "en": "Streak"},
    "best": {"ru": "Рекорд серии", "en": "Best streak"},
    "accuracy": {"ru": "Точность", "en": "Accuracy"},
    "best_acc": {"ru": "Рекорд точности", "en": "Best accuracy"},
    "to_menu": {"ru": "В меню", "en": "To menu"},
}


def t(key: str, lang: str) -> str:
    entry = TEXTS.get(key, {})
    return entry.get(lang, entry.get("en", key))


def color_name(key: str, lang: str) -> str:
    return COLOR_DEFS[key][lang]


def empty_record() -> dict:
    return {"best_streak": 0, "best_accuracy": 0.0}


def default_records() -> dict:
    return {
        "colors": {str(n): empty_record() for n in (2, 3)},
        "numbers": {str(n): empty_record() for n in range(2, 11)},
    }


DEFAULT_SAVE = {
    "lang": "ru",
    "mode": "colors",
    "color_count": 2,
    "number_max": 5,
    "sound": True,
    "records": default_records(),
}


def _normalize_records(raw: object) -> dict:
    base = default_records()
    if not isinstance(raw, dict):
        return base
    for mode in ("colors", "numbers"):
        section = raw.get(mode, {})
        if not isinstance(section, dict):
            continue
        for key, rec in section.items():
            if key not in base[mode] or not isinstance(rec, dict):
                continue
            base[mode][key] = {
                "best_streak": int(rec.get("best_streak", 0)),
                "best_accuracy": float(rec.get("best_accuracy", 0.0)),
            }
    return base


def load_save() -> dict:
    if SAVE_PATH.exists():
        try:
            data = json.loads(SAVE_PATH.read_text(encoding="utf-8"))
            merged = {**DEFAULT_SAVE, **data}
            merged["mode"] = "numbers" if merged.get("mode") == "numbers" else "colors"
            merged["color_count"] = 3 if int(merged.get("color_count", 2)) == 3 else 2
            nmax = int(merged.get("number_max", 5))
            merged["number_max"] = min(10, max(2, nmax))
            merged["lang"] = "en" if merged.get("lang") == "en" else "ru"
            merged["sound"] = bool(merged.get("sound", True))
            merged["records"] = _normalize_records(merged.get("records"))

            # migrate legacy flat records into colors/2 if empty
            legacy_streak = int(data.get("best_streak", 0) or 0)
            legacy_acc = float(data.get("best_accuracy", 0) or 0)
            c2 = merged["records"]["colors"]["2"]
            if legacy_streak > c2["best_streak"]:
                c2["best_streak"] = legacy_streak
            if legacy_acc > c2["best_accuracy"]:
                c2["best_accuracy"] = legacy_acc
            return merged
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            pass
    return {
        **DEFAULT_SAVE,
        "records": default_records(),
    }


def write_save(data: dict) -> None:
    payload = {
        "lang": data["lang"],
        "mode": data["mode"],
        "color_count": int(data["color_count"]),
        "number_max": int(data["number_max"]),
        "sound": bool(data["sound"]),
        "records": _normalize_records(data.get("records")),
    }
    # round accuracies
    for mode in payload["records"]:
        for key, rec in payload["records"][mode].items():
            rec["best_accuracy"] = round(float(rec["best_accuracy"]), 1)
    SAVE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Soft procedural sounds
# ---------------------------------------------------------------------------

def _tone(freq: float, ms: int, volume: float = 0.22, sample_rate: int = 22050) -> pygame.mixer.Sound:
    n = int(sample_rate * ms / 1000)
    buf = array.array("h")
    attack = max(1, int(sample_rate * 0.02))
    release = max(1, int(sample_rate * 0.12))
    for i in range(n):
        env = min(i / attack, 1.0) * min((n - i) / release, 1.0)
        sample = int(volume * env * 32767.0 * math.sin(2 * math.pi * freq * (i / sample_rate)))
        buf.append(sample)
    return pygame.mixer.Sound(buffer=buf.tobytes())


class Sounds:
    def __init__(self) -> None:
        self.enabled = True
        self.click = _tone(420, 70, 0.14)
        self.match = _tone(523, 220, 0.18)
        self.miss = _tone(196, 260, 0.14)
        self.hover = _tone(360, 40, 0.08)

    def play(self, sound: pygame.mixer.Sound) -> None:
        if self.enabled:
            sound.play()


# ---------------------------------------------------------------------------
# Drawing helpers
# ---------------------------------------------------------------------------

def draw_vertical_gradient(surface: pygame.Surface, top: tuple, bottom: tuple) -> None:
    for y in range(HEIGHT):
        k = y / (HEIGHT - 1)
        r = int(top[0] + (bottom[0] - top[0]) * k)
        g = int(top[1] + (bottom[1] - top[1]) * k)
        b = int(top[2] + (bottom[2] - top[2]) * k)
        pygame.draw.line(surface, (r, g, b), (0, y), (WIDTH, y))


def blit_text(
    surface: pygame.Surface,
    text: str,
    font: pygame.font.Font,
    color: tuple,
    center: tuple[int, int] | None = None,
    topleft: tuple[int, int] | None = None,
    alpha: int = 255,
) -> pygame.Rect:
    img = font.render(text, True, color)
    if alpha < 255:
        img = img.copy()
        img.set_alpha(alpha)
    rect = img.get_rect()
    if center:
        rect.center = center
    if topleft:
        rect.topleft = topleft
    surface.blit(img, rect)
    return rect


def draw_soft_rect(
    surface: pygame.Surface,
    rect: pygame.Rect,
    fill: tuple[int, int, int, int],
    radius: int = 18,
    border: tuple[int, int, int] | None = None,
) -> None:
    panel = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
    pygame.draw.rect(panel, fill, panel.get_rect(), border_radius=radius)
    if border:
        pygame.draw.rect(panel, (*border, 90), panel.get_rect(), width=1, border_radius=radius)
    surface.blit(panel, rect.topleft)


def draw_ball(
    surface: pygame.Surface,
    center: tuple[int, int],
    color_key: str,
    size: int = BALL_SIZE,
    highlight: bool = False,
) -> None:
    fill = (*COLOR_DEFS[color_key]["rgb"], 255)
    glow = 1.06 if highlight else 1.0
    r = pygame.Rect(0, 0, int(size * glow), int(size * glow))
    r.center = center
    ball = pygame.Surface((r.w, r.h), pygame.SRCALPHA)
    pygame.draw.ellipse(ball, fill, ball.get_rect())
    rim = (255, 255, 255, 50) if color_key != "white" else (0, 0, 0, 40)
    pygame.draw.ellipse(ball, rim, ball.get_rect(), width=2)
    if highlight:
        pygame.draw.ellipse(ball, (*GOOD, 120), ball.get_rect().inflate(8, 8), width=2)
    surface.blit(ball, r.topleft)


def draw_number_ball(
    surface: pygame.Surface,
    center: tuple[int, int],
    number: int,
    font: pygame.font.Font,
    size: int = BALL_SIZE,
    highlight: bool = False,
) -> None:
    glow = 1.06 if highlight else 1.0
    r = pygame.Rect(0, 0, int(size * glow), int(size * glow))
    r.center = center
    ball = pygame.Surface((r.w, r.h), pygame.SRCALPHA)
    pygame.draw.ellipse(ball, (*NUMBER_BALL, 255), ball.get_rect())
    pygame.draw.ellipse(ball, (255, 255, 255, 50), ball.get_rect(), width=2)
    if highlight:
        pygame.draw.ellipse(ball, (*GOOD, 120), ball.get_rect().inflate(8, 8), width=2)
    surface.blit(ball, r.topleft)
    blit_text(surface, str(number), font, TEXT, center=center)


# ---------------------------------------------------------------------------
# UI button
# ---------------------------------------------------------------------------

class Button:
    def __init__(
        self,
        rect: pygame.Rect,
        label: str,
        kind: str = "text",
        color_key: str | None = None,
        number_value: int | None = None,
    ) -> None:
        self.rect = rect
        self.label = label
        self.kind = kind
        self.color_key = color_key
        self.number_value = number_value
        self.hover = False
        self._was_hover = False

    def update_hover(self, mouse: tuple[int, int], sounds: Sounds) -> None:
        self.hover = self.rect.collidepoint(mouse)
        if self.hover and not self._was_hover:
            sounds.play(sounds.hover)
        self._was_hover = self.hover

    def draw(self, surface: pygame.Surface, fonts: dict, highlight: bool = False) -> None:
        if self.kind == "swatch" and self.color_key:
            rgb = COLOR_DEFS[self.color_key]["rgb"]
            panel = pygame.Surface((self.rect.w, self.rect.h), pygame.SRCALPHA)
            pygame.draw.rect(panel, (*rgb, 255), panel.get_rect(), border_radius=12)
            if self.hover or highlight:
                pygame.draw.rect(panel, (*ACCENT, 220), panel.get_rect(), width=3, border_radius=12)
            elif self.color_key == "white":
                pygame.draw.rect(panel, (0, 0, 0, 50), panel.get_rect(), width=1, border_radius=12)
            else:
                pygame.draw.rect(panel, (255, 255, 255, 45), panel.get_rect(), width=1, border_radius=12)
            surface.blit(panel, self.rect.topleft)
            return

        if self.kind == "number":
            fill = (255, 255, 255, 42 if (self.hover or highlight) else 24)
            draw_soft_rect(
                surface,
                self.rect,
                fill,
                radius=12,
                border=ACCENT if (self.hover or highlight) else ACCENT_DIM,
            )
            blit_text(surface, self.label, fonts["ui"], TEXT, center=self.rect.center)
            return

        fill = (255, 255, 255, 38 if self.hover else 22)
        draw_soft_rect(surface, self.rect, fill, radius=16, border=ACCENT if self.hover else ACCENT_DIM)
        blit_text(surface, self.label, fonts["ui"], TEXT, center=self.rect.center)


# ---------------------------------------------------------------------------
# Game
# ---------------------------------------------------------------------------

class Game:
    def __init__(self) -> None:
        pygame.init()
        pygame.mixer.init(frequency=22050, size=-16, channels=1, buffer=512)
        pygame.display.set_caption("Intention")
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        self.clock = pygame.time.Clock()
        self.fonts = self._load_fonts()
        self.sounds = Sounds()
        self.save = load_save()
        self.sounds.enabled = self.save["sound"]

        self.state = "menu"
        self.streak = 0
        self.session_rounds = 0
        self.session_matches = 0
        self.true_answer: str | int | None = None
        self.chosen_answer: str | int | None = None
        self.matched: bool | None = None
        self.reveal_t = 0.0
        self.reveal_hold = 0.0
        self.buttons: list[Button] = []
        self._build_menu()

    def _load_fonts(self) -> dict:
        candidates = ["Segoe UI", "Calibri", "Arial"]
        name = pygame.font.get_default_font()
        for c in candidates:
            path = pygame.font.match_font(c)
            if path:
                name = path
                break
        return {
            "title": pygame.font.Font(name, 64),
            "subtitle": pygame.font.Font(name, 24),
            "ui": pygame.font.Font(name, 26),
            "small": pygame.font.Font(name, 18),
            "huge": pygame.font.Font(name, 48),
            "stat": pygame.font.Font(name, 20),
            "ball_num": pygame.font.Font(name, 72),
        }

    @property
    def lang(self) -> str:
        return self.save["lang"]

    @property
    def mode(self) -> str:
        return self.save["mode"]

    def record_key(self) -> str:
        if self.mode == "numbers":
            return str(self.save["number_max"])
        return str(self.save["color_count"])

    def current_record(self) -> dict:
        return self.save["records"][self.mode][self.record_key()]

    def pool(self) -> list:
        if self.mode == "numbers":
            n = int(self.save["number_max"])
            return list(range(1, n + 1))
        if self.save["color_count"] == 3:
            return ["black", "white", "gray"]
        return ["black", "white"]

    def accuracy(self) -> float:
        if self.session_rounds <= 0:
            return 0.0
        return 100.0 * self.session_matches / self.session_rounds

    def _update_records(self) -> None:
        rec = self.current_record()
        if self.streak > rec["best_streak"]:
            rec["best_streak"] = self.streak
        if self.session_rounds > 0:
            acc = self.accuracy()
            if acc > rec["best_accuracy"]:
                rec["best_accuracy"] = acc

    def reset_session(self) -> None:
        self.streak = 0
        self.session_rounds = 0
        self.session_matches = 0

    # ----- screens / buttons -------------------------------------------------

    def _build_menu(self) -> None:
        cx, cy = WIDTH // 2, HEIGHT // 2 + 40
        self.buttons = [
            Button(pygame.Rect(cx - 120, cy - 30, 240, 54), t("play", self.lang)),
            Button(pygame.Rect(cx - 120, cy + 40, 240, 54), t("settings", self.lang)),
            Button(pygame.Rect(cx - 120, cy + 110, 240, 54), t("quit", self.lang)),
        ]
        self._menu_actions = ["play", "settings", "quit"]

    def _build_settings(self) -> None:
        cx = WIDTH // 2
        self.buttons = [
            Button(pygame.Rect(cx - 170, 150, 150, 48), t("mode_colors", self.lang)),
            Button(pygame.Rect(cx + 20, 150, 150, 48), t("mode_numbers", self.lang)),
        ]
        self._settings_actions = ["mode_colors", "mode_numbers"]

        if self.mode == "colors":
            self.buttons += [
                Button(pygame.Rect(cx - 170, 250, 150, 48), t("colors_2", self.lang)),
                Button(pygame.Rect(cx + 20, 250, 150, 48), t("colors_3", self.lang)),
            ]
            self._settings_actions += ["c2", "c3"]
        else:
            self.buttons += [
                Button(pygame.Rect(cx - 170, 250, 70, 48), "−"),
                Button(pygame.Rect(cx - 80, 250, 160, 48), f"1 … {self.save['number_max']}"),
                Button(pygame.Rect(cx + 100, 250, 70, 48), "+"),
            ]
            self._settings_actions += ["n_minus", "n_label", "n_plus"]

        self.buttons += [
            Button(pygame.Rect(cx - 120, 340, 240, 48), "RU / EN"),
            Button(
                pygame.Rect(cx - 120, 400, 240, 48),
                f"{t('sound', self.lang)}: {t('on' if self.save['sound'] else 'off', self.lang)}",
            ),
            Button(pygame.Rect(cx - 120, 480, 240, 54), t("back", self.lang)),
        ]
        self._settings_actions += ["lang", "sound", "back"]

    def _build_play_buttons(self) -> None:
        keys = self.pool()
        n = len(keys)
        gap = 10 if n >= 8 else 14
        max_w = WIDTH - 48
        w = min(150, (max_w - (n - 1) * gap) // n)
        h = 58
        total = n * w + (n - 1) * gap
        x0 = WIDTH // 2 - total // 2
        y = HEIGHT - 158
        self.buttons = []
        self._play_actions = keys

        if self.mode == "numbers":
            for i, num in enumerate(keys):
                rect = pygame.Rect(x0 + i * (w + gap), y, w, h)
                self.buttons.append(
                    Button(rect, str(num), kind="number", number_value=int(num))
                )
        else:
            for i, key in enumerate(keys):
                rect = pygame.Rect(x0 + i * (w + gap), y, w, h)
                self.buttons.append(
                    Button(rect, color_name(key, self.lang), kind="swatch", color_key=key)
                )

        self.buttons.append(
            Button(pygame.Rect(WIDTH // 2 - 100, HEIGHT - 78, 200, 48), t("to_menu", self.lang))
        )
        self._menu_btn_index = n

    def end_game(self) -> None:
        self._update_records()
        write_save(self.save)
        self.reset_session()
        self.state = "menu"
        self._build_menu()

    def start_game(self) -> None:
        self.reset_session()
        self.start_round()

    def start_round(self) -> None:
        self.state = "play"
        self.true_answer = random.choice(self.pool())
        self.chosen_answer = None
        self.matched = None
        self.reveal_t = 0.0
        self.reveal_hold = 0.0
        self._build_play_buttons()

    def choose(self, answer: str | int) -> None:
        self.chosen_answer = answer
        self.matched = answer == self.true_answer
        self.session_rounds += 1
        if self.matched:
            self.streak += 1
            self.session_matches += 1
            self.sounds.play(self.sounds.match)
        else:
            self.streak = 0
            self.sounds.play(self.sounds.miss)
        self._update_records()
        write_save(self.save)
        self.state = "reveal"
        self.reveal_t = 0.0
        self.reveal_hold = 0.0
        self._build_play_buttons()

    # ----- event handling ----------------------------------------------------

    def handle_events(self) -> bool:
        mouse = pygame.mouse.get_pos()
        for btn in self.buttons:
            btn.update_hover(mouse, self.sounds)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                if self.state in ("play", "reveal"):
                    self.end_game()
                elif self.state == "settings":
                    write_save(self.save)
                    self.state = "menu"
                    self._build_menu()
                else:
                    return False
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self._on_click(event.pos)
        return True

    def _on_click(self, pos: tuple[int, int]) -> None:
        for i, btn in enumerate(self.buttons):
            if not btn.rect.collidepoint(pos):
                continue
            self.sounds.play(self.sounds.click)
            if self.state == "menu":
                action = self._menu_actions[i]
                if action == "play":
                    self.start_game()
                elif action == "settings":
                    self.state = "settings"
                    self._build_settings()
                elif action == "quit":
                    pygame.event.post(pygame.event.Event(pygame.QUIT))
            elif self.state == "settings":
                action = self._settings_actions[i]
                if action == "mode_colors":
                    self.save["mode"] = "colors"
                elif action == "mode_numbers":
                    self.save["mode"] = "numbers"
                elif action == "c2":
                    self.save["color_count"] = 2
                elif action == "c3":
                    self.save["color_count"] = 3
                elif action == "n_minus":
                    self.save["number_max"] = max(2, int(self.save["number_max"]) - 1)
                elif action == "n_plus":
                    self.save["number_max"] = min(10, int(self.save["number_max"]) + 1)
                elif action == "n_label":
                    pass
                elif action == "lang":
                    self.save["lang"] = "en" if self.save["lang"] == "ru" else "ru"
                elif action == "sound":
                    self.save["sound"] = not self.save["sound"]
                    self.sounds.enabled = self.save["sound"]
                elif action == "back":
                    write_save(self.save)
                    self.state = "menu"
                    self._build_menu()
                    return
                write_save(self.save)
                self._build_settings()
            elif self.state == "play":
                if i == self._menu_btn_index:
                    self.end_game()
                else:
                    self.choose(self._play_actions[i])
            elif self.state == "reveal":
                if i == self._menu_btn_index:
                    self.end_game()
            return

    # ----- drawing -----------------------------------------------------------

    def draw_stats_bar(self) -> None:
        rec = self.current_record()
        acc = self.accuracy()
        best_acc = float(rec["best_accuracy"])
        mode_tag = t("mode_numbers", self.lang) if self.mode == "numbers" else t("mode_colors", self.lang)
        if self.mode == "numbers":
            scope = f"1…{self.save['number_max']}"
        else:
            scope = t("colors_3" if self.save["color_count"] == 3 else "colors_2", self.lang)

        if self.state in ("play", "reveal"):
            line = (
                f"{mode_tag} {scope}   ·   "
                f"{t('streak', self.lang)}: {self.streak}   ·   "
                f"{t('accuracy', self.lang)}: {acc:.0f}%   ·   "
                f"{t('best', self.lang)}: {rec['best_streak']}   ·   "
                f"{t('best_acc', self.lang)}: {best_acc:.0f}%"
            )
        else:
            line = (
                f"{mode_tag} {scope}   ·   "
                f"{t('best', self.lang)}: {rec['best_streak']}   ·   "
                f"{t('best_acc', self.lang)}: {best_acc:.0f}%"
            )
        blit_text(self.screen, line, self.fonts["stat"], TEXT_DIM, center=(WIDTH // 2, 36))

    def draw_menu(self) -> None:
        self.draw_stats_bar()
        blit_text(self.screen, t("title", self.lang), self.fonts["title"], TEXT, center=(WIDTH // 2, 150))
        blit_text(self.screen, t("subtitle", self.lang), self.fonts["subtitle"], ACCENT, center=(WIDTH // 2, 210))
        for btn in self.buttons:
            btn.draw(self.screen, self.fonts)

    def draw_settings(self) -> None:
        blit_text(self.screen, t("settings", self.lang), self.fonts["huge"], TEXT, center=(WIDTH // 2, 70))
        blit_text(self.screen, t("mode", self.lang), self.fonts["small"], TEXT_DIM, center=(WIDTH // 2, 125))
        if self.mode == "colors":
            blit_text(self.screen, t("colors", self.lang), self.fonts["small"], TEXT_DIM, center=(WIDTH // 2, 225))
        else:
            blit_text(self.screen, t("number_max", self.lang), self.fonts["small"], TEXT_DIM, center=(WIDTH // 2, 225))

        for i, btn in enumerate(self.buttons):
            btn.draw(self.screen, self.fonts)
            action = self._settings_actions[i]
            active = (
                (action == "mode_colors" and self.mode == "colors")
                or (action == "mode_numbers" and self.mode == "numbers")
                or (action == "c2" and self.save["color_count"] == 2)
                or (action == "c3" and self.save["color_count"] == 3)
            )
            if active:
                pygame.draw.rect(self.screen, ACCENT, btn.rect.inflate(6, 6), 2, border_radius=18)

        lang_label = f"{t('language', self.lang)}: {'Русский' if self.lang == 'ru' else 'English'}"
        blit_text(self.screen, lang_label, self.fonts["small"], TEXT_DIM, center=(WIDTH // 2, 315))

    def draw_play(self) -> None:
        self.draw_stats_bar()
        prompt = t("prompt_number" if self.mode == "numbers" else "prompt_color", self.lang)
        blit_text(self.screen, prompt, self.fonts["ui"], TEXT, center=(WIDTH // 2, 120))
        blit_text(self.screen, t("hint", self.lang), self.fonts["small"], TEXT_DIM, center=(WIDTH // 2, 160))
        for btn in self.buttons:
            btn.draw(self.screen, self.fonts)

    def draw_reveal(self) -> None:
        self.draw_stats_bar()
        dt_ms = self.clock.get_time()
        self.reveal_t = min(1.0, self.reveal_t + dt_ms / 500.0)

        label = t("match", self.lang) if self.matched else t("no_match", self.lang)
        color = GOOD if self.matched else MISS
        blit_text(self.screen, label, self.fonts["huge"], color, center=(WIDTH // 2, 100))

        center = (WIDTH // 2, HEIGHT // 2 - 20)
        if self.mode == "numbers" and isinstance(self.true_answer, int):
            draw_number_ball(
                self.screen,
                center,
                self.true_answer,
                self.fonts["ball_num"],
                size=BALL_SIZE,
                highlight=bool(self.matched),
            )
        elif isinstance(self.true_answer, str):
            draw_ball(
                self.screen,
                center,
                self.true_answer,
                size=BALL_SIZE,
                highlight=bool(self.matched),
            )
            blit_text(
                self.screen,
                color_name(self.true_answer, self.lang),
                self.fonts["small"],
                TEXT_DIM,
                center=(WIDTH // 2, center[1] + BALL_SIZE // 2 + 28),
            )

        for btn in self.buttons:
            if self.mode == "numbers":
                is_chosen = btn.number_value is not None and btn.number_value == self.chosen_answer
            else:
                is_chosen = btn.color_key is not None and btn.color_key == self.chosen_answer
            btn.draw(self.screen, self.fonts, highlight=bool(is_chosen))

        if self.reveal_t >= 1.0:
            self.reveal_hold += dt_ms / 1000.0
            if self.reveal_hold >= 0.9:
                self.start_round()

    def draw(self) -> None:
        draw_vertical_gradient(self.screen, BG_TOP, BG_BOTTOM)
        if self.state == "menu":
            self.draw_menu()
        elif self.state == "settings":
            self.draw_settings()
        elif self.state == "play":
            self.draw_play()
        elif self.state == "reveal":
            self.draw_reveal()
        pygame.display.flip()

    def run(self) -> None:
        running = True
        while running:
            self.clock.tick(FPS)
            running = self.handle_events()
            self.draw()
        write_save(self.save)
        pygame.quit()


def main() -> None:
    Game().run()


if __name__ == "__main__":
    main()
