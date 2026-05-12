# Wiki 自动同步指南

当 LLM Wiki 能够持续反映您的背景笔记系统时，管理效果最佳。无需每次编写新内容时手动摄取文件，您可以编排一个端到端的自动化流水线。

本指南概述了适用于本地 Mac/Linux 环境的生产级 cron/launchd 策略。

## 两步架构

LLM Wiki Agent 的摄取是一个两步过程：
1. **同步到 `raw/`**：将文件从您的个人库/工具获取到代理的暂存区域。
2. **批量摄取**：在同步的目录上触发 `tools/ingest.py` 进行合成并编织到图谱中。

### 步骤 1：主编排脚本

在您的 wiki 根目录创建一个全面的 shell 脚本（`daily-automated-sync.sh`）：

```bash
#!/usr/bin/env bash
set -uo pipefail

# 定义变量
LAB_DIR="$HOME/projects/active/personal-wiki-lab"
LOG_FILE="$LAB_DIR/automation-cron.log"
DATE=$(date "+%Y-%m-%d %H:%M:%S")

echo "=====================================================" >> "$LOG_FILE"
echo "[$DATE] 开始自动 wiki 同步..." >> "$LOG_FILE"

cd "$LAB_DIR" || exit 1

# 1. 在此运行您的个人 Vault-to-Raw 符号链接脚本
# 示例: ./sync-raw.sh >> "$LOG_FILE" 2>&1

# 2. 使用您选择的 LLM 触发 Litellm 批量摄取
export LLM_MODEL="gemini/gemini-3-flash-preview"
export GEMINI_API_KEY="AIzaSy..."  # 或 export OPENAI_API_KEY

echo "[$DATE] 批量摄取 markdown 文件..." >> "$LOG_FILE"
find raw/ -type l -name "*.md" -o -type f -name "*.md" | \
while read file; do 
    python3 tools/ingest.py "$file" >> "$LOG_FILE" 2>&1
done

# 3. 修复图谱上下文（自动解决断开的语义链接）
echo "[$DATE] 修复断开的节点..." >> "$LOG_FILE"
python3 tools/heal.py >> "$LOG_FILE" 2>&1

echo "[$(date "+%Y-%m-%d %H:%M:%S")] 自动同步完成。" >> "$LOG_FILE"
echo "=====================================================" >> "$LOG_FILE"
```

不要忘记使其可执行：`chmod +x daily-automated-sync.sh`。

### 步骤 2：系统调度器（macOS launchd）

对于 macOS，`launchd` 比 `cron` 更加健壮。

在 `~/Library/LaunchAgents/com.personal-wiki-sync.plist` 创建一个 `.plist` 文件：

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.personal-wiki-sync</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>/Users/your-username/projects/active/personal-wiki-lab/daily-automated-sync.sh</string>
    </array>
    
    <!-- 每天凌晨 2:00 自动执行 -->
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>2</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>

    <!-- 如果错过了时间间隔，在系统启动时运行 -->
    <key>RunAtLoad</key>
    <true/>

    <!-- 诊断日志 -->
    <key>StandardOutPath</key>
    <string>/Users/your-username/projects/active/personal-wiki-lab/daemon.stdout.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/your-username/projects/active/personal-wiki-lab/daemon.stderr.log</string>
</dict>
</plist>
```

加载守护进程：
```bash
launchctl load ~/Library/LaunchAgents/com.personal-wiki-sync.plist
```

### 自我修复与健康监控
由于自动化在夜间静默运行，您的 `daemon.stderr.log` 确保您能够发现任何 API 失败。编排脚本包含 `tools/heal.py`，强烈建议使用：它将无缝拦截并构建您一天中积累但从未单独形式化的概念。