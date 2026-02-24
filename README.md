# LanGallery Lite

局域网极简图片浏览器。  
后端使用 `FastAPI`，前端使用 `Vite + Vue 3 + TypeScript`。

## 功能范围

- 读取电脑指定目录下的图片文件
- 支持递归读取子目录
- 手机在同一局域网访问并浏览
- 网格浏览 + 点击查看大图
- 不生成缩略图，不包含上传/删除/鉴权等额外功能

## 后端启动

1. 创建并激活虚拟环境（PowerShell）

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

2. 启动服务（示例）

```powershell
python -m backend.app.main --gallery-dir "D:\Photos" --host 0.0.0.0 --port 8000
```

可选参数：

- `--recursive / --no-recursive`：是否递归扫描子目录（默认递归）
- `--extensions`：图片扩展名白名单，逗号分隔
- `--frontend-dist`：前端构建目录，默认 `frontend/dist`

## 前端开发模式

```powershell
cd frontend
npm install
npm run dev
```

开发模式下前端默认运行在 `5173` 端口，并代理 `/api` 到 `8000`。

## 生产模式（单端口）

1. 构建前端

```powershell
cd frontend
npm run build
cd ..
```

2. 启动后端（同上）

```powershell
python -m backend.app.main --gallery-dir "D:\Photos" --host 0.0.0.0 --port 8000
```

此时访问 `http://<电脑局域网IP>:8000` 即可打开页面。

## 测试

```powershell
pytest backend/tests
```
