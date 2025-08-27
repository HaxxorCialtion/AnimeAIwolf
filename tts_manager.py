# tts_manager.py

import asyncio
import aiohttp
import os
import re
import json
import logging
import base64
import requests
import time
import threading
from typing import List
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from config import TTS_CONFIG
from openai import OpenAI

# 用于存储SiliconFlow返回的完整声音URI
VOICE_MAP_FILE = 'siliconflow_voices.json'

def _load_voice_map():
    """加载已存储的声音URI映射文件。"""
    if not os.path.exists(VOICE_MAP_FILE):
        return {}
    try:
        with open(VOICE_MAP_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (IOError, json.JSONDecodeError):
        return {}

def _save_voice_map(data: dict):
    """保存声音URI映射到文件。"""
    try:
        with open(VOICE_MAP_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except IOError as e:
        logging.error(f"保存声音映射文件失败: {e}")

def _is_valid_voice_uri(uri: str) -> bool:
    """检查Voice URI格式是否有效"""
    return (isinstance(uri, str) and 
            uri.startswith('speech:') and 
            uri.count(':') >= 3 and
            'None' not in uri)

def upload_siliconflow_voices_if_needed():
    """
    智能上传 SiliconFlow音色：
    1. 检查现有URI格式是否正确
    2. 重新上传格式不正确或缺失的音色
    3. 验证上传结果
    """
    config = TTS_CONFIG['providers'].get('siliconflow')
    local_config = TTS_CONFIG['providers'].get('local_gsv')
    if not config or not local_config:
        logging.warning("SiliconFlow或本地TTS配置未找到，跳过上传。")
        return False

    api_key = config.get('api_key')
    if not api_key or "your-siliconflow-api-key-here" in api_key:
        logging.warning("SiliconFlow API Key未配置，跳过上传。请在config.py中配置。")
        return False

    print("\n" + "="*60)
    print("🎵 SiliconFlow TTS 音色上传检查")
    print("="*60)

    headers = {"Authorization": f"Bearer {api_key}"}
    voice_map = _load_voice_map()
    
    # 检查现有URI格式
    invalid_uris = []
    missing_players = []
    
    for player_id, voice_name in config['voice_names'].items():
        existing_uri = voice_map.get(str(player_id))
        if not existing_uri:
            missing_players.append((player_id, voice_name))
            print(f"❌ 玩家 {player_id} ({voice_name}) 缺失音色URI")
        elif not _is_valid_voice_uri(existing_uri):
            invalid_uris.append((player_id, voice_name, existing_uri))
            print(f"⚠️  玩家 {player_id} ({voice_name}) URI格式不正确: {existing_uri}")
        else:
            print(f"✅ 玩家 {player_id} ({voice_name}) URI格式正确")
    
    # 需要上传的玩家
    players_to_upload = missing_players + [(pid, vname, _) for pid, vname, _ in invalid_uris]
    
    if not players_to_upload:
        print("🎉 所有音色URI格式正确，无需重新上传")
        return True
    
    print(f"\n🔄 需要上传 {len(players_to_upload)} 个音色...")
    
    success_count = 0
    new_voice_map = voice_map.copy()
    
    for player_data in players_to_upload:
        player_id = player_data[0]
        voice_name = player_data[1]
        
        ref_audio_path = local_config['reference_audios'].get(player_id)
        ref_text = local_config['reference_texts'].get(player_id)

        if not ref_audio_path or not os.path.exists(ref_audio_path):
            print(f"❌ 玩家 {player_id} 参考音频不存在: {ref_audio_path}")
            continue

        print(f"\n🔤 上传玩家 {player_id} ({voice_name})...")
        
        try:
            with open(ref_audio_path, "rb") as f:
                files = {"file": f}
                data = { 
                    "model": config['model'], 
                    "customName": voice_name, 
                    "text": ref_text 
                }
                response = requests.post(
                    config['upload_api_url'], 
                    headers=headers, 
                    files=files, 
                    data=data, 
                    timeout=60
                )
                response.raise_for_status()
                response_data = response.json()
                
                voice_uri = response_data.get("uri")
                if not voice_uri:
                    print(f"   ❌ 响应中缺少URI字段")
                    print(f"   响应内容: {response_data}")
                    continue
                
                # 验证URI格式
                if _is_valid_voice_uri(voice_uri):
                    print(f"   ✅ 上传成功: {voice_uri}")
                    new_voice_map[str(player_id)] = voice_uri
                    success_count += 1
                else:
                    print(f"   ❌ URI格式仍然不正确: {voice_uri}")
                    # 尝试查找其他可能的完整URI字段
                    for key, value in response_data.items():
                        if _is_valid_voice_uri(str(value)):
                            print(f"   🔍 在字段 '{key}' 找到有效URI: {value}")
                            new_voice_map[str(player_id)] = str(value)
                            success_count += 1
                            break
                    else:
                        print(f"   ❌ 无法找到有效的URI格式")
                
        except requests.exceptions.HTTPError as e:
            print(f"   ❌ HTTP错误 {e.response.status_code}: {e.response.text}")
        except Exception as e:
            print(f"   ❌ 上传异常: {e}")
    
    # 保存结果
    if success_count > 0:
        _save_voice_map(new_voice_map)
        print(f"\n💾 已保存 {success_count} 个音色URI到映射文件")
        
        # 验证第一个成功上传的音色
        if _test_first_voice_tts(new_voice_map, config):
            print("✅ TTS功能验证成功")
        else:
            print("⚠️  TTS功能验证失败，但音色已上传")
    
    print("\n" + "="*60)
    total_needed = len(players_to_upload)
    if success_count == total_needed:
        print(f"🎉 音色上传完成! ({success_count}/{total_needed})")
        return True
    else:
        print(f"⚠️  部分音色上传失败 ({success_count}/{total_needed})")
        return success_count > 0

def _test_first_voice_tts(voice_map: dict, config: dict) -> bool:
    """测试第一个音色的TTS功能"""
    if not voice_map:
        return False
    
    try:
        print("\n🧪 测试TTS功能...")
        player_id = list(voice_map.keys())[0]
        voice_uri = voice_map[player_id]
        
        client = OpenAI(
            api_key=config['api_key'],
            base_url="https://api.siliconflow.cn/v1"
        )
        
        with client.audio.speech.with_streaming_response.create(
            model=config['model'],
            voice=voice_uri,
            input="TTS功能测试成功",
            response_format="mp3"
        ) as response:
            if response.http_response.status_code == 200:
                print(f"   ✅ 玩家 {player_id} TTS测试通过")
                return True
            else:
                print(f"   ❌ TTS测试失败，状态码: {response.http_response.status_code}")
                return False
                
    except Exception as e:
        print(f"   ❌ TTS测试异常: {e}")
        return False

class TTSManager:
    def __init__(self, socketio):
        self.socketio = socketio
        self.provider_name = TTS_CONFIG.get("default_provider", "local_gsv")
        self.config = TTS_CONFIG['providers'].get(self.provider_name)
        
        if not self.config:
            raise ValueError(f"TTS配置错误: 未找到名为 '{self.provider_name}' 的供应商配置。")

        self.voice_map = {}
        if self.provider_name == "siliconflow":
            self.voice_map = _load_voice_map()
        
        # 初始化线程池执行器
        self.executor = ThreadPoolExecutor(max_workers=TTS_CONFIG.get('concurrency', 2))

        logging.info(f"TTS管理器已初始化，使用供应商: {self.provider_name}")

    def _split_text(self, text: str) -> List[str]:
        """将长文本按标点分割成适合TTS的短句列表。"""
        text = text.strip()
        if not text: 
            return []
        
        # 定义标点符号分隔符（中英文）
        separators = r'[。！？；：,.!?;:\n]'
        
        # 按标点符号切分，保留分隔符
        parts = re.split(f'({separators})', text)
        
        chunks = []
        current_chunk = ""
        
        for part in parts:
            if part.strip():  # 跳过空字符串
                current_chunk += part
                # 如果是标点符号，结束当前块
                if re.match(separators, part):
                    if current_chunk.strip():
                        chunks.append(current_chunk.strip())
                    current_chunk = ""
        
        # 添加最后一块（如果有）
        if current_chunk.strip():
            chunks.append(current_chunk.strip())
        
        # 过滤掉太短的块
        chunks = [chunk for chunk in chunks if len(chunk.strip()) > 1]
        
        return chunks

    async def _stream_local_gsv(self, player_id: int, chunks: List[str]):
        """处理本地GSV TTS的逻辑。"""
        # 添加TTS播放延迟，但1号玩家（首发）不延迟
        if player_id != 1:
            audio_delay = TTS_CONFIG.get('audio_play_delay', 3.0)
            logging.info(f"玩家 {player_id} TTS播放延迟 {audio_delay} 秒（防止拥堵）")
            await asyncio.sleep(audio_delay)
        else:
            logging.info(f"玩家 {player_id} 为首发，无需延迟")
        
        ref_audio_path = self.config['reference_audios'].get(player_id)
        prompt_text = self.config['reference_texts'].get(player_id)
        if not ref_audio_path or not prompt_text:
            logging.error(f"玩家 {player_id} 的本地TTS配置缺失。")
            return
        
        params = {
            "text_lang": "zh", 
            "ref_audio_path": os.path.abspath(ref_audio_path), 
            "prompt_lang": "zh", 
            "prompt_text": prompt_text, 
            "media_type": "wav", 
            "temperature": 0.8
        }
        
        async with aiohttp.ClientSession() as session:
            for chunk_text in chunks:
                req_params = params.copy()
                req_params['text'] = chunk_text
                try:
                    async with session.get(self.config['api_url'], params=req_params, timeout=60) as response:
                        if response.status == 200:
                            audio_data = await response.read()
                            encoded_chunk = base64.b64encode(audio_data).decode('utf-8')
                            self.socketio.emit('play_audio_chunk', {
                                'playerId': player_id, 
                                'audioChunk': encoded_chunk
                            })
                        else:
                            logging.error(f"本地TTS请求失败: {response.status}, {await response.text()}")
                except Exception as e:
                    logging.error(f"本地TTS请求异常: {e}")

    def _generate_siliconflow_chunk_sync(self, voice_uri: str, text_chunk: str, chunk_index: int = 0) -> bytes | None:
        """
        根据成功案例优化的同步音频生成函数。
        每次调用都创建独立的OpenAI客户端实例，确保线程安全。
        """
        try:
            logging.info(f"正在生成音频块 {chunk_index + 1}: {text_chunk[:30]}{'...' if len(text_chunk) > 30 else ''}")
            
            # 调试信息：显示详细的请求参数
            logging.info(f"调试信息 - API Key前缀: {self.config['api_key'][:20]}...")
            logging.info(f"调试信息 - Base URL: https://api.siliconflow.cn/v1")
            logging.info(f"调试信息 - Model: {self.config['model']}")
            logging.info(f"调试信息 - Voice URI: {voice_uri}")
            logging.info(f"调试信息 - Text length: {len(text_chunk)}")
            logging.info(f"调试信息 - Response format: mp3")
            
            # 每次调用都创建新的客户端实例，避免线程间冲突
            client = OpenAI(
                api_key=self.config['api_key'],
                base_url="https://api.siliconflow.cn/v1"
            )
            
            # 验证voice_uri格式
            if not voice_uri or not voice_uri.startswith('speech:'):
                logging.error(f"Voice URI格式不正确: {voice_uri}")
                return None
            
            # 使用流式响应创建音频
            logging.info(f"开始调用OpenAI客户端生成音频块 {chunk_index + 1}")
            with client.audio.speech.with_streaming_response.create(
                model=self.config['model'],
                voice=voice_uri,
                input=text_chunk,
                response_format="mp3"
            ) as response:
                # 记录响应状态
                logging.info(f"收到响应，状态: {response.http_response.status_code}")
                # 读取所有音频数据到内存
                audio_bytes = response.read()
            
            logging.info(f"音频块 {chunk_index + 1} 生成完成，大小: {len(audio_bytes)} 字节")
            return audio_bytes
            
        except Exception as e:
            # 详细的错误信息
            logging.error(f"SiliconFlow音频块 {chunk_index + 1} 生成失败")
            logging.error(f"错误详情: {type(e).__name__}: {str(e)}")
            logging.error(f"失败的文本: {text_chunk}")
            logging.error(f"使用的Voice URI: {voice_uri}")
            return None

    async def _stream_siliconflow(self, player_id: int, chunks: List[str]):
        """
        通过线程池并发执行同步的TTS请求，然后按顺序将结果发送到客户端。
        """
        # 添加TTS播放延迟，但1号玩家（首发）不延迟
        if player_id != 1:
            audio_delay = TTS_CONFIG.get('audio_play_delay', 3.0)
            logging.info(f"玩家 {player_id} TTS播放延迟 {audio_delay} 秒（防止拥堵）")
            await asyncio.sleep(audio_delay)
        else:
            logging.info(f"玩家 {player_id} 为首发，无需延迟")
        
        # 调试信息：打印voice映射情况
        logging.info(f"调试信息 - 当前voice映射内容: {self.voice_map}")
        logging.info(f"调试信息 - 查找玩家 {player_id} 的voice URI...")
        
        voice_uri = self.voice_map.get(str(player_id))
        if not voice_uri:
            logging.error(f"在 '{VOICE_MAP_FILE}' 中找不到玩家 {player_id} 的声音URI。")
            logging.error(f"可用的玩家ID: {list(self.voice_map.keys())}")
            
            # 尝试重新加载voice映射文件
            logging.info("尝试重新加载voice映射文件...")
            self.voice_map = _load_voice_map()
            logging.info(f"重新加载后的voice映射: {self.voice_map}")
            
            voice_uri = self.voice_map.get(str(player_id))
            if not voice_uri:
                logging.error(f"重新加载后仍然找不到玩家 {player_id} 的声音URI")
                return
        
        logging.info(f"找到玩家 {player_id} 的Voice URI: {voice_uri}")
        
        if not chunks:
            logging.warning(f"玩家 {player_id} 没有可处理的文本块")
            return
        
        logging.info(f"开始为玩家 {player_id} 生成 {len(chunks)} 个音频块...")
        
        loop = asyncio.get_running_loop()
        
        # 为每个文本块创建一个在线程池中运行的任务
        tasks = [
            loop.run_in_executor(
                self.executor, 
                self._generate_siliconflow_chunk_sync, 
                voice_uri, 
                chunk,
                i  # 添加块索引用于日志
            )
            for i, chunk in enumerate(chunks)
        ]
        
        try:
            # 等待所有线程任务完成
            generated_audio_chunks = await asyncio.gather(*tasks, return_exceptions=True)
            logging.info(f"玩家 {player_id} 的所有音频块生成完毕")

            # 按顺序发送结果
            successful_count = 0
            for i, audio_data in enumerate(generated_audio_chunks):
                if isinstance(audio_data, Exception):
                    logging.error(f"音频块 {i + 1} 生成异常: {audio_data}")
                    continue
                    
                if audio_data:
                    try:
                        encoded_chunk = base64.b64encode(audio_data).decode('utf-8')
                        self.socketio.emit('play_audio_chunk', {
                            'playerId': player_id, 
                            'audioChunk': encoded_chunk
                        })
                        successful_count += 1
                        # 添加小延迟确保音频块有序播放
                        await asyncio.sleep(0.1)
                    except Exception as e:
                        logging.error(f"发送音频块 {i + 1} 时出错: {e}")
                else:
                    logging.warning(f"音频块 {i + 1} 为空，跳过")
            
            logging.info(f"玩家 {player_id} 成功发送了 {successful_count}/{len(chunks)} 个音频块")
            
        except Exception as e:
            logging.error(f"玩家 {player_id} 的音频生成过程中出现异常: {e}")

    async def stream_tts_for_player(self, player_id: int, text: str):
        """
        总入口函数：分割文本并根据配置调用相应的TTS处理函数。
        简单的延迟机制，确保1号玩家无延迟，其他玩家有配置的延迟。
        """
        if not text or not text.strip():
            logging.warning(f"玩家 {player_id} 的文本为空，跳过TTS")
            return
            
        chunks = self._split_text(text)
        if not chunks: 
            logging.warning(f"玩家 {player_id} 文本无法分割，跳过TTS: {text}")
            return

        logging.info(f"玩家 {player_id} 文本已切分为 {len(chunks)} 个块")
        for i, chunk in enumerate(chunks):
            logging.debug(f"  块 {i + 1}: {chunk[:50]}{'...' if len(chunk) > 50 else ''}")

        try:
            if self.provider_name == "local_gsv":
                await self._stream_local_gsv(player_id, chunks)
            elif self.provider_name == "siliconflow":
                await self._stream_siliconflow(player_id, chunks)
            else:
                logging.error(f"不支持的TTS供应商: {self.provider_name}")
        except Exception as e:
            logging.error(f"玩家 {player_id} TTS处理失败: {e}", exc_info=True)