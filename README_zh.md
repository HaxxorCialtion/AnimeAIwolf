# AnimeAIwolf：LLM和TTS驱动的动漫角色扮演狼人杀

中文说明 | [English](README.md)

## 角色预览
<img src="./processed_images/1.jpg" width="80" height="80"> <img src="./processed_images/2.jpg" width="80" height="80"> <img src="./processed_images/3.jpg" width="80" height="80"> <img src="./processed_images/4.jpg" width="80" height="80"> <img src="./processed_images/5.jpg" width="80" height="80"> <img src="./processed_images/6.jpg" width="80" height="80"> <img src="./processed_images/7.jpg" width="80" height="80"> <img src="./processed_images/8.jpg" width="80" height="80">

## 项目简介
AnimeAIwolf 是一个基于大语言模型（LLM）和文本转语音（TTS）技术的动漫角色扮演狼人杀游戏。

## GitHub 源码安装教程
### 环境准备
1. 建议在虚拟环境中安装依赖：
   ```bash
   pip install -r requirements.txt
   ```
2. 运行程序：
   ```bash
   python app.py
   ```
**注意**：其余教程和一键启动包使用方法相同。

> 💖 如果您感觉满意，别忘了给我点个 Star！

## 一键启动包教程
核心配置文件为 `config.py`，您需要根据需求修改各项配置参数。

### 一、快速启动
1. **注册硅基流动账户**
   - 访问链接：[https://cloud.siliconflow.cn/i/vKgMJi1F](https://cloud.siliconflow.cn/i/vKgMJi1F)
   - 获取您的 API Key
2. **配置 API Key**
   - 在 `.env.example` 中找到 `SILICONFLOW_API_KEY`
   - 将您的硅基流动 API Key 替换 `your_api_key_here`
3. **启动程序**
   - 双击 `启动.bat`
   - 在浏览器中输入 `http://localhost:5000`

<img src="./images/tutorial/1.png" width="400" alt="LLM API Key 填入示例">

### 二、自定义角色
#### 2.1 角色昵称和个性设定
1. 找到 `2. 角色扮演与昵称配置` 部分
2. 修改各个角色的昵称和性格设定
3. **重要提醒**：`7` 号角色总是玩家角色

#### 2.2 角色头像设置
1. 进入主目录下的 `./images` 目录
2. 根据角色昵称顺序，修改或增减图片
3. 图片文件名需与角色 ID 一一对应

#### 2.3 角色语音配置
1. **配置路径**
   - 找到 `6. 音频与TTS配置` 部分
   - 修改 `reference_audios` 和 `reference_texts` 中的音频路径和对应文本
2. **重启设置**
   - 为确保修改生效，请删除主目录中的 `siliconflow_voices.json` 文件
   - 重新启动程序
3. **TTS 服务选择**
   
   **选项一：硅基流动 TTS 服务**
   - 使用配置文件中的默认设置
   
   **选项二：本地 GPT-SoVITS**
   - 针对不同角色训练的 GPT-SoVITS 模型表现更优异
   - 项目地址：[https://github.com/RVC-Boss/GPT-SoVITS](https://github.com/RVC-Boss/GPT-SoVITS)
   - 启动 API 服务：
     ```bash
     runtime\python.exe api_v2.py -a 127.0.0.1 -p 9880 -c GPT_SoVITS/configs/tts_infer.yaml
     ```
4. **音频播放调优**
   - 若角色语音重叠严重，可调整 `audio_play_delay` 参数

### 三、LLM 服务配置
#### 3.1 Ollama 本地模型
- 项目支持 Ollama 本地模型部署

#### 3.2 其他 LLM 服务
- 兼容 OpenAI 接口的其他 API 服务
- 在 `3. LLM 供应商与模型配置` 中修改 `openai_compatible` 相关配置

#### 3.3 推荐配置
**Deepseek-V3 + GPT-SoVITS** 组合

### 四、高级配置选项
#### 4.1 游戏核心配置
- **配置位置**：`1. 游戏核心配置` → `GAME_CONFIG`
- **可调整内容**：
  - 各身份角色数量
  - 对话发起规则
  - 其他游戏参数

⚠️ **重要提醒**：如果增加了 `players_count`，请同步更新以下配置：
- `2. 角色扮演与昵称配置`
- `6. 音频与TTS配置`

#### 4.2 LLM 生成参数
- **配置位置**：`4. LLM 生成参数配置`
- **功能**：微调各身份的表现（影响相对有限）

#### 4.3 提示词模板修改
- **修改位置**：`image_utils.py` → `construct_llm_prompt` 函数
- **注意事项**：请确保您理解修改的影响

⚠️ **警告**：修改此类参数前请确保您明白操作的后果

### 五、常见问题
#### Q: 使用硅基流动 TTS API 首次启动失败怎么办？
**A:** 这是已知 Bug，解决方法：
1. 关闭终端
2. 重新启动 `.bat` 文件即可

### 六、后续规划
- 在现有基础上开发更多有趣的多角色扮演 LLM 应用
- 持续优化游戏体验和AI表现

### 七、联系我们
如遇到 Bug 或需要技术支持，可通过以下方式联系：
- **📧 邮箱**：cialtion737410@sjtu.edu.cn & cialtion@outlook.com
- **📺 Bilibili**：https://www.bilibili.com/video/BV1MVemzUE9r
- **💬 QQ群**：暂未开放

---

## 贡献指南
欢迎提交 Issue 和 Pull Request 来改进项目！

## 开源协议
本项目采用 [MIT协议](LICENSE) 开源。