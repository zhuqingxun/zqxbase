---
description: MINT 流水线 Stage 1: 语音转文本——调用阿里云百炼平台将录音文件转为带时间戳和说话人标记的原始口水稿。当用户提到"语音转文字""录音转文本""转录""transcribe""把录音转成文字""ASR"时使用。支持 mp3/m4a/wav/flac/ogg 等常见音频格式，自动启用说话人分离。
argument-hint: "<音频文件路径> <人名或会议名>"
---


# mint:transcribe — 语音转文本

调用阿里云百炼平台（DashScope Fun-ASR）将录音转为口水稿，自动启用说话人分离和标点恢复。

## 用法

```
/mint:transcribe <音频文件路径> <人名或会议名>
```

示例：
- `/mint:transcribe D:\Downloads\interview.mp3 李玉蕾访谈`
- `/mint:transcribe "D:\华为云盘\录音\meeting.m4a" 产品评审会`

## 执行流程

### 第一步：解析参数

从用户指令中提取：
- **音频路径**：本地文件绝对路径
- **名称**：用于目录命名和输出文件命名

验证音频文件存在，检查格式是否支持（mp3/m4a/wav/flac/ogg/opus/wma/aac/mp4/avi/mkv/mov）。

### 第二步：初始化工作目录

判断目录结构是否已存在。如果是首次运行，在音频文件所在目录下创建完整的 MINT 工作目录：

```
{name}/
├── 01_音频/           ← 复制或移动原始音频到此处
├── 02_原始稿/
│   └── old/
├── 03_校对稿/
│   └── old/
├── 04_编辑稿/
│   └── old/
├── 05_分析稿/
│   └── old/
└── meta.yaml
```

创建初始 `meta.yaml`：
```yaml
project: "{name}"
created: {当前日期}
source_audio: "{音频文件名}"

stages:
  transcribe:
    status: pending
  refine:
    status: pending
  polish:
    status: pending
  extract:
    status: pending

revisions: []
```

如果工作目录已存在（meta.yaml 已有），跳过创建，直接进入转录。

### 第三步：检查依赖

确认转录脚本的依赖可用：
```bash
uv run --script ~/.claude/commands/mint/scripts/transcribe.py --help 2>/dev/null || echo "需要安装依赖"
```

脚本使用 PEP 723 inline metadata，`uv run --script` 会自动处理依赖安装。

### 第四步：执行转录

运行转录脚本：
```bash
uv run --script ~/.claude/commands/mint/scripts/transcribe.py "<音频路径>" "<名称>"
```

脚本会：
1. 读取 API Key（从环境变量 `DASHSCOPE_API_KEY` 或密钥文件）
2. 上传音频文件到阿里云 OSS（签名 URL，转录后自动清理）
3. 提交异步转录任务（Fun-ASR 模型 + 说话人分离）
4. 轮询等待完成（每 5 秒检查，显示进度）
5. 解析结果，合并同一说话人的连续语句
6. 格式化输出为 markdown

### 第五步：整理输出

脚本默认输出到音频同目录。需要将输出文件移动到工作目录中：

1. 将脚本输出的 `{name}_原始.md` 移动到 `{工作目录}/02_原始稿/{name}_原始稿.md`
2. 如果 `02_原始稿/` 中已有同名文件，先将旧版移动到 `02_原始稿/old/{name}_原始稿_v{N}.md`

### 第六步：更新 meta.yaml

更新 transcribe 阶段状态：
```yaml
stages:
  transcribe:
    status: completed
    version: 1  # 或递增
    completed_at: {当前 ISO 时间}
    params:
      model: "fun-asr"
      speakers: {识别到的说话人数}
```

如果是重新转录，version 递增。

### 第七步：验证并报告

1. 确认输出文件已在正确位置
2. 报告：
   - 工作目录路径
   - 输出文件路径和字数
   - 识别到的说话人数量
   - 音频时长
3. 提示后续步骤：`/mint:refine` 进行逐字稿清洁

## 输出格式

```markdown
00:00:12 Speaker 1

这个问题很好，我觉得核心还是在于我们整个选拔机制的问题。

00:00:35 Speaker 2

你说的选拔机制，具体是指哪些环节？

00:00:42 Speaker 1

首先是任职资格体系，这个已经成为一个枷锁了...
```

- 时间戳格式：`HH:MM:SS`
- 说话人标记：`Speaker 1`、`Speaker 2`...（保留数字编号）
- 同一说话人的连续发言合并为一段
- 输出路径：`{工作目录}/02_原始稿/{name}_原始稿.md`

## API 配置

- **平台**：阿里云百炼（DashScope）
- **模型**：Fun-ASR（Paraformer-v2，中文 SOTA 级别）
- **API Key**：从密钥文件读取「阿里bailian (标准 DashScope)」条目
- **功能开关**：说话人分离 + 标点恢复 + 时间戳

## 异常处理

| 情况 | 处理 |
|------|------|
| 音频文件不存在 | 报错并提示检查路径 |
| API Key 无效 | 提示检查密钥文件或环境变量 |
| 转录任务失败 | 显示错误信息，建议检查音频格式或文件大小 |
| 超时（>30 分钟未完成） | 报告 task_id 供手动查询 |
| 说话人分离失败 | 降级为不分说话人的转录 |
| 工作目录已存在 | 保留现有目录，转录结果版本递增 |
