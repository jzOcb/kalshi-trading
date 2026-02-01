#!/bin/bash
# Kalshi Trading Skill - GitHub & ClawdHub 发布脚本

set -e

echo "🚀 Kalshi Trading Skill 发布流程"
echo "================================"

REPO_DIR="$HOME/kalshi-trading-repo"
SOURCE_DIR="/home/clawdbot/clawd/kalshi"

# 1. 复制文件到仓库目录
echo ""
echo "📦 步骤 1: 复制文件..."
rsync -av --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' --exclude='cache' "$SOURCE_DIR/" "$REPO_DIR/"
cd "$REPO_DIR"
echo "✅ 文件已复制到 $REPO_DIR"

# 2. 初始化 Git
echo ""
echo "📝 步骤 2: 初始化 Git 仓库..."
if [ ! -d ".git" ]; then
    git init
    echo "✅ Git 仓库已初始化"
else
    echo "ℹ️  Git 仓库已存在"
fi

# 3. 配置 Git 用户
git config user.name "Jason Zuo"
git config user.email "jzclaws1@gmail.com"

# 4. 提交所有文件
echo ""
echo "💾 步骤 3: 提交文件..."
git add -A
git commit -m "Initial commit: Kalshi Trading Skill for ClawdHub" || echo "ℹ️  没有新的改动"

# 5. 添加远程仓库
echo ""
echo "🔗 步骤 4: 配置远程仓库..."
REMOTE_URL="https://github.com/jzclaws/kalshi-trading.git"
if git remote | grep -q "origin"; then
    git remote set-url origin "$REMOTE_URL"
else
    git remote add origin "$REMOTE_URL"
fi
git branch -M main

# 6. 推送到 GitHub
echo ""
echo "⬆️  步骤 5: 推送到 GitHub..."
echo "⚠️  需要输入 GitHub Personal Access Token"
git push -u origin main

# 7. 安装 ClawdHub CLI（如需要）
echo ""
echo "📦 步骤 6: 检查 ClawdHub CLI..."
if ! command -v clawdhub &> /dev/null; then
    npm install -g clawdhub
fi

# 8. 发布到 ClawdHub
echo ""
echo "🌐 步骤 7: 发布到 ClawdHub..."
clawdhub publish

echo ""
echo "🎉 发布完成！"
