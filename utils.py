from astrbot.api.all import *
import aiofiles
import aiohttp
import asyncio
from pathlib import Path
from astrbot.api import logger
from astrbot.api.star import StarTools

async def download_image(image_url: str) -> str | None:
    temp_dir : Path = StarTools.get_data_dir('llss_sub') / "temp"
    # if not temp_dir.exists():
    #     temp_dir.mkdir(parents=True, exist_ok=True)
    try:
        file_name = image_url.split("/")[-1]
        file_path = temp_dir / file_name
        if file_path.exists():
            return str(file_path)
        if await _download_image_with_retry(image_url, file_path):
            return str(file_path)
        else:
            return None
    except Exception as e:
        logger.error(f"下载处理图片失败：{e}")
        return None
    
async def _download_image_with_retry(
    url: str,
    save_path: Path,
    max_retries: int = 3,
    timeout: int = 60
) -> bool:
    """
    异步下载图片并自动重试
    
    Args:
        url: 图片URL
        save_path: 保存路径
        max_retries: 最大重试次数（包括首次尝试）
        timeout: 超时时间（秒）
    
    Returns:
        bool: 下载是否成功
    """
    # 确保保存目录存在
    save_dir = save_path.parent
    save_dir.mkdir(parents=True, exist_ok=True)
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    async with aiohttp.ClientSession(headers=headers) as session:
        for attempt in range(max_retries):
            try:
                logger.info(f"尝试下载图片 (尝试 {attempt + 1}/{max_retries}): {url}")
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as response:
                    # 检查HTTP状态码
                    if response.status != 200:
                        logger.warning(f"HTTP错误 {response.status}，尝试 {attempt + 1}/{max_retries}")
                        continue
                    
                    # 获取内容长度
                    content_length = response.headers.get('Content-Length')
                    
                    # 读取并保存文件
                    content = await response.read()
                    
                    # 校验下载的数据
                    if not content:
                        logger.warning(f"下载内容为空，尝试 {attempt + 1}/{max_retries}")
                        continue
                    
                    # 检查文件大小
                    if len(content) < 100:  # 假设图片至少100字节
                        logger.warning(f"文件大小过小 ({len(content)} bytes)，可能不是有效的图片")
                        continue
                    
                    # 异步写入文件
                    async with aiofiles.open(save_path, 'wb') as f:
                        await f.write(content)
                    
                    logger.info(f"图片下载成功: {save_path} ({len(content)} bytes)")
                    return True
                    # 额外校验：尝试打开文件确认是有效图片
                    # try:
                    #     await verify_image(save_path)
                    #     logger.info(f"图片校验成功: {save_path}")
                    #     return True
                    # except Exception as e:
                    #     logger.warning(f"图片校验失败: {e}")
                    #     continue
                        
            except asyncio.TimeoutError:
                logger.warning(f"请求超时，尝试 {attempt + 1}/{max_retries}")
                
            except aiohttp.ClientError as e:
                logger.warning(f"网络错误: {e}，尝试 {attempt + 1}/{max_retries}")
                
            except Exception as e:
                logger.warning(f"未知错误: {e}，尝试 {attempt + 1}/{max_retries}")
            
            # 如果不是最后一次尝试，等待一段时间后重试
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # 指数退避
                logger.info(f"等待 {wait_time} 秒后重试...")
                await asyncio.sleep(wait_time)
    
    logger.error(f"图片下载失败，已尝试 {max_retries} 次: {url}")
    return False

async def _image_obfus(img_data):
    """破坏图片哈希"""
    from PIL import Image as ImageP
    from io import BytesIO
    import random

    try:
        with BytesIO(img_data) as input_buffer:
            with ImageP.open(input_buffer) as img:
                if img.mode != "RGB":
                    img = img.convert("RGB")

                width, height = img.size
                pixels = img.load()

                points = []
                for _ in range(3):
                    while True:
                        x = random.randint(0, width - 1)
                        y = random.randint(0, height - 1)
                        if (x, y) not in points:
                            points.append((x, y))
                            break

                for x, y in points:
                    r, g, b = pixels[x, y]

                    r_change = random.choice([-1, 1])
                    g_change = random.choice([-1, 1])
                    b_change = random.choice([-1, 1])

                    new_r = max(0, min(255, r + r_change))
                    new_g = max(0, min(255, g + g_change))
                    new_b = max(0, min(255, b + b_change))

                    pixels[x, y] = (new_r, new_g, new_b)

                with BytesIO() as output:
                    img.save(output, format="JPEG", quality=95, subsampling=0)
                    return output.getvalue()

    except Exception as e:
        logger.warning(f"破坏图片哈希时发生错误: {str(e)}")
        return img_data
    