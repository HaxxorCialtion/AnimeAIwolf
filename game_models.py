# game_models.py

from enum import Enum

class Role(Enum):
    VILLAGER = "村民"
    WEREWOLF = "狼人"
    SEER = "预言家"  # <-- 新增

class GamePhase(Enum):
    WAITING = "waiting"
    PRE_GAME_SEER = "pre_game_seer"  # <-- 新增：游戏开始前的预言家预演阶段
    NIGHT_SEER = "night_seer"
    NIGHT_WEREWOLF = "night_werewolf"
    DAY = "day"
    DISCUSSION = "discussion"
    VOTING = "voting"
    ENDED = "ended"

class GameError(Exception):
    """游戏自定义错误异常类"""
    pass