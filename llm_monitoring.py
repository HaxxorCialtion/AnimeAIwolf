# llm_monitoring.py

import json
import logging
from datetime import datetime

LOG_FILE = 'llm_calls.jsonl'

def log_llm_call(call_type: str, player_id: int, prompt: str, response_data: dict, duration_ms: float):
    """
    将一次完整的LLM调用信息记录到日志文件中。

    :param call_type: 调用类型 ('speech' 或 'vote')
    :param player_id: 发起调用的玩家ID
    :param prompt: 发送给LLM的完整Prompt
    :param response_data: 从Ollama收到的完整JSON响应
    :param duration_ms: 调用耗时（毫秒）
    """
    try:
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "call_type": call_type,
            "player_id": player_id,
            "duration_ms": round(duration_ms, 2),
            "usage": {
                "prompt_tokens": response_data.get("prompt_eval_count", 0),
                "completion_tokens": response_data.get("eval_count", 0),
                "total_tokens": response_data.get("prompt_eval_count", 0) + response_data.get("eval_count", 0)
            },
            "prompt": prompt,
            "response": response_data.get('response', '').strip()
        }
        
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')

    except Exception as e:
        logging.error(f"写入LLM监控日志失败: {e}")