# 利用fastapi实现部署文件服务器

from fastapi import FastAPI, File, UploadFile, Response, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import re
from pathlib import Path
import shutil
import os
from mimetypes import guess_type
import stat
from urllib.parse import quote
from starlette.responses import StreamingResponse
from email.utils import formatdate

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def file_iterator(file_path, offset, chunk_size):
    """
    文件生成器
    :param file_path: 文件绝对路径
    :param offset: 文件读取的起始位置
    :param chunk_size: 文件读取的块大小
    :return: yield
    """
    with open(file_path, 'rb') as f:
        f.seek(offset, os.SEEK_SET)
        while True:
            data = f.read(chunk_size)
            if data:
                yield data
            else:
                break

# 上传文件

@app.post("/upload")
async def upload(file: UploadFile = File()):
    with open('static/'+file.filename, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    return {"filename": file.filename}

@app.get("/hello")
async def hello():
    return {"hello": "world"}
 
@app.get("/download/{file_name}")
async def download_file(request: Request, file_name: str):
    """分片下载文件，支持断点续传"""
    # 检查文件是否存在
    file_path = 'static/'+file_name
    # 获取文件的信息
    stat_result = os.stat(file_path)
    content_type, encoding = guess_type(file_path)
    content_type = content_type or 'application/octet-stream'
    # 读取文件的起始位置和终止位置
    range_str = request.headers.get('range', '')
    range_match = re.search(r'bytes=(\d+)-(\d+)', range_str, re.S) or re.search(r'bytes=(\d+)-', range_str, re.S)
    if range_match:
        start_bytes = int(range_match.group(1))
        end_bytes = int(range_match.group(2)) if range_match.lastindex == 2 else stat_result.st_size - 1
    else:
        start_bytes = 0
        end_bytes = stat_result.st_size - 1
    # 这里 content_length 表示剩余待传输的文件字节长度
    content_length = stat_result.st_size - start_bytes if stat.S_ISREG(stat_result.st_mode) else stat_result.st_size
    # 构建文件名称
    name, *suffix = file_name.rsplit('.', 1)
    suffix = f'.{suffix[0]}' if suffix else ''
    filename = quote(f'{name}{suffix}')  # 文件名编码，防止中文名报错
    # 打开文件从起始位置开始分片读取文件
    return StreamingResponse(
        file_iterator(file_path, start_bytes, 1024 * 1024 * 1),  # 每次读取 1M
        media_type=content_type,
        headers={
            'content-disposition': f'attachment; filename="{filename}"',
            'accept-ranges': 'bytes',
            'connection': 'keep-alive',
            'content-length': str(content_length),
            'content-range': f'bytes {start_bytes}-{end_bytes}/{stat_result.st_size}',
            'last-modified': formatdate(stat_result.st_mtime, usegmt=True),
        },
        status_code=206 if start_bytes > 0 else 200
    )

# uvicorn serve:app --reload
if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=8111)