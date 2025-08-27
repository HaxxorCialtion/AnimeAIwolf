# llm_utils.py

import logging
import requests
import json
import random
import time
from config import LLM_PROVIDERS, PERSONAS, LLM_GENERATION_PARAMS, LLM_DEBUG_CONFIG
from llm_monitoring import log_llm_call
from game_models import Role

# --- 参数合并与配置函数 ---
def _get_generation_params(call_type: str = None, player_role: str = None) -> dict:
    """
    根据调用类型和角色获取合并后的LLM生成参数
    优先级: 角色重写 > 调用类型重写 > 全局默认
    """
    # 从全局默认开始
    params = LLM_GENERATION_PARAMS.get("defaults", {}).copy()
    
    # 应用调用类型特定的参数
    if call_type and call_type in LLM_GENERATION_PARAMS.get("call_type_overrides", {}):
        call_type_params = LLM_GENERATION_PARAMS["call_type_overrides"][call_type]
        params.update(call_type_params)
    
    # 应用角色特定的参数（如果提供）
    if player_role and player_role in LLM_GENERATION_PARAMS.get("role_overrides", {}):
        role_params = LLM_GENERATION_PARAMS["role_overrides"][player_role]
        params.update(role_params)
    
    return params

def _log_debug_info(call_type: str, player_id: int, prompt: str = None, response: dict = None, duration: float = None):
    """统一的调试信息记录"""
    debug_config = LLM_DEBUG_CONFIG
    
    if debug_config.get("log_prompts") and prompt:
        logging.debug(f"LLM Prompt for player {player_id} ({call_type}):\n{prompt[:200]}...")
    
    if debug_config.get("log_responses") and response:
        logging.debug(f"LLM Response for player {player_id} ({call_type}): {response}")
    
    if debug_config.get("log_timing") and duration is not None:
        logging.info(f"LLM call for player {player_id} ({call_type}) took {duration:.2f}ms")
    
    if debug_config.get("log_token_usage") and response:
        prompt_tokens = response.get("prompt_eval_count") or response.get("prompt_tokens", 0)
        completion_tokens = response.get("eval_count") or response.get("completion_tokens", 0)
        if prompt_tokens > 0 or completion_tokens > 0:
            logging.info(f"Token usage for player {player_id} ({call_type}): {prompt_tokens} prompt + {completion_tokens} completion = {prompt_tokens + completion_tokens} total")

# --- 增强的LLM API调用核心函数 ---
def _call_ollama(config: dict, prompt: str, params: dict = None) -> dict:
    """调用Ollama API，支持可配置参数"""
    if params is None:
        params = {}
    
    # 构建Ollama选项
    options = {}
    if "temperature" in params:
        options["temperature"] = params["temperature"]
    if "top_p" in params:
        options["top_p"] = params["top_p"]
    if "presence_penalty" in params:
        options["repeat_penalty"] = 1.0 + params["presence_penalty"]  # Ollama使用repeat_penalty
    
    payload = {
        "model": config['model'],
        "prompt": prompt,
        "stream": False,
        "options": options,
        "format": "json"
    }
    
    timeout = params.get("timeout", 30)
    response = requests.post(config['api_url'], json=payload, timeout=timeout)
    response.raise_for_status()
    return json.loads(response.json().get('response', '{}'))

def _call_openai_compatible(config: dict, prompt: str, params: dict = None) -> dict:
    """调用OpenAI兼容API，支持可配置参数"""
    if params is None:
        params = {}
    
    headers = {
        "Authorization": f"Bearer {config['api_key']}",
        "Content-Type": "application/json"
    }
    
    # 构建OpenAI格式的参数
    payload = {
        "model": config['model'],
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {"type": "json_object"}
    }
    
    # 添加生成参数
    if "temperature" in params:
        payload["temperature"] = params["temperature"]
    if "top_p" in params:
        payload["top_p"] = params["top_p"]
    if "max_tokens" in params and params["max_tokens"]:
        payload["max_tokens"] = params["max_tokens"]
    if "presence_penalty" in params:
        payload["presence_penalty"] = params["presence_penalty"]
    if "frequency_penalty" in params:
        payload["frequency_penalty"] = params["frequency_penalty"]
    
    timeout = params.get("timeout", 30)
    response = requests.post(config['api_url'], headers=headers, json=payload, timeout=timeout)
    response.raise_for_status()
    raw_content = response.json().get('choices', [{}])[0].get('message', {}).get('content', '{}')
    return json.loads(raw_content)

def _call_ollama_speech(config: dict, prompt: str, params: dict = None) -> dict:
    """调用Ollama API生成发言（不需要JSON格式）"""
    if params is None:
        params = {}
    
    options = {}
    if "temperature" in params:
        options["temperature"] = params["temperature"]
    if "top_p" in params:
        options["top_p"] = params["top_p"]
    if "presence_penalty" in params:
        options["repeat_penalty"] = 1.0 + params["presence_penalty"]
    
    payload = {
        "model": config['model'], 
        "prompt": prompt, 
        "stream": False, 
        "options": options
    }
    
    timeout = params.get("timeout", 30)
    response = requests.post(config['api_url'], json=payload, timeout=timeout)
    response.raise_for_status()
    return response.json()

def _call_openai_compatible_speech(config: dict, prompt: str, params: dict = None) -> dict:
    """调用OpenAI兼容API生成发言"""
    if params is None:
        params = {}
    
    headers = {
        "Authorization": f"Bearer {config['api_key']}", 
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": config['model'], 
        "messages": [{"role": "user", "content": prompt}]
    }
    
    # 添加生成参数
    if "temperature" in params:
        payload["temperature"] = params["temperature"]
    if "top_p" in params:
        payload["top_p"] = params["top_p"]
    if "max_tokens" in params and params["max_tokens"]:
        payload["max_tokens"] = params["max_tokens"]
    if "presence_penalty" in params:
        payload["presence_penalty"] = params["presence_penalty"]
    if "frequency_penalty" in params:
        payload["frequency_penalty"] = params["frequency_penalty"]
    
    timeout = params.get("timeout", 30)
    response = requests.post(config['api_url'], headers=headers, json=payload, timeout=timeout)
    response.raise_for_status()
    return response.json()

def generate_llm_response(prompt: str, call_type: str, player_id: int, player_role: str = None) -> dict:
    """
    增强的LLM响应生成函数，支持可配置参数
    """
    provider_name = LLM_PROVIDERS.get("default", "ollama")
    config = LLM_PROVIDERS.get(provider_name)

    if not config:
        logging.error(f"LLM配置错误: 未找到名为 '{provider_name}' 的供应商配置。")
        return {"error": "LLM configuration error"}

    # 获取合并后的生成参数
    generation_params = _get_generation_params(call_type, player_role)
    
    start_time = time.monotonic()
    response_data = {}
    
    # 调试信息记录
    if LLM_DEBUG_CONFIG.get("log_prompts"):
        _log_debug_info(call_type, player_id, prompt=prompt)
    
    try:
        if call_type == 'speech':
            if provider_name == "ollama":
                raw_response = _call_ollama_speech(config, prompt, generation_params)
                response_data = {
                    "response": raw_response.get('response', ''),
                    "prompt_eval_count": raw_response.get("prompt_eval_count", 0),
                    "eval_count": raw_response.get("eval_count", 0),
                }
            elif provider_name == "openai_compatible":
                raw_response = _call_openai_compatible_speech(config, prompt, generation_params)
                response_data = {
                    "response": raw_response.get('choices', [{}])[0].get('message', {}).get('content', ''),
                    "prompt_tokens": raw_response.get('usage', {}).get('prompt_tokens', 0),
                    "completion_tokens": raw_response.get('usage', {}).get('completion_tokens', 0),
                }
        else:
            if provider_name == "ollama":
                response_data = _call_ollama(config, prompt, generation_params)
            elif provider_name == "openai_compatible":
                response_data = _call_openai_compatible(config, prompt, generation_params)
            else:
                raise NotImplementedError(f"不支持的LLM供应商: {provider_name}")

    except requests.exceptions.RequestException as e:
        logging.error(f"调用LLM API失败 ({provider_name}): {e}")
        response_data = {"error": str(e)}
    except Exception as e:
        logging.error(f"处理LLM响应时发生未知错误 ({provider_name}): {e}")
        response_data = {"error": str(e)}

    duration_ms = (time.monotonic() - start_time) * 1000
    
    # 调试信息记录
    _log_debug_info(call_type, player_id, response=response_data, duration=duration_ms)
    
    # 记录到监控系统
    log_llm_call(call_type, player_id, prompt, response_data, duration_ms)
    
    return response_data

# --- Prompt构建与工具调用函数 ---
def _get_player_nickname(game_state: dict, player_id: int) -> str:
    player = next((p for p in game_state['players'] if p['id'] == player_id), None)
    return player.get('nickname', f"玩家{player_id}") if player else f"玩家{player_id}"

def _build_game_history_text(game_state: dict) -> str:
    history_lines = []
    for day_log in game_state.get('game_log', []):
        day = day_log['day']
        if day > 1:
            prev_day_log = next((log for log in game_state['game_log'] if log['day'] == day - 1), None)
            if prev_day_log and prev_day_log.get('eliminated_night'):
                eliminated_id = prev_day_log['eliminated_night']
                nickname = _get_player_nickname(game_state, eliminated_id)
                player = next((p for p in game_state['players'] if p['id'] == eliminated_id), None)
                role = player.get('revealed_role', '未知') if player else '未知'
                history_lines.append(f"--- 第 {day} 天 (天亮) ---")
                history_lines.append(f"[昨夜结果] {nickname}({eliminated_id}号)被淘汰，身份是: {role}。")
            else:
                history_lines.append(f"--- 第 {day} 天 (天亮) ---")
                history_lines.append("[昨夜结果] 平安夜。")
        else:
             history_lines.append(f"--- 第 {day} 天 ---")
        if day_log.get('speeches'):
            history_lines.append("[白天发言]")
            for speech in day_log['speeches']:
                nickname = _get_player_nickname(game_state, speech['player_id'])
                history_lines.append(f"  - {nickname}({speech['player_id']}号): \"{speech['text']}\"")
        if day_log.get('eliminated_vote'):
            eliminated_id = day_log['eliminated_vote']
            nickname = _get_player_nickname(game_state, eliminated_id)
            player = next((p for p in game_state['players'] if p['id'] == eliminated_id), None)
            role = player.get('revealed_role', '未知') if player else '未知'
            history_lines.append(f"[投票结果] {nickname}({eliminated_id}号)被投票淘汰，身份是: {role}。")
    current_day = game_state['day']
    is_today_logged = any(f"--- 第 {current_day} 天" in line for line in history_lines)
    if not is_today_logged and current_day > 1:
        prev_day_log = next((log for log in game_state['game_log'] if log.get('day') == current_day - 1), None)
        if prev_day_log and prev_day_log.get('eliminated_night'):
            eliminated_id = prev_day_log['eliminated_night']
            nickname = _get_player_nickname(game_state, eliminated_id)
            player = next((p for p in game_state['players'] if p['id'] == eliminated_id), None)
            role = player.get('revealed_role', '未知') if player else '未知'
            history_lines.append(f"--- 第 {current_day} 天 (天亮) ---")
            history_lines.append(f"[昨夜结果] {nickname}({eliminated_id}号)被淘汰，身份是: {role}。")
    return "\n".join(history_lines) if history_lines else "游戏刚刚开始，还没有任何历史记录。"

def _get_seer_secret_knowledge_text(player: dict) -> str:
    if player.get('role') != Role.SEER.value or not player.get('seer_knowledge'): return ""
    knowledge_lines = ["---", "# 你的秘密情报（仅你可见）"]
    for check in player['seer_knowledge']:
        day_text = f"第{check['day']}天晚上" if check['day'] > 0 else "游戏开始前"
        knowledge_lines.append(f"- 你在{day_text}查验了 **{check['checked_id']}号** 玩家，其真实身份是: **{check['role']}**。")
    knowledge_lines.append("---")
    return "\n".join(knowledge_lines)

def construct_llm_prompt(game_state: dict, player_id: int) -> str:
    """
    为AI玩家构建一个高度情景化和策略化的LLM Prompt。
    """
    player = next(p for p in game_state['players'] if p['id'] == player_id)
    role = player['role']
    
    # 1. 基础信息模块
    persona_prompt = PERSONAS.get(player_id, "")
    role_play_section = f"# 你的角色扮演指导\n{persona_prompt}\n---" if persona_prompt else ""
    game_history = _build_game_history_text(game_state)
    seer_knowledge = _get_seer_secret_knowledge_text(player)
    
    # 2. 动态生成任务和策略模块 (核心修改)
    mission = ""
    guidelines = ""

    if role == Role.SEER.value:
        mission = (
            "你的身份是 **预言家**，是好人阵营的灵魂人物。你的任务是每晚查验一人身份，并利用你的信息引导村民投票淘汰狼人。\n"
            "**!! 极度危险警告 !!** 你的身份一旦暴露，你很容易成为狼人夜晚的必杀目标。因此，**生存**和**传递信息**同等重要。"
        )
        guidelines = (
            "# 你的行动指导 (预言家策略)\n"
            "1.  **谨慎权衡**：不要轻易暴露你的身份。过早地跳出来说我是预言家是一种非常危险的行为。\n"
            "2.  **信息传递技巧**：\n"
            "    - **暗示**：如果你查验了A是好人（金水），你可以说我觉得A玩家发言很好，我暂时相信他，而不是直接说A是我的金水。\n"
            "    - **引导**：如果你查验了B是狼人，你可以说B玩家的发言逻辑有问题，我怀疑他的身份，引导大家怀疑他。\n"
            "3.  **何时摊牌 (跳身份)**：只有在关键时刻才考虑暴露身份，例如：\n"
            "    - 当你查到狼人，并且确信你的发言能说服足够多的人在白天将他投出去时。\n"
            "    - 当场上出现另一个假冒预言家的人，你必须站出来与他对峙，争夺好人的信任时。\n"
            "4.  **发言重点**：你的发言应该围绕你的查验信息展开，即使是暗示性的。分析场上局势，指出你怀疑谁，信任谁，并给出简要理由。"
        )

    elif role == Role.WEREWOLF.value:
        mission = (
            "你的身份是 **狼人**，你的任务是伪装成村民，误导好人，并在晚上与同伴一起淘汰威胁最大的人，直到狼人数量不少于好人。\n"
            "**核心要点**：获取好人的信任是你胜利的关键。预言家是你的最大威胁。"
        )
        guidelines = (
            "# 你的行动指导 (狼人策略)\n"
            "1.  **积极伪装**：像一个真正的村民一样发言。分析局势，找出你认为的狼人（即嫁祸给某个好人）。\n"
            "2.  **制造混乱**：\n"
            "    - **拉拢阵营**：声称相信某个发言好的好人，将他拉入你的阵营，让他为你说话。\n"
            "    - **攻击目标**：有策略地攻击一个看起来很聪明或有领导力的好人，引导大家怀疑他。\n"
            "3.  **团队合作**：留意你狼同伴的发言和投票，在不暴露自己的前提下与他们形成配合。\n"
            "4.  **悍跳预言家 (高风险策略)**：在局势混乱时，你可以冒险声称自己是预言家，并给一个好人查杀（说他是狼人），或者给你的狼同伴金水（说他是好人），以扰乱好人阵营的判断。"
        )

    else: # Role.VILLAGER.value
        mission = (
            "你的身份是 **村民**，是好人阵营的基石。你没有任何特殊能力，你唯一的武器就是你的逻辑和判断力。\n"
            "**核心任务**：仔细聆听每个人的发言，分辨出谁在说谎，找出所有隐藏的狼人，并跟随真正的预言家将他们投票出局。" 
        )
        guidelines = (
            "# 你的行动指导 (村民策略)\n"
            "1.  **认真倾听**：仔细听每个人的发言，寻找逻辑漏洞和前后矛盾的地方。\n"
            "2.  **逻辑站边**：在你的发言中，明确指出你认为谁的发言更好、更可信，你怀疑谁，并说明你的理由。\n"
            "3.  **分辨预言家**：如果有人声称是预言家，仔细分析他的发言和查验信息是否合理。狼人也可能会假冒预言家。\n" 
            "你可以需要想办法保护预言家，包括不限于真预言家被狼人盯上时，你假装预言家欺骗狼人。\n"
            "4.  **保持清醒**：不要轻易被别人的发言煽动。作为村民，你的每一票都至关重要。"     
        )

    # 3. 组装最终的Prompt
    prompt = f"""你正在玩一场狼人杀游戏。
# 游戏规则
1.  **身份配置**：有**村民**、**狼人**和一名**预言家**。
2.  **胜利条件**：村民阵营（村民、预言家）淘汰所有狼人；或狼人数量不少于好人。
3.  **特殊时期**: 第一天之前除了预言家验人，并没有其他游戏记录，且大家发言都是严格编号按照顺序进行的，除了自由发言时期。
4.  **游戏流程**：游戏流程为白天顺序发言、自由发言，投票（第一天不投票），夜晚（预言家验人、狼人淘汰人），然后又是白天，以此循环。
{role_play_section}
# 你的身份与任务
你是 {player['nickname']}({player_id}号)。{mission}
{seer_knowledge}
# 完整的游戏历史记录
{game_history}
# 当前局势
- **当前阶段**: 第 {game_state['day']} 天，轮到你发言。
- **存活玩家**: {[p['id'] for p in game_state['players'] if p['is_alive']]}。
{guidelines}
# 发言要求
- **直接输出**：直接给出你的发言内容，不要包含任何前缀，如"我的发言是:"。
- **发言简短**：尽量控制在40字以内。

现在，请发言："""
    return prompt

def construct_voting_prompt(game_state: dict, player_id: int) -> str:
    player = next(p for p in game_state['players'] if p['id'] == player_id)
    persona_prompt = PERSONAS.get(player_id, "")
    role_play_section = f"# 你的角色扮演指导\n{persona_prompt}\n---" if persona_prompt else ""
    role = player['role']
    alive_players = [p for p in game_state['players'] if p.get('is_alive')]
    game_history = _build_game_history_text(game_state)
    seer_knowledge = _get_seer_secret_knowledge_text(player)
    
    tool_definition = """
# 工具定义
你必须使用以下工具来做出你的决定。
你必须返回一个JSON对象，其中包含你要使用的工具名称和参数。
例如: {"tool_name": "vote_for_player", "arguments": {"player_id": 4, "reason": "他的发言很可疑。"}}

可用工具:
- `vote_for_player`: 投票淘汰一名玩家。
  - `player_id` (整数, 必需): 你想要投票淘汰的玩家编号。
  - `reason` (字符串, 必需): 你投票给这个玩家的简要理由。
"""
    
    prompt = f"""你正在玩一场狼人杀游戏，现在是第 {game_state['day']} 天的投票阶段。
{role_play_section}
你的身份是 **{role}**。
{seer_knowledge}
# 完整的游戏历史记录
{game_history}
# 投票目标
从以下存活玩家中选择一人进行投票（不能投给自己）：
{[_get_player_nickname(game_state, p['id']) + '(' + str(p['id']) + '号)' for p in alive_players if p['id'] != player_id]}
{tool_definition}
请根据你的分析，调用 `vote_for_player` 工具来投票。
"""
    return prompt

def get_llm_vote(game_state: dict, player_id: int, max_retries: int = None) -> int:
    if max_retries is None:
        max_retries = LLM_DEBUG_CONFIG.get("max_retries", 3)
        
    alive_players = [p for p in game_state['players'] if p.get('is_alive')]
    valid_targets = [p['id'] for p in alive_players if p['id'] != player_id]
    if not valid_targets: 
        return None
    
    # 获取玩家角色信息
    player = next((p for p in game_state['players'] if p['id'] == player_id), None)
    player_role = player.get('role') if player else None
    
    prompt = construct_voting_prompt(game_state, player_id)
    
    base_delay = LLM_DEBUG_CONFIG.get("base_retry_delay", 1.0)
    enable_backoff = LLM_DEBUG_CONFIG.get("enable_retry_backoff", True)
    
    for attempt in range(max_retries):
        data = generate_llm_response(prompt, call_type='vote', player_id=player_id, player_role=player_role)
        
        if "error" in data:
            logging.warning(f"玩家{player_id}投票尝试 {attempt+1}: API调用失败 - {data['error']}")
            if attempt < max_retries - 1 and enable_backoff:
                delay = base_delay * (2 ** attempt)  # 指数退避
                time.sleep(delay)
            continue

        try:
            if data.get("tool_name") == "vote_for_player":
                vote_target = data.get("arguments", {}).get("player_id")
                if vote_target in valid_targets:
                    logging.info(f"玩家{player_id}通过LLM投票给: {vote_target}")
                    return vote_target
                else:
                    logging.warning(f"玩家{player_id}投票尝试 {attempt+1}: 目标 {vote_target} 无效。")
            else:
                logging.warning(f"玩家{player_id}投票尝试 {attempt+1}: 返回的JSON未使用正确的工具。")
        except Exception as e:
            logging.warning(f"玩家{player_id}投票尝试 {attempt+1}: 解析或验证响应失败 - {e}。响应: {data}")

    fallback_vote = random.choice(valid_targets)
    logging.error(f"玩家{player_id}的LLM投票在 {max_retries} 次尝试后全失败，随机投票给: {fallback_vote}")
    return fallback_vote

def construct_werewolf_kill_prompt(game_state: dict, player_id: int) -> str:
    player = next(p for p in game_state['players'] if p['id'] == player_id)
    other_werewolves = [p for p in game_state['players'] if p['role'] == Role.WEREWOLF.value and p['id'] != player_id]
    
    alive_players = [p for p in game_state['players'] if p.get('is_alive')]
    valid_targets = [p for p in alive_players if p['role'] != Role.WEREWOLF.value]

    game_history = _build_game_history_text(game_state)
    
    tool_definition = """
# 工具定义
你必须使用以下JSON格式来做出你的决定。
例如: {"tool_name": "kill_player", "arguments": {"player_id": 4, "reason": "他是预言家，威胁最大。"}}

可用工具:
- `kill_player`: 在夜晚淘汰一名玩家。
  - `player_id` (整数, 必需): 你想要淘汰的玩家编号。
  - `reason` (字符串, 必需): 你选择淘汰这个玩家的简要理由。
"""
    
    prompt = f"""你正在玩一场狼人杀游戏，现在是第 {game_state['day']} 天的夜晚，轮到狼人行动。
# 你的身份与同伴
你是 {player['nickname']}({player_id}号)，你的身份是 **狼人**。
你的同伴是: {[_get_player_nickname(game_state, p['id']) + '(' + str(p['id']) + '号)' for p in other_werewolves] or ['无']}

# 完整的游戏历史记录
{game_history}

# 淘汰目标
你的任务是淘汰一名好人（村民或预言家）。从以下目标中选择一人进行淘汰：
{[_get_player_nickname(game_state, p['id']) + '(' + str(p['id']) + '号)' for p in valid_targets]}

{tool_definition}
请根据你的分析，调用 `kill_player` 工具来淘汰一名玩家。优先淘汰暴露身份的预言家或看起来最聪明的玩家。
"""
    return prompt

def get_llm_werewolf_kill(game_state: dict, player_id: int, max_retries: int = None) -> int:
    if max_retries is None:
        max_retries = LLM_DEBUG_CONFIG.get("max_retries", 3)
        
    alive_players = [p for p in game_state['players'] if p.get('is_alive')]
    valid_targets = [p['id'] for p in alive_players if p['role'] != Role.WEREWOLF.value]
    if not valid_targets:
        logging.warning(f"狼人 {player_id} 找不到任何可淘汰的目标。")
        return None

    # 获取玩家角色信息
    player = next((p for p in game_state['players'] if p['id'] == player_id), None)
    player_role = player.get('role') if player else None

    prompt = construct_werewolf_kill_prompt(game_state, player_id)
    
    base_delay = LLM_DEBUG_CONFIG.get("base_retry_delay", 1.0)
    enable_backoff = LLM_DEBUG_CONFIG.get("enable_retry_backoff", True)
    
    for attempt in range(max_retries):
        data = generate_llm_response(prompt, call_type='kill', player_id=player_id, player_role=player_role)
        
        if "error" in data:
            logging.warning(f"狼人{player_id}淘汰尝试 {attempt+1}: API调用失败 - {data['error']}")
            if attempt < max_retries - 1 and enable_backoff:
                delay = base_delay * (2 ** attempt)
                time.sleep(delay)
            continue

        try:
            if data.get("tool_name") == "kill_player":
                target_id = data.get("arguments", {}).get("player_id")
                if target_id in valid_targets:
                    logging.info(f"狼人{player_id}通过LLM选择淘汰: {target_id}")
                    return target_id
                else:
                    logging.warning(f"狼人{player_id}淘汰尝试 {attempt+1}: 目标 {target_id} 无效。有效目标: {valid_targets}")
            else:
                logging.warning(f"狼人{player_id}淘汰尝试 {attempt+1}: 返回的JSON未使用正确的工具。")
        except Exception as e:
            logging.warning(f"狼人{player_id}淘汰尝试 {attempt+1}: 解析或验证响应失败 - {e}。响应: {data}")

    fallback_kill = random.choice(valid_targets)
    logging.error(f"狼人{player_id}的LLM淘汰在 {max_retries} 次尝试后全失败，随机选择: {fallback_kill}")
    return fallback_kill

def get_llm_seer_check(game_state: dict, player_id: int, max_retries: int = None) -> int:
    if max_retries is None:
        max_retries = LLM_DEBUG_CONFIG.get("max_retries", 3)
        
    alive_players = [p for p in game_state['players'] if p.get('is_alive')]
    seer = next((p for p in game_state['players'] if p['id'] == player_id), None)
    checked_ids = {check['checked_id'] for check in seer.get('seer_knowledge', [])}
    valid_targets = [p['id'] for p in alive_players if p['id'] != player_id and p['id'] not in checked_ids]
    if not valid_targets:
        return None
    return random.choice(valid_targets)