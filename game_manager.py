# game_manager.py

import os
import json
import random
import logging
import threading
import time
import asyncio
from datetime import datetime
from config import GAME_CONFIG, NICKNAMES
from game_models import Role, GamePhase, GameError
from llm_utils import construct_llm_prompt, get_llm_vote, generate_llm_response, get_llm_seer_check, get_llm_werewolf_kill
from tts_manager import TTSManager

class WerewolfWebGame:
    # --- 修改：构造函数接收 voice_enabled 参数 ---
    def __init__(self, socketio, voice_enabled: bool = False):
        self.socketio = socketio
        self.voice_enabled = voice_enabled  # 存储当前游戏的语音模式
        self.game_state = {}
        self.game_file_path = None
        self.current_speaker_index = 0
        self.discussion_active = False
        self.discussion_end_time = None
        self.voting_active = False
        self.night_active = False
        self.human_vote = None
        self.human_night_target = None
        self.game_started = False
        self.next_speaker_callback = None
        
        # 只有在语音模式启用时才初始化TTS管理器
        if self.voice_enabled:
            self.tts_manager = TTSManager(self.socketio)
        else:
            self.tts_manager = None
    
    # ... (从 _save_game_state 到 process_voting_without_human 之间的所有函数保持不变) ...
    def _save_game_state(self):
        if not self.game_file_path: return
        try:
            with open(self.game_file_path, 'w', encoding='utf-8') as f:
                json.dump(self.game_state, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logging.error(f"保存游戏状态失败: {e}")
            
    def start_game(self):
        if self.game_started: raise GameError("游戏已经开始")
        games_folder = "games"
        if not os.path.exists(games_folder): os.makedirs(games_folder)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.game_file_path = os.path.join(games_folder, f"game_{timestamp}.json")
        self.game_state = {"game_id": timestamp, "total_players": GAME_CONFIG['players_count'], "day": 1, "phase": GamePhase.WAITING.value, "players": [], "game_log": []}
        player_ids = list(range(1, GAME_CONFIG['players_count'] + 1))
        random.shuffle(player_ids)
        for player_id in player_ids:
            self.game_state['players'].append({"id": player_id, "nickname": NICKNAMES.get(player_id, f"玩家{player_id}"), "role": None, "is_alive": True, "is_human": (player_id == 7)})
        self.assign_roles()
        self.emit_log("游戏开始！身份已分配完成")
        self.game_started = True
        self.socketio.emit('game_started')
        self._save_game_state()
        
        seer = self.get_seer()
        if seer and seer['is_alive']:
            self.emit_log("预言家请在天亮前查验一人...")
            threading.Timer(2.0, self._pre_game_seer_turn).start()
        else:
            threading.Timer(2.0, self.start_day_phase).start()

    def assign_roles(self):
        roles = ([Role.WEREWOLF.value] * GAME_CONFIG['werewolves_count'] +
                 [Role.SEER.value] * GAME_CONFIG['seer_count'] +
                 [Role.VILLAGER.value] * GAME_CONFIG['villagers_count'])
        random.shuffle(roles)

        for player, role in zip(self.game_state['players'], roles):
            player['role'] = role
            if role == Role.SEER.value:
                player['seer_knowledge'] = []

        human_player = self.get_human_player()
        if human_player:
            logging.info(f"玩家{human_player['id']}({human_player['nickname']})的身份是：{human_player['role']}")
        self.emit_game_state()

    def add_speech_to_log(self, player_id, text):
        current_day = self.game_state['day']
        day_log = next((log for log in self.game_state['game_log'] if log['day'] == current_day), None)
        if not day_log:
            day_log = {"day": current_day, "speeches": [], "eliminated_vote": None, "eliminated_night": None}
            self.game_state['game_log'].append(day_log)
        day_log['speeches'].append({"player_id": player_id, "text": text})
        self._save_game_state()

    def _pre_game_seer_turn(self):
        self.game_state['phase'] = GamePhase.PRE_GAME_SEER.value
        self.emit_phase_update("游戏准备中 - 预言家查验")
        seer = self.get_seer()
        if not seer:
            self.start_day_phase()
            return
        checked_ids = {check['checked_id'] for check in seer.get('seer_knowledge', [])}
        checkable_targets = [p['id'] for p in self.get_alive_players() if p['id'] != seer['id'] and p['id'] not in checked_ids]
        if not checkable_targets:
            self.emit_log("预言家已无新的可查验目标。")
            threading.Timer(2.0, self.start_day_phase).start()
            return
        if seer['is_human']:
            self.socketio.emit('request_seer_action', {'targets': checkable_targets})
        else:
            threading.Thread(target=self._run_ai_pre_game_seer_check, args=(seer,)).start()

    def _run_ai_pre_game_seer_check(self, seer):
        target_id = get_llm_seer_check(self.game_state, seer['id'])
        if target_id:
            self.process_seer_check(seer, target_id, day=0)
        self.start_day_phase()

    def process_seer_check(self, seer, target_id, day=None):
        if day is None:
            day = self.game_state['day']
        target_player = next((p for p in self.game_state['players'] if p['id'] == target_id), None)
        if not target_player: return
        result_role = target_player['role']
        if result_role in [Role.WEREWOLF.value]:
            result_role = Role.WEREWOLF.value
        else:
            result_role = "好人"
        seer['seer_knowledge'].append({
            "day": day,
            "checked_id": target_id,
            "role": result_role 
        })
        self._save_game_state()
        logging.info(f"预言家({seer['id']},{seer['nickname']})在第{day}天查验了{target_id}号，身份是{result_role}")
        if seer['is_human']:
            self.socketio.emit('seer_result', {
                "target_id": target_id, 
                "role": result_role,
                "day": day
            })
    
    def start_day_phase(self):
        self.game_state['day'] = max(1, self.game_state['day'])
        self.game_state['phase'] = GamePhase.DAY.value
        self.emit_phase_update(f"第{self.game_state['day']}天 白天 - 按序发言")
        self.emit_log(f"--- 第{self.game_state['day']}天 天亮了 ---")
        if self.game_state['day'] > 1:
            prev_day_log = next((log for log in self.game_state['game_log'] if log.get('day') == self.game_state['day'] - 1), None)
            if prev_day_log and prev_day_log.get('eliminated_night'):
                eliminated_id = prev_day_log.get('eliminated_night')
                player = next((p for p in self.game_state['players'] if p['id'] == eliminated_id), None)
                if player:
                    self.emit_log(f"昨晚, {player['nickname']}({eliminated_id}号)被淘汰了，其身份是: {player['revealed_role']}")
            else:
                self.emit_log("昨晚是平安夜。")
        self.emit_game_state()
        if self.check_game_over(): return
        self.ordered_speech()

    def start_night_phase(self):
        self.night_active = True
        self.human_night_target = None
        self.emit_log(f"--- 第{self.game_state['day']}天 夜晚降临 ---")
        seer = self.get_seer()
        if seer and seer['is_alive']:
            self._handle_seer_turn(seer)
        else:
            self._handle_werewolf_turn()

    def _handle_seer_turn(self, seer):
        self.game_state['phase'] = GamePhase.NIGHT_SEER.value
        self.emit_phase_update(f"第{self.game_state['day']}天 夜晚 - 预言家行动")
        checked_ids = {check['checked_id'] for check in seer.get('seer_knowledge', [])}
        checkable_targets = [p['id'] for p in self.get_alive_players() if p['id'] != seer['id'] and p['id'] not in checked_ids]
        if not checkable_targets:
            self.emit_log("预言家已无新的可查验目标。")
            threading.Timer(3.0, self._handle_werewolf_turn).start()
            return
        if seer['is_human']:
            self.socketio.emit('request_seer_action', {'targets': checkable_targets})
        else:
            threading.Thread(target=self._run_ai_seer_check, args=(seer,)).start()

    def _run_ai_seer_check(self, seer):
        target_id = get_llm_seer_check(self.game_state, seer['id'])
        if target_id:
            self.process_seer_check(seer, target_id)
        self._handle_werewolf_turn()

    def _handle_werewolf_turn(self):
        self.game_state['phase'] = GamePhase.NIGHT_WEREWOLF.value
        self.emit_phase_update(f"第{self.game_state['day']}天 夜晚 - 狼人行动")
        human_player = self.get_human_player()
        if human_player and human_player['is_alive'] and human_player['role'] == Role.WEREWOLF.value:
            other_werewolves = [p for p in self.get_werewolves() if p['id'] != human_player['id']]
            other_werewolves_info = [f"{p['nickname']}({p['id']}号)" for p in other_werewolves]
            self.emit_log(f"你是狼人，请选择淘汰目标。你的狼同伴是: {other_werewolves_info or '无'}")
            self.socketio.emit('start_night_werewolf')
        else:
            self.emit_log("狼人请行动...")
            threading.Timer(3.0, self.process_night_action).start()
    
    def next_day(self):
        self.game_state['day'] += 1
        self.human_vote = None
        self.human_night_target = None
        self.night_active = False
        self._save_game_state()
        threading.Timer(2.0, self.start_day_phase).start()

    def ordered_speech(self):
        alive_players = sorted(self.get_alive_players(), key=lambda p: p['id'])
        self.current_speaker_index = 0
        def _next():
            if self.current_speaker_index >= len(alive_players):
                self.start_discussion()
                return
            player = alive_players[self.current_speaker_index]
            if not player['is_alive']:
                self.current_speaker_index += 1
                _next()
                return
            self.emit_log(f"现在轮到 {player['nickname']}({player['id']}号) 发言。")
            if player['is_human']:
                self.socketio.emit('request_speech')
            else:
                threading.Timer(random.uniform(*GAME_CONFIG['computer_speech_delay']), self.computer_speech, [player]).start()
        self.next_speaker_callback = _next
        _next()

    def computer_speech(self, player):
        if not player['is_alive'] or self.game_state['phase'] == GamePhase.ENDED.value:
            if self.next_speaker_callback:
                self.current_speaker_index += 1
                self.next_speaker_callback()
            return
        
        prompt = construct_llm_prompt(self.game_state, player['id'])
        # 传递角色信息给LLM
        response_data = generate_llm_response(
            prompt, 
            call_type='speech', 
            player_id=player['id'],
            player_role=player['role']  # 新增：传递角色信息
        )
        
        speech = response_data.get('response', '').strip()
        if not speech:
            speech = f"我是{player['nickname']}({player['id']}号)，过。"
            logging.warning(f"玩家{player['id']} LLM响应失败，使用备用发言。")
        
        self.emit_speech(player['id'], speech)
        if self.next_speaker_callback:
            self.current_speaker_index += 1
            self.next_speaker_callback()

        def _schedule_computer_discussion(self, player):
            if not self.discussion_active or self.discussion_end_time is None: 
                return
            time_remaining = self.discussion_end_time - time.monotonic()
            if time_remaining < 5.0: 
                return 
            
            def speak():
                if not self.discussion_active: 
                    return
                if player['is_alive'] and random.random() < GAME_CONFIG['discussion_probability']:
                    prompt = construct_llm_prompt(self.game_state, player['id'])
                    # 传递角色信息给LLM
                    response_data = generate_llm_response(
                        prompt, 
                        call_type='speech', 
                        player_id=player['id'],
                        player_role=player['role']  # 新增：传递角色信息
                    )
                    
                    speech = response_data.get('response', '').strip() or f"{player['nickname']}({player['id']}号)补充一点..."
                    if self.discussion_active:
                        self.emit_speech(player['id'], speech)
                self._schedule_computer_discussion(player)
                
            delay = random.uniform(5, 15)
            threading.Timer(delay, speak).start()

    def handle_human_speech(self, text):
        player = self.get_human_player()
        if player:
            self.emit_speech(player['id'], text)
        if self.next_speaker_callback:
            self.current_speaker_index += 1
            self.next_speaker_callback()
            
    def start_discussion(self):
        self.game_state['phase'] = GamePhase.DISCUSSION.value
        self.discussion_active = True
        self.discussion_end_time = time.monotonic() + GAME_CONFIG['discussion_time']
        self.emit_phase_update(f"第{self.game_state['day']}天 白天 - 自由讨论 ({GAME_CONFIG['discussion_time']}秒)")
        self.socketio.emit('start_discussion')
        threading.Timer(float(GAME_CONFIG['discussion_time']), self.end_discussion).start()
        self.start_computer_discussion()

    def end_discussion(self):
        if not self.discussion_active: return
        self.discussion_active = False
        self.discussion_end_time = None
        self.socketio.emit('discussion_ended')
        self.emit_log("自由讨论结束。")
        if self.game_state['day'] == 1:
            self.emit_log("第一天不投票，直接进入夜晚。")
            self.start_night_phase()
        else:
            self.start_voting()
            
    def start_voting(self):
        self.game_state['phase'] = GamePhase.VOTING.value
        self.voting_active = True
        self.emit_phase_update(f"第{self.game_state['day']}天 白天 - 投票")
        self.emit_log("投票阶段开始。")
        human_player = self.get_human_player()
        if not human_player or not human_player.get('is_alive'):
            self.emit_log("你已死亡，观战中...")
            threading.Timer(3.0, self.process_voting_without_human).start()
        else:
            self.socketio.emit('start_voting')

    def start_computer_discussion(self):
        computers = [p for p in self.get_alive_players() if not p['is_human']]
        for player in computers:
            self._schedule_computer_discussion(player)

    def _schedule_computer_discussion(self, player):
        if not self.discussion_active or self.discussion_end_time is None: return
        time_remaining = self.discussion_end_time - time.monotonic()
        if time_remaining < 5.0: return 
        def speak():
            if not self.discussion_active: return
            if player['is_alive'] and random.random() < GAME_CONFIG['discussion_probability']:
                prompt = construct_llm_prompt(self.game_state, player['id'])
                response_data = generate_llm_response(prompt, call_type='speech', player_id=player['id'])
                speech = response_data.get('response', '').strip() or f"{player['nickname']}({player['id']}号)补充一点..."
                if self.discussion_active:
                    self.emit_speech(player['id'], speech)
            self._schedule_computer_discussion(player)
        delay = random.uniform(5, 15)
        threading.Timer(delay, speak).start()


    def process_voting(self, is_human_participating=True):
            self.voting_active = False
            self.socketio.emit('voting_ended')
            votes, vote_log_msg = {}, []
            
            # 处理人类玩家投票
            human_player = self.get_human_player()
            if is_human_participating and self.human_vote and human_player:
                target_player = self.get_player_by_id(self.human_vote)
                votes[self.human_vote] = votes.get(self.human_vote, 0) + 1
                vote_log_msg.append(f"{human_player['nickname']}(你) -> {target_player['nickname']}({self.human_vote}号)")
            
            # 并行处理AI玩家投票
            computers = [p for p in self.get_alive_players() if not p['is_human']]
            if computers:
                logging.info(f"开始并行处理 {len(computers)} 个AI玩家的投票...")
                
                # 使用线程池并行执行投票
                from concurrent.futures import ThreadPoolExecutor, as_completed
                import time
                
                def get_vote_for_player(player):
                    """为单个AI玩家获取投票，包含错误处理"""
                    try:
                        start_time = time.time()
                        vote_target_id = get_llm_vote(self.game_state, player['id'])
                        duration = time.time() - start_time
                        return {
                            'player': player,
                            'vote_target_id': vote_target_id,
                            'success': True,
                            'duration': duration
                        }
                    except Exception as e:
                        logging.error(f"玩家 {player['id']} 投票失败: {e}")
                        return {
                            'player': player,
                            'vote_target_id': None,
                            'success': False,
                            'error': str(e)
                        }
                
                # 并行执行所有AI投票
                vote_results = []
                with ThreadPoolExecutor(max_workers=min(len(computers), 4)) as executor:
                    # 提交所有投票任务
                    future_to_player = {
                        executor.submit(get_vote_for_player, player): player 
                        for player in computers
                    }
                    
                    # 收集结果
                    for future in as_completed(future_to_player):
                        result = future.result()
                        vote_results.append(result)
                
                # 处理投票结果
                successful_votes = 0
                failed_votes = 0
                
                for result in vote_results:
                    player = result['player']
                    if result['success'] and result['vote_target_id'] is not None:
                        vote_target_id = result['vote_target_id']
                        votes[vote_target_id] = votes.get(vote_target_id, 0) + 1
                        target_player = self.get_player_by_id(vote_target_id)
                        vote_log_msg.append(f"{player['nickname']}({player['id']}号) -> {target_player['nickname']}({vote_target_id}号)")
                        successful_votes += 1
                        logging.info(f"玩家 {player['id']} 投票成功 (耗时: {result.get('duration', 0):.2f}s)")
                    else:
                        failed_votes += 1
                        logging.warning(f"玩家 {player['id']} 投票失败，将被视为弃票")
                
                logging.info(f"投票并行处理完成: 成功 {successful_votes}/{len(computers)}")
                if failed_votes > 0:
                    logging.warning(f"有 {failed_votes} 个AI玩家投票失败")
            
            # 处理投票结果（保持原有逻辑）
            self.emit_log(f"投票详情: {', '.join(vote_log_msg) if vote_log_msg else '无有效投票'}")
            
            if not votes:
                self.emit_log("无人投票，平安日。")
            else:
                max_votes = max(votes.values())
                eliminated_ids = [pid for pid, count in votes.items() if count == max_votes]
                if len(eliminated_ids) > 1:
                    self.emit_log(f"平票！无人出局。")
                else:
                    eliminated_id = eliminated_ids[0]
                    player = self.get_player_by_id(eliminated_id)
                    self.eliminate_player(eliminated_id, 'vote')
                    if player:
                        self.emit_log(f"{player['nickname']}({eliminated_id}号)被投票淘汰，其身份是: {player['revealed_role']}。")
                    self.emit_game_state()
            
            if not self.check_game_over():
                self.start_night_phase()

    def process_voting_without_human(self):
        self.process_voting(is_human_participating=False)

    # --- 函数替换：process_night_action ---
    def process_night_action(self):
        """
        重构后的夜晚行动处理函数，逻辑更健壮。
        """
        # 检查游戏是否已经结束，以防万一
        if self.check_game_over():
            return

        target_id = None
        living_werewolves = self.get_werewolves()

        # 1. 如果没有存活的狼人，游戏应该已经结束了，但作为保险措施，我们将其视为平安夜
        if not living_werewolves:
            logging.warning("process_night_action被调用，但没有找到任何存活的狼人。这可能是一个状态错误。")
            self.emit_log("所有狼人均已被淘汰，平安夜。")
            self.next_day()
            return

        # 2. 检查是否是人类狼人玩家在行动
        if self.human_night_target:
            target_id = self.human_night_target
        else:
            # 3. 如果不是人类玩家，则寻找一个AI狼人来行动
            ai_werewolf = next((w for w in living_werewolves if not w['is_human']), None)
            
            if ai_werewolf:
                # 找到了AI狼人，让它决定目标
                target_id = get_llm_werewolf_kill(self.game_state, ai_werewolf['id'])
            else:
                # 4. 如果找不到AI狼人（意味着剩下的狼人都是人类玩家，但他们没有行动）
                # 这是一种边缘情况，同样视为平安夜
                logging.warning(f"轮到AI狼人行动，但只找到人类狼人。")
                self.emit_log("狼人阵营出现分歧，无人行动。")
                self.next_day()
                return
        
        # 5. 根据最终确定的target_id来执行淘汰
        if target_id:
            self.eliminate_player(target_id, 'night')
        else:
            # 如果target_id为None（例如LLM调用失败且没有备用方案），则为平安夜
            self.emit_log("狼人未能达成一致，平安夜。")
        
        # 6. 再次检查游戏是否结束，然后进入下一天
        if not self.check_game_over():
            self.next_day()

    def eliminate_player(self, player_id, reason):
        player = self.get_player_by_id(player_id)
        if player and player['is_alive']:
            player['is_alive'] = False
            player['revealed_role'] = player['role']
            day_log = next((log for log in self.game_state['game_log'] if log['day'] == self.game_state['day']), None)
            if not day_log:
                day_log = {"day": self.game_state['day'], "speeches": [], "eliminated_vote": None, "eliminated_night": None}
                self.game_state['game_log'].append(day_log)
            if reason == 'vote':
                day_log['eliminated_vote'] = player_id
            else:
                day_log['eliminated_night'] = player_id
            self._save_game_state()

    def get_player_by_id(self, player_id):
        return next((p for p in self.game_state['players'] if p['id'] == player_id), None)
    def get_human_player(self):
        return next((p for p in self.game_state['players'] if p['is_human']), None)
    def get_seer(self):
        return next((p for p in self.game_state['players'] if p['role'] == Role.SEER.value), None)
    def get_alive_players(self):
        return [p for p in self.game_state['players'] if p.get('is_alive')]
    def get_werewolves(self):
        return [p for p in self.get_alive_players() if p['role'] == Role.WEREWOLF.value]

    def emit_log(self, message):
        logging.info(message)
        self.socketio.emit('log_message', message)
        
    def emit_speech(self, player_id, text):
        """
        处理发言：向所有客户端发送文本，并根据游戏设置选择性地触发TTS。
        """
        player = self.get_player_by_id(player_id)
        nickname = player['nickname'] if player else f"玩家{player_id}"
        
        self.add_speech_to_log(player_id, text)
        self.socketio.emit('new_speech', {'playerId': player_id, 'text': text, 'nickname': nickname})
        self.emit_log(f"{nickname}({player_id}号)说: {text}")

        # --- 核心修改：只有在语音模式启用、TTS管理器存在且发言者是AI时才调用TTS ---
        if self.voice_enabled and self.tts_manager and player and not player.get('is_human', False):
            
            def run_tts_in_thread():
                try:
                    asyncio.run(self.tts_manager.stream_tts_for_player(player_id, text))
                except Exception as e:
                    logging.error(f"玩家 {player_id} 的TTS线程出错: {e}", exc_info=True)

            tts_thread = threading.Thread(target=run_tts_in_thread, daemon=True)
            tts_thread.start()
            logging.info(f"已为玩家 {player_id} 启动TTS线程 (语音模式)")
        else:
            logging.info(f"玩家 {player_id} 发言 (文字模式)")

    def emit_phase_update(self, phase_text):
        self.game_state['phase'] = phase_text
        self.socketio.emit('phase_update', phase_text)
        self._save_game_state()
    def emit_error(self, message):
        logging.error(message)
        self.socketio.emit('error_message', {'message': message})
    
    def emit_game_state(self):
        human_player = self.get_human_player()
        if not human_player: return
        
        # --- 修改：扩展颜色列表以支持更多玩家 ---
        # 准备一个足够长的颜色列表，或者使用颜色生成算法
        colors = [
            '#ffb3ba', '#bae1ff', '#baffc9', '#ffffba', '#ffdfba', 
            '#e0bbff', '#ffc9de', '#c9c9ff', '#f5c6a5', '#a5f5e0',
            '#e6a5f5', '#f5e6a5' 
        ] # 扩展到12种颜色

        state_for_client = {
            'players': [{
                'id': p['id'], 
                'nickname': p['nickname'], 
                'isAlive': p['is_alive'], 
                'isHuman': p['is_human'], 
                # 使用取模运算来安全地获取颜色，防止数组越界
                'color': colors[(p['id'] - 1) % len(colors)] 
            } for p in sorted(self.game_state['players'], key=lambda x: x['id'])], 
            'day': self.game_state['day'], 
            'phase': self.game_state['phase'], 
            'humanRole': human_player.get('role', '未知'), 
            'humanId': human_player['id']
        }
        self.socketio.emit('game_state', state_for_client)

        
    def check_game_over(self):
        werewolves = self.get_werewolves()
        good_players = [p for p in self.get_alive_players() if p['role'] != Role.WEREWOLF.value]
        winner = None
        if len(werewolves) == 0: winner = "好人阵营"
        elif len(werewolves) >= len(good_players): winner = "狼人"
        if winner:
            self.game_state['phase'] = GamePhase.ENDED.value
            self.discussion_active = self.voting_active = self.night_active = False
            end_message = f"🎉 游戏结束！{winner}获胜！"
            self.emit_log(end_message)
            all_roles_info = "-- - 最终身份公布 ---\n"
            sorted_players = sorted(self.game_state['players'], key=lambda p: p['id'])
            for player in sorted_players:
                all_roles_info += f"{player['nickname']}({player['id']}号) 的身份是: {player['role']}\n"
            self.emit_log(all_roles_info)
            self.socketio.emit('game_end', {'winner': winner})
            self._save_game_state()
            return True
        return False
