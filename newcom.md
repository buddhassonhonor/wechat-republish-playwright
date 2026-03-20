# 新电脑部署说明

如果你把整个 `wechat_republish_playwright` 文件夹复制到一台新电脑，按下面步骤配置后，就可以继续使用抖音下载、文案提取、小红书发布这套流程。

## 1. 先准备系统环境

你需要先在新电脑上安装这些基础软件：

- `Miniconda` 或 `Anaconda`
- `Git`，如果你后面还想继续更新仓库
- `Microsoft Visual C++ Redistributable`，很多 Windows 本地工具会用到
- 浏览器，建议保留 `Chromium` 相关组件由 `playwright` 自动安装

如果你要用 `xiaohongshu-mcp` 的 Windows 可执行文件，还要注意：

- Windows Defender 可能误报 `leakless.exe` 或登录程序
- 如果出现拦截，给 `xiaohongshu-mcp-bin` 和它运行时生成的临时目录加排除项

## 2. 复制项目目录

建议完整复制到类似下面的路径：

```powershell
D:\github\wechat_republish_playwright
```

目录里你会用到的主要部分：

- `douyin-downloader`
- `xiaohongshu-mcp`
- `xiaohongshu-mcp-bin`
- `order.md`
- `newcom.md`

## 3. 创建或激活 conda 环境

如果新电脑上还没有 `playwright` 环境，就新建一个。

### 3.1 新建环境

```powershell
conda create -n playwright python=3.10 -y
conda activate playwright
```

### 3.2 已有环境就直接激活

```powershell
conda activate playwright
```

## 4. 安装 Python 依赖

进入抖音项目目录：

```powershell
cd D:\github\wechat_republish_playwright\douyin-downloader
```

安装依赖：

```powershell
python -m pip install -r requirements.txt
```

如果你想用国内源，可以这样装：

```powershell
python -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

## 5. 安装 Playwright 浏览器

项目依赖 Playwright 的 Chromium。

```powershell
python -m pip install playwright
python -m playwright install chromium
```

如果新电脑上以后还要跑小红书自动化，也建议保留这个浏览器环境。

## 6. 安装本地语音识别模型依赖

当前项目的文案提取支持 `faster-whisper` 本地后端。

如果依赖没装上，可以再补一次：

```powershell
python -m pip install faster-whisper
```

第一次做音频转写时会自动下载模型，默认会优先走本地 GPU。

## 7. 抖音相关功能怎么跑

### 7.1 扫码登录抖音

```powershell
cd D:\github\wechat_republish_playwright\douyin-downloader
python -m tools.cookie_fetcher --config config.yml
```

作用：

- 打开浏览器
- 扫码登录抖音
- 保存 Cookie 到配置文件

### 7.2 下载抖音喜欢列表

```powershell
python run.py -c config.yml
```

如果你要下载自己的喜欢列表，配置里一般要有：

```yaml
link:
  - https://www.douyin.com/user/self?showTab=like
mode:
  - like
rate_limit: 0.5
thread: 2
```

## 8. 已下载作品的文案提取

```powershell
python -m tools.text_extractor -c config.yml
```

如果只想重跑某一条：

```powershell
python -m tools.text_extractor -c config.yml --force --aweme-id 7436012128940625178
```

它会优先：

- 音频转文本
- 再 OCR 图片
- 再提取字幕

## 9. 小红书发布相关功能怎么跑

### 9.1 启动登录程序

先扫码登录小红书账号：

```powershell
cd D:\github\wechat_republish_playwright\xiaohongshu-mcp-bin
.\xiaohongshu-login-windows-amd64.exe
```

### 9.2 启动 MCP 服务

这个窗口要一直开着：

```powershell
cd D:\github\wechat_republish_playwright\xiaohongshu-mcp-bin
.\xiaohongshu-mcp-windows-amd64.exe -headless=false
```

### 9.3 查看哪些作品可发

```powershell
cd D:\github\wechat_republish_playwright\douyin-downloader
python -m tools.xhs_publish -c config.yml --list
```

### 9.4 随机发一条未发布作品

```powershell
python -m tools.xhs_publish -c config.yml --random --publish
```

### 9.5 指定某条作品发布

```powershell
python -m tools.xhs_publish -c config.yml --aweme-id 7436012128940625178 --publish
```

### 9.6 允许重发已发布作品

```powershell
python -m tools.xhs_publish -c config.yml --aweme-id 7436012128940625178 --publish --include-published
```

## 10. 新电脑首次使用的推荐顺序

1. 安装 `Miniconda`
2. 复制整个项目目录
3. `conda create -n playwright python=3.10 -y`
4. `conda activate playwright`
5. `pip install -r requirements.txt`
6. `python -m playwright install chromium`
7. `python -m tools.cookie_fetcher --config config.yml`
8. `python run.py -c config.yml`
9. `python -m tools.text_extractor -c config.yml`
10. 启动 `xiaohongshu-login-windows-amd64.exe`
11. 启动 `xiaohongshu-mcp-windows-amd64.exe -headless=false`
12. `python -m tools.xhs_publish -c config.yml --list`
13. `python -m tools.xhs_publish -c config.yml --random --publish`

## 11. 常见问题

### 11.1 `conda activate playwright` 报错

说明这个环境还没创建，先执行：

```powershell
conda create -n playwright python=3.10 -y
```

### 11.2 `playwright` 没有浏览器

执行：

```powershell
python -m playwright install chromium
```

### 11.3 文案提取只得到很短结果

优先确认：

- 这条作品是否真有音频
- `faster-whisper` 是否已安装
- 是否已经生成过旧的 transcript 文件

必要时重跑：

```powershell
python -m tools.text_extractor -c config.yml --force --aweme-id 7436012128940625178
```

### 11.4 小红书登录程序被 Defender 拦截

通常是 Windows 的误报。可以先只给最小范围加排除项：

- `D:\github\wechat_republish_playwright\xiaohongshu-mcp-bin`
- 运行时解压出的 `leakless-amd64-...` 临时目录
