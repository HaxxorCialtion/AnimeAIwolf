# image_utils.py

import os
import logging
from PIL import Image
from config import IMAGE_CONFIG, GAME_CONFIG

def ensure_images_folder():
    """确保images文件夹和处理后的文件夹存在"""
    images_folder = os.path.join(os.getcwd(), 'images')
    processed_folder = os.path.join(os.getcwd(), 'processed_images')
    if not os.path.exists(images_folder): os.makedirs(images_folder)
    if not os.path.exists(processed_folder): os.makedirs(processed_folder)
    return images_folder, processed_folder

def find_player_image(player_id, images_folder):
    """查找玩家原始图片文件"""
    for ext in IMAGE_CONFIG['supported_formats']:
        for filename in [f"{player_id}{ext}", f"player_{player_id}{ext}", f"玩家{player_id}{ext}"]:
            filepath = os.path.join(images_folder, filename)
            if os.path.exists(filepath): return filepath
    return None

def process_player_image(player_id, source_path, processed_folder):
    """处理玩家图片：调整大小、格式转换并保存"""
    try:
        with Image.open(source_path) as img:
            if img.mode != 'RGB':
                if img.mode == 'RGBA':
                    background = Image.new('RGB', img.size, (255, 255, 255))
                    background.paste(img, mask=img.split()[-1])
                    img = background
                else:
                    img = img.convert('RGB')
            
            img.thumbnail(IMAGE_CONFIG['avatar_size'], Image.Resampling.LANCZOS)
            canvas = Image.new('RGB', IMAGE_CONFIG['avatar_size'], (255, 255, 255))
            x, y = (IMAGE_CONFIG['avatar_size'][0] - img.width) // 2, (IMAGE_CONFIG['avatar_size'][1] - img.height) // 2
            canvas.paste(img, (x, y))
            
            output_path = os.path.join(processed_folder, f"{player_id}.jpg")
            canvas.save(output_path, format=IMAGE_CONFIG['output_format'], 
                        quality=IMAGE_CONFIG['quality'], optimize=True)
            logging.info(f"成功处理头像: {source_path} -> {output_path}")
            return output_path
    except Exception as e:
        logging.error(f"处理玩家{player_id}图片失败: {e}")
        return None

def create_default_avatar(player_id, processed_folder):
    """如果找不到图片，则创建纯色默认头像"""
    logging.warning(f"玩家{player_id}未找到图片，也未实现默认头像生成。")
    pass

def initialize_player_avatars():
    """初始化所有玩家头像 (新逻辑：如果源文件存在则强制覆盖)"""
    images_folder, processed_folder = ensure_images_folder()
    logging.info("开始检查并初始化玩家头像...")

    for player_id in range(1, GAME_CONFIG['players_count'] + 1):
        # 1. 优先在 'images' 文件夹中查找源文件
        source_path = find_player_image(player_id, images_folder)
        
        if source_path:
            # 2. 如果找到了源文件，则强制处理并覆盖旧头像
            logging.info(f"找到玩家 {player_id} 的源文件，将进行处理或覆盖...")
            if not process_player_image(player_id, source_path, processed_folder):
                # 如果处理失败，创建一个默认头像作为备用
                create_default_avatar(player_id, processed_folder)
        else:
            # 3. 如果没有找到源文件，才检查是否已存在处理过的头像
            processed_path = os.path.join(processed_folder, f"{player_id}.jpg")
            if not os.path.exists(processed_path):
                # 只有在处理过的头像也不存在的情况下，才创建默认头像
                logging.info(f"未找到玩家 {player_id} 的源文件且无已处理头像，将创建默认头像。")
                create_default_avatar(player_id, processed_folder)

    logging.info("玩家头像初始化检查完成")