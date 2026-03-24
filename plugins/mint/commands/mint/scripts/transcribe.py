# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "dashscope>=1.20.0",
#     "requests",
#     "oss2",
# ]
# ///
"""百炼平台语音转文本脚本 - Fun-ASR 录音文件识别

用法:
    uv run --script transcribe.py <音频路径或URL> <人名> [说话人数量]

说明:
    - 本地文件自动上传到阿里云 OSS（签名 URL），转录后自动清理
    - 支持格式: mp3/m4a/wav/flac/ogg/opus/wma/aac/mp4/avi/mkv/mov
    - 输出: 同目录下 {人名}_原始稿.md
"""

import sys
import os
import time
import json
import logging
import requests
from http import HTTPStatus
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(message)s',
    datefmt='%H:%M:%S',
)
logger = logging.getLogger(__name__)

# OSS 配置（可通过环境变量覆盖）
OSS_BUCKET = os.getenv('MINT_OSS_BUCKET', 'memoinsight-audio')
OSS_ENDPOINT = os.getenv('MINT_OSS_ENDPOINT', 'https://oss-cn-beijing.aliyuncs.com')
OSS_SIGNED_URL_EXPIRY = 7200  # 签名 URL 有效期：2 小时


def get_dashscope_key() -> str:
    """获取 DashScope API Key

    优先级: DASHSCOPE_API_KEY 环境变量 > Bitwarden CLI
    """
    key = os.getenv('DASHSCOPE_API_KEY')
    if key:
        return key
    # 尝试 Bitwarden CLI（需要已解锁 session）
    try:
        import subprocess
        bw_path = os.path.expanduser('~/AppData/Roaming/npm/bw.cmd')
        if not os.path.exists(bw_path):
            bw_path = 'bw'  # fallback to PATH
        result = subprocess.run(
            [bw_path, 'get', 'password', '阿里bailian (标准 DashScope)'],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    raise RuntimeError(
        '未找到 DASHSCOPE_API_KEY。请设置环境变量: export DASHSCOPE_API_KEY="sk-..."'
    )


def get_oss_credentials() -> tuple[str, str]:
    """获取 OSS AccessKey ID 和 Secret

    优先级: 环境变量 > Bitwarden CLI
    """
    ak = os.getenv('OSS_ACCESS_KEY_ID')
    sk = os.getenv('OSS_ACCESS_KEY_SECRET')
    if ak and sk:
        return ak, sk
    # 尝试 Bitwarden CLI
    try:
        import subprocess
        bw_path = os.path.expanduser('~/AppData/Roaming/npm/bw.cmd')
        if not os.path.exists(bw_path):
            bw_path = 'bw'
        result = subprocess.run(
            [bw_path, 'get', 'item', '阿里云 OSS'],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            import json as _json
            item = _json.loads(result.stdout)
            fields = {f['name']: f['value'] for f in item.get('fields', [])}
            ak = fields.get('AccessKey ID', '')
            sk = fields.get('AccessKey Secret', '')
            if ak and sk:
                return ak, sk
    except Exception:
        pass
    raise RuntimeError(
        '未找到 OSS AccessKey。请设置环境变量:\n'
        '  export OSS_ACCESS_KEY_ID="..."\n'
        '  export OSS_ACCESS_KEY_SECRET="..."'
    )


def upload_to_oss(file_path: str) -> tuple[str, str]:
    """上传本地文件到 OSS，返回 (签名URL, oss_key)

    使用签名 URL 而非公开读，bucket 可保持私有权限。
    """
    import oss2

    ak, sk = get_oss_credentials()
    auth = oss2.Auth(ak, sk)
    bucket = oss2.Bucket(auth, OSS_ENDPOINT, OSS_BUCKET)

    file_name = os.path.basename(file_path)
    file_size_mb = os.path.getsize(file_path) / 1024 / 1024
    oss_key = f'temp/{int(time.time())}_{file_name}'

    logger.info(f'上传到 OSS: {file_name} ({file_size_mb:.1f}MB)')
    bucket.put_object_from_file(oss_key, file_path)

    signed_url = bucket.sign_url('GET', oss_key, OSS_SIGNED_URL_EXPIRY)
    logger.info('上传完成，已生成签名 URL')

    return signed_url, oss_key


def cleanup_oss(oss_key: str) -> None:
    """删除 OSS 上的临时文件"""
    import oss2

    try:
        ak, sk = get_oss_credentials()
        auth = oss2.Auth(ak, sk)
        bucket = oss2.Bucket(auth, OSS_ENDPOINT, OSS_BUCKET)
        bucket.delete_object(oss_key)
        logger.info(f'OSS 临时文件已清理: {oss_key}')
    except Exception as e:
        logger.warning(f'OSS 清理失败（不影响结果）: {e}')


def get_file_url(file_path: str) -> tuple[str, str | None]:
    """将输入转为可访问的 URL，返回 (url, oss_key_or_None)"""
    if file_path.startswith(('http://', 'https://')):
        return file_path, None

    abs_path = os.path.abspath(file_path)
    if not os.path.exists(abs_path):
        raise FileNotFoundError(f'文件不存在: {abs_path}')

    url, oss_key = upload_to_oss(abs_path)
    return url, oss_key


def submit_transcription(file_url: str, api_key: str, speaker_count: int | None = None) -> str:
    """提交异步转录任务，返回 task_id"""
    import dashscope
    from dashscope.audio.asr import Transcription

    dashscope.base_http_api_url = 'https://dashscope.aliyuncs.com/api/v1'
    dashscope.api_key = api_key

    kwargs: dict = {
        'model': 'fun-asr',
        'file_urls': [file_url],
        'diarization_enabled': True,
        'language_hints': ['zh', 'en'],
    }
    if speaker_count and speaker_count >= 2:
        kwargs['speaker_count'] = speaker_count

    logger.info('提交转录任务...')
    resp = Transcription.async_call(**kwargs)

    if resp.status_code != HTTPStatus.OK:
        raise RuntimeError(f'任务提交失败: {resp.code} - {resp.message}')

    task_id = resp.output.task_id
    logger.info(f'任务ID: {task_id}')
    return task_id


def wait_for_result(task_id: str, timeout: int = 1800):
    """轮询等待转录完成"""
    from dashscope.audio.asr import Transcription

    start = time.time()
    while True:
        elapsed = int(time.time() - start)
        if elapsed > timeout:
            raise TimeoutError(
                f'转录超时（{timeout}s）。任务ID: {task_id}'
            )

        result = Transcription.fetch(task=task_id)
        status = result.output.task_status

        if status == 'SUCCEEDED':
            logger.info(f'转录完成！耗时 {elapsed} 秒')
            return result
        elif status == 'FAILED':
            raise RuntimeError(f'转录失败: {json.dumps(result.output, ensure_ascii=False, default=str)}')

        logger.info(f'  状态: {status} ... ({elapsed}s)')
        time.sleep(5)


def parse_transcription(result) -> list[tuple[int, int, str]]:
    """解析转录结果，返回 [(begin_time_ms, speaker_id, text), ...]"""
    segments = []

    for file_result in result.output.results:
        if file_result.get('subtask_status') != 'SUCCEEDED':
            logger.warning(f'子任务未成功: {file_result.get("subtask_status")}')
            continue

        url = file_result.get('transcription_url')
        if not url:
            continue

        logger.info('下载转录结果...')
        resp = requests.get(url, timeout=60)
        resp.raise_for_status()
        data = resp.json()

        for transcript in data.get('transcripts', []):
            for sentence in transcript.get('sentences', []):
                text = sentence.get('text', '').strip()
                if not text:
                    continue

                speaker_id = sentence.get('speaker_id', 0)
                words = sentence.get('words', [])
                begin_time = int(words[0]['begin_time']) if words else sentence.get('begin_time', 0)

                segments.append((begin_time, speaker_id, text))

    return segments


def merge_speaker_turns(segments: list[tuple[int, int, str]]) -> list[tuple[int, int, str]]:
    """合并同一说话人的连续发言"""
    if not segments:
        return []

    merged = []
    cur_time, cur_spk, cur_texts = segments[0][0], segments[0][1], [segments[0][2]]

    for begin_time, speaker_id, text in segments[1:]:
        if speaker_id == cur_spk:
            cur_texts.append(text)
        else:
            merged.append((cur_time, cur_spk, ''.join(cur_texts)))
            cur_time, cur_spk, cur_texts = begin_time, speaker_id, [text]

    merged.append((cur_time, cur_spk, ''.join(cur_texts)))
    return merged


def format_timestamp(ms: int) -> str:
    """毫秒转 HH:MM:SS"""
    total_seconds = ms / 1000
    h = int(total_seconds // 3600)
    m = int((total_seconds % 3600) // 60)
    s = int(total_seconds % 60)
    return f'{h:02d}:{m:02d}:{s:02d}'


def format_markdown(turns: list[tuple[int, int, str]]) -> str:
    """格式化为带时间戳和说话人标记的 markdown"""
    lines = []
    for begin_time, speaker_id, text in turns:
        ts = format_timestamp(begin_time)
        speaker = f'Speaker {speaker_id + 1}'
        lines.append(f'{ts} {speaker}\n\n{text}\n')
    return '\n'.join(lines)


def main():
    if len(sys.argv) < 3:
        print('用法: uv run --script transcribe.py <音频路径或URL> <人名> [说话人数量]')
        print('示例: uv run --script transcribe.py D:/录音/interview.mp3 李玉蕾')
        print('      uv run --script transcribe.py D:/录音/meeting.m4a 张三 3')
        sys.exit(1)

    audio_input = sys.argv[1]
    person_name = sys.argv[2]
    speaker_count = int(sys.argv[3]) if len(sys.argv) > 3 else None

    api_key = get_dashscope_key()
    logger.info(f'API Key: {api_key[:6]}...****')

    # 上传并获取 URL
    file_url, oss_key = get_file_url(audio_input)

    try:
        # 转录
        task_id = submit_transcription(file_url, api_key, speaker_count)
        result = wait_for_result(task_id)

        # 解析
        segments = parse_transcription(result)
        if not segments:
            logger.error('未识别到任何内容，请检查音频文件。')
            sys.exit(1)

        turns = merge_speaker_turns(segments)
        markdown = format_markdown(turns)

        # 输出
        if audio_input.startswith(('http://', 'https://')):
            output_dir = os.getcwd()
        else:
            output_dir = os.path.dirname(os.path.abspath(audio_input))

        output_path = os.path.join(output_dir, f'{person_name}_原始稿.md')
        Path(output_path).write_text(markdown, encoding='utf-8')

        # 统计
        total_chars = sum(len(t) for _, _, t in turns)
        unique_speakers = len(set(s for _, s, _ in turns))
        max_time_ms = max(t for t, _, _ in turns) if turns else 0
        duration_min = max_time_ms / 1000 / 60

        print(f'\n{"="*50}')
        print(f'转录完成！')
        print(f'  输出文件: {output_path}')
        print(f'  总字数:   {total_chars:,}')
        print(f'  说话人:   {unique_speakers} 人')
        print(f'  音频时长: {duration_min:.1f} 分钟')
        print(f'  发言段数: {len(turns)}')
        print(f'{"="*50}')

    finally:
        # 无论成功失败，都清理 OSS 临时文件
        if oss_key:
            cleanup_oss(oss_key)


if __name__ == '__main__':
    main()
