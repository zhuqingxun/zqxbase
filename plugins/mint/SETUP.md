# MINT 插件配置指南

## 快速开始

MINT 包含 4 个阶段，**仅 Stage 1（Transcribe）需要配置**，Stage 2-4 无需任何外部配置。

如果你已有转录稿（来自飞书妙记、讯飞、Whisper 等），可以直接从 Stage 2 开始使用，跳过本配置。

## Stage 1 配置（Transcribe）

Stage 1 使用阿里云百炼（DashScope）Fun-ASR 进行语音识别，仅需 **1 个环境变量**。

### 第一步：获取 API Key

1. 注册/登录 [阿里云百炼平台](https://bailian.console.aliyun.com/)
2. 进入 **API-KEY 管理** 页面
3. 创建一个 API Key（`sk-` 开头）

### 第二步：设置环境变量

```bash
# Linux / macOS
export DASHSCOPE_API_KEY="sk-your-api-key-here"

# Windows (PowerShell)
$env:DASHSCOPE_API_KEY = "sk-your-api-key-here"

# Windows (Git Bash)
export DASHSCOPE_API_KEY="sk-your-api-key-here"
```

建议将此行添加到 shell 配置文件（`~/.bashrc`、`~/.zshrc` 或 PowerShell Profile）以持久化。

### 第三步：验证

```
/mint:transcribe ~/test-audio.mp3 测试
```

## 可选配置

| 环境变量 | 说明 | 默认值 |
|----------|------|--------|
| `DASHSCOPE_API_KEY` | 百炼 API Key（**必需**） | 无 |
| `MINT_BW_DASHSCOPE_ENTRY` | Bitwarden CLI 中存储 API Key 的条目名称 | 无（不使用 Bitwarden） |

如果设置了 `MINT_BW_DASHSCOPE_ENTRY`，当 `DASHSCOPE_API_KEY` 未设置时，脚本会尝试从 Bitwarden CLI 获取密钥（需要 `bw` CLI 已安装并解锁）。

## 运行依赖

- **Python 3.10+**
- **uv**（Python 包管理器）— [安装指南](https://docs.astral.sh/uv/getting-started/installation/)
- Stage 1 的 Python 依赖（`dashscope`、`requests`）由 `uv run --script` 自动安装，无需手动操作

## 不使用 Stage 1 的用户

如果你使用其他 ASR 工具转录，只需将转录稿保存为以下格式即可从 Stage 2 开始：

```
HH:MM:SS Speaker N

发言内容...

HH:MM:SS Speaker M

发言内容...
```

然后使用 `/mint:refine <工作目录>` 开始处理。
