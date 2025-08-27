# app.py

import sys
import os

# --- 诊断代码开始 ---
# 将当前脚本所在的目录手动添加到Python的搜索路径中
# 这是解决嵌入式Python包模块找不到问题的关键代码
script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)
# --- 诊断代码结束 ---

# --- 验证代码开始 ---
print("--- 诊断信息 ---")
print(f"当前工作目录 (os.getcwd): {os.getcwd()}")
print("Python 模块搜索路径 (sys.path):")
for path in sys.path:
    print(f"  - {path}")
print("--- 诊断信息结束 ---\n")
# --- 验证代码结束 ---

import os
import logging
from flask import Flask, render_template, send_file, send_from_directory
from flask_socketio import SocketIO, emit

from game_manager import WerewolfWebGame
from image_utils import initialize_player_avatars
from game_models import GameError, GamePhase, Role
from config import TTS_CONFIG
# --- 新增：导入上传工具 ---
from tts_manager import upload_siliconflow_voices_if_needed

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')

app = Flask(__name__)
app.config['SECRET_KEY'] = 'werewolf_game_secret_refactored'
socketio = SocketIO(app, cors_allowed_origins="*")

game = None

# ... (所有路由和SocketIO事件处理函数保持不变) ...
@app.route('/')
def index():
    initialize_player_avatars()
    return render_template('index.html')

@app.route('/images/<path:filename>')
def serve_from_images(filename):
    return send_from_directory('images', filename)

@app.route('/avatar/<int:player_id>')
def get_avatar(player_id):
    try:
        processed_folder = os.path.join(os.getcwd(), 'processed_images')
        avatar_path = os.path.join(processed_folder, f"{player_id}.jpg")
        if os.path.exists(avatar_path):
            return send_file(avatar_path, mimetype='image/jpeg')
        else:
            return "Avatar not found", 404
    except Exception as e:
        logging.error(f"获取玩家{player_id}头像失败: {e}")
        return "Error loading avatar", 500

@socketio.on('connect')
def handle_connect():
    global game
    game = None
    logging.info("客户端连接，游戏实例已重置")

@socketio.on('start_game')
def handle_start_game(data):
    global game
    try:
        voice_enabled = data.get('voice_enabled', TTS_CONFIG.get('enabled', False))
        game = WerewolfWebGame(socketio, voice_enabled=voice_enabled)
        logging.info(f"创建全新的游戏实例 (语音模式: {'启用' if voice_enabled else '禁用'})")
        
        game.start_game()
        logging.info("新游戏已启动")
        
        human_player = game.get_human_player()
        if human_player and human_player.get('role') == Role.SEER.value:
            image_url = '/images/egg_0.jpg' 
            emit('seer_challenge_prompt', {
                'message': '你抽到了预言家！但小心，一个特殊的挑战正在降临...祝你好运！',
                'image_url': image_url
            })

    except GameError as e:
        emit('error_message', {'message': str(e)})
    except Exception as e:
        logging.error(f"开始游戏失败: {e}", exc_info=True)
        emit('error_message', {'message': '开始游戏失败，请刷新页面重试'})

@socketio.on('send_speech')
def handle_send_speech(data):
    if game and game.game_started and data.get('text'):
        game.handle_human_speech(data['text'])

@socketio.on('send_discussion_speech')
def handle_discussion_speech(data):
     if game and game.discussion_active and data.get('text'):
        player = game.get_human_player()
        if player and player['is_alive']:
            game.emit_speech(player['id'], data['text'])

@socketio.on('skip_discussion')
def handle_skip_discussion():
    if game: game.end_discussion()

@socketio.on('send_vote')
def handle_vote(data):
    if game and game.voting_active and data.get('target'):
        try:
            game.human_vote = int(data['target'])
            game.process_voting()
        except (ValueError, TypeError):
            game.emit_error("无效的投票目标")

@socketio.on('send_night_action')
def handle_night_action(data):
    if game and game.night_active and data.get('target'):
        try:
            game.human_night_target = int(data['target'])
            game.process_night_action()
        except (ValueError, TypeError):
            game.emit_error("无效的夜晚目标")

@socketio.on('send_seer_action')
def handle_seer_action(data):
    if game and game.game_started and data.get('target'):
        seer = game.get_seer()
        if seer and seer['is_human']:
            try:
                target_id = int(data['target'])
                
                is_pre_game = game.game_state['phase'] == GamePhase.PRE_GAME_SEER.value
                
                day = 0 if is_pre_game else game.game_state['day']
                game.process_seer_check(seer, target_id, day=day)
                
                if is_pre_game:
                    game.start_day_phase()
                else:
                    game._handle_werewolf_turn()

            except (ValueError, TypeError):
                game.emit_error("无效的查验目标")

@socketio.on('restart_game')
def handle_restart_game():
    logging.info("收到重新加载游戏请求")
    socketio.emit('reload_page')

@socketio.on('disconnect')
def handle_disconnect():
    logging.info("客户端断开连接")


if __name__ == '__main__':
    print("=" * 60)
    print("狼人杀游戏服务器启动中...")
    print("=" * 60)
    
    # 初始化头像
    print("正在初始化玩家头像...")
    initialize_player_avatars()
    print("头像初始化完成")
    
    # 检查和设置TTS
    tts_provider = TTS_CONFIG.get("default_provider")
    tts_enabled = TTS_CONFIG.get("enabled", False)
    
    if tts_enabled:
        print(f"\nTTS功能已启用，使用供应商: {tts_provider}")
        
        if tts_provider == "siliconflow":
            print("正在配置SiliconFlow TTS...")
            
            # 检查配置
            siliconflow_config = TTS_CONFIG['providers'].get('siliconflow', {})
            api_key = siliconflow_config.get('api_key', '')
            
            if not api_key or 'your-siliconflow-api-key-here' in api_key:
                print("错误: SiliconFlow API Key未配置！")
                print("请在config.py中设置正确的API Key")
                print("将以纯文字模式启动（无语音）")
            else:
                print("API Key已配置")
                print("开始音色上传和验证...")
                
                try:
                    # 调用增强的上传函数
                    upload_success = upload_siliconflow_voices_if_needed()
                    
                    if upload_success:
                        print("SiliconFlow TTS配置完成！")
                        print("游戏中AI角色将有语音播放")
                    else:
                        print("警告: TTS配置未完全成功，部分功能可能受限")
                        print("建议检查API配额和网络连接")
                        print("游戏仍可正常运行（无语音或部分语音）")
                        
                except Exception as e:
                    print(f"错误: TTS配置过程中出现错误: {e}")
                    print("将以纯文字模式启动")
                    
        elif tts_provider == "local_gsv":
            print("使用本地GSV TTS服务")
            print("请确保GSV服务在 http://127.0.0.1:9880 运行")
        else:
            print(f"警告: 未知的TTS供应商: {tts_provider}")
            print("将以纯文字模式启动")
    else:
        print("TTS功能已禁用，游戏将以纯文字模式运行")
    
    # 启动服务器
    print("\n" + "=" * 60)
    print("启动游戏服务器...")
    print("访问地址: http://localhost:5000")
    print("开始您的狼人杀之旅！")
    print("=" * 60)
    
    try:
        socketio.run(app, debug=True, host='0.0.0.0', port=5000)
    except KeyboardInterrupt:
        print("\n游戏服务器已停止")
    except Exception as e:
        print(f"\n错误: 服务器启动失败: {e}")
        print("请检查端口5000是否被占用")