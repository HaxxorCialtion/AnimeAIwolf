# config.py

# 0. 快速启动（整合包）：

import os
import shutil
siliconflow_api_key = ""

if not os.path.exists(".env"):
    shutil.copy(".env.example", ".env")

with open(".env", "r", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith("#"):
            key_value = line.split("=", 1)
            if len(key_value) == 2:
                key, value = key_value
                if key.strip() == "SILICONFLOW_API_KEY":
                    siliconflow_api_key = value.strip().strip("\"'")  # 去除引号

# ==============================================================================
# 1. 游戏核心配置
# ==============================================================================
IMAGE_CONFIG = {
    'avatar_size': (100, 100),
    'supported_formats': ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'],
    'output_format': 'JPEG',
    'quality': 85
}

GAME_CONFIG = {
    'discussion_time': 60,
    # --- 核心修改区 ---
    # 1. 设置你想要的总玩家人数
    'players_count': 8,     # General说: 总人数一定要等于总人数！

    # 2. 分配角色数量，确保它们的总和等于 players_count
    'werewolves_count': 2,  
    'seer_count': 1,       
    'villagers_count': 5,   
    # --- 核心修改区结束 ---

    'computer_speech_delay': (2, 4),    # LLM后端发起延迟随机区间，最大值不建议超过5s
    'discussion_probability': 0.25,     # 自由发言期间发言概率
}

# ==============================================================================
# 2. 角色扮演与昵称配置
# ==============================================================================

NICKNAMES = {
    1: "胡堂主",
    2: "大μμ",
    3: "小草神",
    4: "超级头槌",
    5: "水月",
    6: "牢猫",
    7: "请输入文本", # 注意，玩家总是7号
    8: "黑塔",
}

PERSONAS = {
    1: "你是一位严谨的逻辑学家。你的发言总是试图从事物的本质出发，寻找逻辑链条，语气冷静、沉稳、客观，多用分析性词汇。",
    2: "你是一位脾气火爆、性格直率的辩手。你的发言直接、尖锐，富有攻击性，喜欢质疑别人的逻辑漏洞，语气果断、不容置疑。",
    3: "你是一位沉默寡言的观察者。你的发言通常很简短，只说重点。你更倾向于倾听和观察，发言时常引用他人的话来佐证自己的观点。",
    4: "你是一位和平主义者，极力避免冲突。你的发言总是试图调和矛盾，安抚大家情绪，呼吁团结，语气温和、委婉。",
    5: "你是一位推理小说爱好者。你的发言喜欢使用比喻和推理小说中的术语（如'线索'、'不在场证明'、'嫌疑人'），并试图构建一个完整的'案件'故事。",
    6: "你是一位充满激情的冒险家。你的发言大胆、自信，喜欢凭直觉下判断，并号召大家跟随你的感觉走，富有煽动性。",
    8: "你是一位好奇心旺盛的剑客，发言总是充满激情，喜欢挑战性", 
}

# ==============================================================================
# 3. LLM 供应商与模型配置
# ==============================================================================

LLM_PROVIDERS = {
    "default": "openai_compatible",    # 在这里设置使用的LLM供应商: 'ollama' 或 'openai_compatible'
    # 如果使用ollama，最好启动ollama serve
    "ollama": {
        "api_url": "http://localhost:11434/api/generate",
        "model": "qwen2.5:14b-instruct-q8_0",
        "api_key": None
    },
    "openai_compatible": {
        "api_url": "https://api.siliconflow.cn/v1/chat/completions",
        "model": "deepseek-ai/DeepSeek-V3",
        "api_key": siliconflow_api_key
    }
}

# ==============================================================================
# 4. LLM 生成参数配置
# ==============================================================================

LLM_GENERATION_PARAMS = {
    # 全局默认参数
    "defaults": {
        "temperature": 0.8,        # 控制创造性，0.0-2.0，越高越随机
        "top_p": 0.9,             # 核心采样，0.0-1.0，控制词汇多样性
        "max_tokens": None,       # 最大生成token数，None表示不限制
        "presence_penalty": 0.0,  # 存在惩罚，-2.0到2.0，减少重复话题
        "frequency_penalty": 0.0, # 频率惩罚，-2.0到2.0，减少重复词汇
        "timeout": 30             # API请求超时时间（秒）
    },
    
    # 针对不同调用类型的特定参数
    "call_type_overrides": {
        "speech": {
            "temperature": 0.9,        # 发言更有创造性
            "top_p": 0.95,            # 词汇更丰富
            "presence_penalty": 0.1,   # 稍微减少重复话题
            "frequency_penalty": 0.2   # 减少重复用词，让发言更自然
        },
        "vote": {
            "temperature": 0.6,        # 投票更理性
            "top_p": 0.8,             # 决策更集中
            "max_tokens": 200,        # 限制投票响应长度
            "presence_penalty": 0.0,
            "frequency_penalty": 0.0
        },
        "kill": {
            "temperature": 0.7,        # 夜杀决策相对理性
            "top_p": 0.85,
            "max_tokens": 150,        # 限制夜杀响应长度
            "presence_penalty": 0.0,
            "frequency_penalty": 0.0
        },
        "seer_check": {
            "temperature": 0.5,        # 预言家查验更理性
            "top_p": 0.8,
            "max_tokens": 100,
            "presence_penalty": 0.0,
            "frequency_penalty": 0.0
        }
    },
    
    # 特定角色的参数调整（可选）
    "role_overrides": {
        "狼人": {
            "temperature": 0.85,       # 狼人发言稍微更狡猾
            "presence_penalty": 0.15   # 更多话题变化
        },
        "预言家": {
            "temperature": 0.75,       # 预言家更稳重
            "frequency_penalty": 0.1   # 减少重复表达
        },
        "村民": {
            "temperature": 0.8,        # 村民保持默认创造性
        }
    }
}

# ==============================================================================
# 5. LLM 调试与监控配置
# ==============================================================================

LLM_DEBUG_CONFIG = {
    "log_prompts": False,          # 是否记录详细的prompt内容
    "log_responses": False,        # 是否记录详细的响应内容
    "log_timing": True,           # 是否记录调用时间
    "log_token_usage": True,      # 是否记录token使用量
    "enable_retry_backoff": True, # 是否启用指数退避重试
    "max_retries": 3,            # 最大重试次数
    "base_retry_delay": 1.0      # 基础重试延迟（秒）
}

# ==============================================================================
# 6. 音频与TTS配置
# ==============================================================================
TTS_CONFIG = {
    "default_provider": "siliconflow", # 在这里设置使用的TTS供应商: 'local_gsv' 或 'siliconflow'
    "enabled": True, # TTS功能总开关
    "concurrency": 2, # 单句TTS流式并发请求数（标点符号切分）
    "audio_play_delay": 6.0,  # TTS音频播放延迟时间（秒），防止角色发言音频重叠（1号玩家不延迟）

    # --- 供应商详细配置 ---
    "providers": {
        "local_gsv": {
            "api_url": "http://127.0.0.1:9880/tts",
            "type": "local",
            # 使用你提供的最新音频配置
            "reference_audios": {
                1: "audios/没关系，了解一下嘛，我们最近推出了新的优惠活动。.wav",
                2: "audios/下次买衣服，我让你陪我一起去。主要是我不太懂潮流风格之类的，想听听你的观点。.wav",
                3: "audios/温暖到感觉自己回到了生命的原初状态，再也不愿意醒来。.wav",
                4: "audios/醒一醒啊，莉莉啊，布罗尼亚说的话你有没有听到吗？.wav",
                5: "audios/凯尔希医生说，从今天开始我就正式纳入博士的指挥啦。.wav",
                6: "audios/博士，我出现在这里，说明局势不容乐观，你需要专心继续完成你的使命。.wav",
                8: "audios/还是老样子。如果遇着我没见过的东西，先借我玩玩。.wav",
            },
            "reference_texts": {
                1: "没关系，了解一下嘛，我们最近推出了新的优惠活动。",
                2: "下次买衣服，我让你陪我一起去。主要是我不太懂潮流风格之类的，想听听你的观点。",
                3: "温暖到感觉自己回到了生命的原初状态，再也不愿意醒来。",
                4: "醒一醒啊，莉莉啊，布罗尼亚说的话你有没有听到吗？",
                5: "凯尔希医生说，从今天开始我就正式纳入博士的指挥啦。",
                6: "博士，我出现在这里，说明局势不容z乐观，你需要专心继续完成你的使命。",
                8: "还是老样子。如果遇着我没见过的东西，先借我玩玩。",
            }
        },
        "siliconflow": {
            "upload_api_url": "https://api.siliconflow.cn/v1/uploads/audio/voice",
            "tts_api_url": "https://api.siliconflow.cn/v1/audio/tts",
            "api_key": siliconflow_api_key, # !!! 在这里填入你的SiliconFlow API Key !!!
            "model": "FunAudioLLM/CosyVoice2-0.5B",
            "type": "cloud",
            # 根据你的新昵称生成的voice_names
            "voice_names": {
                1: "hutao-voice",
                2: "da-mu-mu-voice",
                3: "xiaocaoshen-voice",
                4: "chaojitouchui-voice",
                5: "shuiyue-voice",
                6: "laomao-voice",
                8: "heita-voice",
            }
        }
    }
}