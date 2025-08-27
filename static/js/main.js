const socket = io();
let gameState = null;
let discussionTimer = null;
let isConnected = false;
let gameStarted = false;

let audioContext;
const audioQueues = {};
const isPlaying = {};
const playerGains = {};

function initAudioContext() {
    if (!audioContext && (window.AudioContext || window.webkitAudioContext)) {
        try {
            audioContext = new (window.AudioContext || window.webkitAudioContext)();
            if (audioContext.state === 'suspended') {
                audioContext.resume();
            }
            addLogEntry('音频系统已准备就绪。', 'success');
        } catch (e) {
            addLogEntry('错误：您的浏览器不支持Web Audio API。', 'error');
            console.error("Web Audio API is not supported in this browser", e);
        }
    }
}

socket.on('play_audio_chunk', function(data) {
    initAudioContext();
    if (!audioContext) return;

    const { playerId, audioChunk } = data;

    const binaryString = window.atob(audioChunk);
    const len = binaryString.length;
    const bytes = new Uint8Array(len);
    for (let i = 0; i < len; i++) {
        bytes[i] = binaryString.charCodeAt(i);
    }
    const arrayBuffer = bytes.buffer;

    audioContext.decodeAudioData(arrayBuffer, (decodedBuffer) => {
        if (!audioQueues[playerId]) {
            audioQueues[playerId] = [];
        }
        audioQueues[playerId].push(decodedBuffer);
        
        if (!isPlaying[playerId]) {
            playNextChunk(playerId);
        }
    }, (error) => {
        console.error(`Error decoding audio data for player ${playerId}:`, error);
        addLogEntry(`解码玩家 ${playerId} 的音频失败`, 'error');
    });
});

function playNextChunk(playerId) {
    if (!audioQueues[playerId] || audioQueues[playerId].length === 0) {
        isPlaying[playerId] = false;
        updateSpeakingIndicator(playerId, false);
        return;
    }

    isPlaying[playerId] = true;
    updateSpeakingIndicator(playerId, true);

    if (!playerGains[playerId]) {
        playerGains[playerId] = audioContext.createGain();
        playerGains[playerId].connect(audioContext.destination);
        const slider = document.querySelector(`.volume-slider[data-player-id='${playerId}']`);
        if (slider) {
            playerGains[playerId].gain.value = slider.value;
        }
    }

    const bufferToPlay = audioQueues[playerId].shift();
    const source = audioContext.createBufferSource();
    source.buffer = bufferToPlay;
    source.connect(playerGains[playerId]);
    source.start();

    source.onended = () => {
        playNextChunk(playerId);
    };
}

function handleVolumeChange(sliderElement, playerId) {
    const volume = parseFloat(sliderElement.value);
    if (audioContext && playerGains[playerId]) {
        playerGains[playerId].gain.setTargetAtTime(volume, audioContext.currentTime, 0.01);
    }
}

function updateSpeakingIndicator(playerId, isSpeaking) {
    const playerDiv = document.querySelector(`.player[data-player-id='${playerId}']`);
    if (playerDiv) {
        const indicator = playerDiv.querySelector('.speaking-indicator');
        if (indicator) {
            indicator.style.display = isSpeaking ? 'block' : 'none';
        }
    }
}

socket.on('connect', function() {
    isConnected = true;
    updateConnectionStatus();
    addLogEntry('已连接到游戏服务器', 'success');
});

socket.on('disconnect', function() {
    isConnected = false;
    updateConnectionStatus();
    addLogEntry('与服务器断开连接', 'error');
});

socket.on('seer_challenge_prompt', function(data) {
    let messageDiv = document.createElement('div');
    messageDiv.className = 'log-entry';
    messageDiv.style.borderLeftColor = '#ffc107';
    messageDiv.style.textAlign = 'center';

    let messageText = document.createElement('p');
    messageText.textContent = data.message;
    messageText.style.fontWeight = 'bold';
    messageDiv.appendChild(messageText);

    if (data.image_url) {
        let challengeImage = document.createElement('img');
        challengeImage.src = data.image_url;
        challengeImage.alt = '挑战提示';
        challengeImage.style.maxWidth = '80%';
        challengeImage.style.maxHeight = '150px';
        challengeImage.style.borderRadius = '10px';
        challengeImage.style.marginTop = '10px';
        messageDiv.appendChild(challengeImage);
    }

    let logArea = document.getElementById('logContent'); 
    if (logArea) {
        logArea.prepend(messageDiv); 
    } else {
        alert(data.message); 
    }
});

function updateConnectionStatus() {
    const statusElement = document.getElementById('connectionStatus');
    const startBtn = document.getElementById('startGameBtn');
    
    if (isConnected) {
        statusElement.textContent = '✅ 已连接到服务器';
        statusElement.className = 'connection-status connected';
        if (!gameStarted) {
            startBtn.disabled = false;
        }
    } else {
        statusElement.textContent = '❌ 连接断开';
        statusElement.className = 'connection-status disconnected';
        startBtn.disabled = true;
    }
}

function startGame() {
    if (!isConnected) return;
    
    const voiceEnabled = document.getElementById('voiceToggle').checked;

    if (voiceEnabled) {
        initAudioContext();
    }
    
    gameStarted = true;
    const startBtn = document.getElementById('startGameBtn');
    const startBtnText = document.getElementById('startBtnText');
    const startBtnLoading = document.getElementById('startBtnLoading');
    
    startBtn.disabled = true;
    startBtnText.classList.add('hidden');
    startBtnLoading.classList.remove('hidden');
    
    socket.emit('start_game', { voice_enabled: voiceEnabled });
    
    addLogEntry(`正在创建新游戏 (语音: ${voiceEnabled ? '开启' : '关闭'})...`, 'success');
}

socket.on('game_started', function() {
    document.getElementById('startGameScreen').style.display = 'none';
    document.getElementById('gameContent').style.display = 'flex';
    addLogEntry('新游戏已开始！正在分配身份...', 'success');
    clearDiscussionTimer();
    hideAllInputs();
});

socket.on('game_state', function(state) {
    gameState = state;
    updateGameDisplay();
    updateRoleInfo();
    updateInputValidators();
});

socket.on('phase_update', function(phase) {
    document.getElementById('phaseIndicator').textContent = phase;
});

socket.on('new_speech', function(data) {
    addSpeechBubble(data.playerId, data.text);
});

socket.on('log_message', function(message) {
    addLogEntry(message);
});

socket.on('error_message', function(data) {
    addLogEntry(data.message, 'error');
    alert(data.message);
});

socket.on('request_speech', function(data) {
    showSpeechInput();
});

socket.on('start_discussion', function() {
    showDiscussionInput();
    startDiscussionTimer();
});

socket.on('discussion_ended', function() {
    hideDiscussionInput();
    clearDiscussionTimer();
});

socket.on('start_voting', function() {
    showVoteInput();
});

socket.on('voting_ended', function() {
    hideVoteInput();
});

socket.on('start_night_werewolf', function() {
    showNightInput();
});

socket.on('start_night_villager', function() {
    hideAllInputs();
});

socket.on('request_seer_action', function(data) {
    addLogEntry('夜晚：预言家请选择查验目标。', 'info');
    showSeerInput();
});

socket.on('seer_result', function(data) {
    addLogEntry(`夜晚查验结果：${data.target_id}号玩家的身份是 - ${data.role}`, 'success');
});

socket.on('game_end', function(data) {
    alert(`🎉 游戏结束！${data.winner}获胜！`);
    hideAllInputs();
    clearDiscussionTimer();
    addLogEntry(`游戏结束！${data.winner}获胜！`, 'success');
    
    setTimeout(() => {
        document.getElementById('startGameScreen').style.display = 'flex';
        document.getElementById('gameContent').style.display = 'none';
        document.getElementById('speechArea').innerHTML = '';
        
        const startBtn = document.getElementById('startGameBtn');
        const startBtnText = document.getElementById('startBtnText');
        const startBtnLoading = document.getElementById('startBtnLoading');
        
        startBtn.disabled = !isConnected;
        startBtnText.classList.remove('hidden');
        startBtnLoading.classList.add('hidden');
        startBtnText.textContent = '再来一局';
        
        startBtn.onclick = function() {
            startGame();
        };
        
        addLogEntry('点击"再来一局"以开始新游戏', 'info');
    }, 3000);
});

function getPlayerAvatarPath(playerId) {
    return `/avatar/${playerId}`;
}

function updateInputValidators() {
    if (!gameState || !gameState.players) return;
    const maxPlayerId = gameState.players.length;
    
    const targetInputs = [
        document.getElementById('voteTarget'),
        document.getElementById('nightTarget'),
        document.getElementById('seerTarget')
    ];

    targetInputs.forEach(input => {
        if (input) {
            input.setAttribute('max', maxPlayerId);
        }
    });
}

function updateGameDisplay() {
    if (!gameState) return;
    
    const grid = document.getElementById('playersGrid');
    grid.innerHTML = '';
    
    gameState.players.forEach(player => {
        const playerDiv = document.createElement('div');
        playerDiv.className = `player ${!player.isAlive ? 'dead' : ''}`;
        playerDiv.dataset.playerId = player.id;
        const avatarPath = getPlayerAvatarPath(player.id);
        
        playerDiv.innerHTML = `
            <div class="speaking-indicator"></div>
            <div class="player-avatar" style="background-image: url('${avatarPath}');">
                <div class="player-id">${player.id}</div>
            </div>
            <div class="player-name">${player.nickname}</div>
            <div class="player-role">${player.isHuman ? '(你)' : '电脑'}</div>
            <div class="player-controls">
                <span class="volume-icon">🔊</span>
                <input type="range" min="0" max="1.5" step="0.05" value="1" 
                        class="volume-slider" data-player-id="${player.id}"
                        oninput="handleVolumeChange(this, ${player.id})"
                        onclick="event.stopPropagation()">
            </div>
        `;
        grid.appendChild(playerDiv);
    });
}

function updateRoleInfo() {
    if (!gameState || !gameState.humanId) return;
    const roleInfo = document.getElementById('roleInfo');
    const humanPlayer = gameState.players.find(p => p.isHuman);
    if(humanPlayer) {
        roleInfo.textContent = `你是 ${humanPlayer.nickname}(${gameState.humanId}号)，身份：${gameState.humanRole}`;
    }
}

function addSpeechBubble(playerId, text) {
    const speechArea = document.getElementById('speechArea');
    const bubble = document.createElement('div');
    bubble.className = 'speech-bubble';
    const avatarPath = getPlayerAvatarPath(playerId);

    let nickname = `玩家${playerId}`;
    if (gameState && gameState.players) {
        const player = gameState.players.find(p => p.id === playerId);
        if (player) {
            nickname = player.nickname;
        }
    }
    
    bubble.innerHTML = `
        <div class="avatar-small" style="background-image: url('${avatarPath}');"></div>
        <div class="speech-content">
            <strong>${nickname} (${playerId}号):</strong> ${text}
        </div>
    `;
    speechArea.appendChild(bubble);
    speechArea.scrollTop = speechArea.scrollHeight;
}

function addLogEntry(message, type = 'info') {
    const logContent = document.getElementById('logContent');
    const entry = document.createElement('div');
    entry.className = `log-entry ${type}`;
    entry.textContent = `[${new Date().toLocaleTimeString()}] ${message}`;
    logContent.appendChild(entry);
    logContent.scrollTop = logContent.scrollHeight;
}

function showSpeechInput() {
    hideAllInputs();
    document.getElementById('speechInput').classList.remove('hidden');
    document.getElementById('speechText').focus();
}

function showDiscussionInput() {
    hideAllInputs();
    document.getElementById('discussionInput').classList.remove('hidden');
    document.getElementById('discussionText').focus();
}

function showVoteInput() {
    hideAllInputs();
    document.getElementById('voteInput').classList.remove('hidden');
    document.getElementById('voteTarget').focus();
}

function showNightInput() {
    hideAllInputs();
    document.getElementById('nightInput').classList.remove('hidden');
    document.getElementById('nightTarget').focus();
}

function showSeerInput() {
    hideAllInputs();
    document.getElementById('seerInput').classList.remove('hidden');
    document.getElementById('seerTarget').focus();
}

function hideAllInputs() {
    document.getElementById('speechInput').classList.add('hidden');
    document.getElementById('discussionInput').classList.add('hidden');
    document.getElementById('voteInput').classList.add('hidden');
    document.getElementById('nightInput').classList.add('hidden');
    document.getElementById('seerInput').classList.add('hidden');
}

function startDiscussionTimer() {
    let seconds = gameState ? (gameState.discussion_time || 60) : 60;
    const timer = document.getElementById('timer');
    timer.classList.remove('hidden');
    
    discussionTimer = setInterval(() => {
        timer.textContent = `⏰ ${seconds}秒`;
        seconds--;
        if (seconds < 0) {
            clearDiscussionTimer();
        }
    }, 1000);
}

function clearDiscussionTimer() {
    if (discussionTimer) {
        clearInterval(discussionTimer);
        discussionTimer = null;
    }
    document.getElementById('timer').classList.add('hidden');
}

function sendSpeech() {
    const input = document.getElementById('speechText');
    const text = input.value.trim();
    if (!text) {
        addLogEntry('请输入发言内容', 'error');
        return;
    }
    socket.emit('send_speech', {text: text});
    input.value = '';
    hideAllInputs();
}

function sendDiscussionSpeech() {
    const input = document.getElementById('discussionText');
    const text = input.value.trim();
    if (!text) return;
    socket.emit('send_discussion_speech', {text: text});
    input.value = '';
}

function skipDiscussion() {
    socket.emit('skip_discussion');
}

function sendVote() {
    const input = document.getElementById('voteTarget');
    const target = parseInt(input.value);
    const maxPlayerId = gameState ? gameState.players.length : 7;
    if (!target || target < 1 || target > maxPlayerId) {
        addLogEntry(`请输入有效的玩家编号(1-${maxPlayerId})`, 'error');
        return;
    }
    if (!gameState) return;
    const humanPlayer = gameState.players.find(p => p.isHuman);
    if (target === humanPlayer.id) {
        addLogEntry('不能投票给自己', 'error');
        return;
    }
    const targetPlayer = gameState.players.find(p => p.id === target);
    if (!targetPlayer || !targetPlayer.isAlive) {
        addLogEntry('该玩家不存在或已被淘汰', 'error');
        return;
    }
    socket.emit('send_vote', {target: target});
    hideAllInputs();
}

function sendNightAction() {
    const input = document.getElementById('nightTarget');
    const target = parseInt(input.value);
    const maxPlayerId = gameState ? gameState.players.length : 7;
    if (!target || target < 1 || target > maxPlayerId) {
        addLogEntry(`请输入有效的玩家编号(1-${maxPlayerId})`, 'error');
        return;
    }
    if (!gameState) return;
    const humanPlayer = gameState.players.find(p => p.isHuman);
    if (target === humanPlayer.id) {
        addLogEntry('不能选择自己', 'error');
        return;
    }
    const targetPlayer = gameState.players.find(p => p.id === target);
    if (!targetPlayer || !targetPlayer.isAlive) {
        addLogEntry('该玩家已被淘汰', 'error');
        return;
    }
    socket.emit('send_night_action', {target: target});
    hideAllInputs();
}

function sendSeerAction() {
    const input = document.getElementById('seerTarget');
    const target = parseInt(input.value);
    const maxPlayerId = gameState ? gameState.players.length : 7;
    if (!target || target < 1 || target > maxPlayerId) {
        addLogEntry(`请输入有效的玩家编号(1-${maxPlayerId})`, 'error');
        return;
    }
    if (!gameState) return;
    const humanPlayer = gameState.players.find(p => p.isHuman);
    if (target === humanPlayer.id) {
        addLogEntry('不能查验自己', 'error');
        return;
    }
    const targetPlayer = gameState.players.find(p => p.id === target);
    if (!targetPlayer || !targetPlayer.isAlive) {
        addLogEntry('该玩家不存在或已被淘汰，无法查验', 'error');
        return;
    }
    socket.emit('send_seer_action', {target: target});
    hideAllInputs();
}

document.addEventListener('keypress', function(e) {
    if (e.key === 'Enter') {
        if (!document.getElementById('speechInput').classList.contains('hidden')) {
            sendSpeech();
        } else if (!document.getElementById('discussionInput').classList.contains('hidden')) {
            sendDiscussionSpeech();
        } else if (!document.getElementById('voteInput').classList.contains('hidden')) {
            sendVote();
        } else if (!document.getElementById('nightInput').classList.contains('hidden')) {
            sendNightAction();
        } else if (!document.getElementById('seerInput').classList.contains('hidden')) {
            sendSeerAction();
        }
    }
});

updateConnectionStatus();