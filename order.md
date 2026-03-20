cd E:\PROJECT\wechat_republish_playwright\xiaohongshu-mcp-bin
.\xiaohongshu-mcp-windows-amd64.exe -headless=true -port ":18061"
上一条启动后台MCP ，下面命令是启动发布程序 
cd E:\PROJECT\wechat_republish_playwright\douyin-downloader

..\.venv\Scripts\python.exe -m tools.auto_publisher --min-hours 3 --max-hours 5 --retry-minutes 3 --base-url http://127.0.0.1:18061

成功后随机等待 3~5 小时，失败后 3 分钟重试。

..\.venv\Scripts\python.exe -m tools.auto_publisher --once --base-url http://127.0.0.1:18061



# douyin-downloader 使用顺序

下面按实际操作流程整理：先登录抖音，下载作品，再提取文案，最后发布到小红书。

## 1. 激活环境

```powershell
cd E:\PROJECT\wechat_republish_playwright\douyin-downloader
..\.venv\Scripts\Activate.ps1
```

## 2. 抖音登录与下载

### 2.1 扫码登录并保存 Cookie

```powershell
python -m tools.cookie_fetcher --config config.yml
```

作用：
- 打开浏览器
- 扫码登录你的抖音账号
- 保存登录态到 `config.yml` / `config\cookies.json`

### 2.2 下载抖音喜欢列表

```powershell
python run.py -c config.yml
```

常见配置要点：

```yaml
link:
  - https://www.douyin.com/user/self?showTab=like
mode:
  - like
rate_limit: 0.5
thread: 2
```

补充：
- `rate_limit` 越小越慢，越保守
- `thread` 不要开太高，`2~5` 一般够用

## 3. 已下载作品的文案提取

### 3.1 默认离线提取

```powershell
python -m tools.text_extractor -c config.yml
```

作用：
- 读取 `Downloaded/download_manifest.jsonl`
- 只处理已经下载完成的作品
- 默认跳过已经生成过 `*.transcript.txt` / `*.transcript.json` 的作品

### 3.2 强制重跑某个作品

```powershell
python -m tools.text_extractor -c config.yml --force --aweme-id 7436012128940625178
```

### 3.3 只处理指定作品

```powershell
python -m tools.text_extractor -c config.yml --aweme-id 7436012128940625178
```

## 4. 小红书发布前准备

### 4.1 启动登录程序

这个窗口要保持运行，先完成扫码登录。

```powershell
cd E:\PROJECT\wechat_republish_playwright\xiaohongshu-mcp-bin
.\xiaohongshu-login-windows-amd64.exe
```

### 4.2 启动 MCP / HTTP 服务

这个窗口也要保持运行，不要关闭。

发布时建议无头模式，避免位置授权弹窗阻塞。

```powershell
cd E:\PROJECT\wechat_republish_playwright\xiaohongshu-mcp-bin
.\xiaohongshu-mcp-windows-amd64.exe -headless=true -port ":18061"
```

需要人工扫码或排查问题时再用有头模式：

```powershell
cd E:\PROJECT\wechat_republish_playwright\xiaohongshu-mcp-bin
.\xiaohongshu-mcp-windows-amd64.exe -headless=false -port ":18061"
```

## 5. 发布到小红书

### 5.1 先列出可发作品

```powershell
cd E:\PROJECT\wechat_republish_playwright\douyin-downloader
..\.venv\Scripts\python.exe -m tools.xhs_publish -c config.yml --list
```

输出里会显示：
- `published=yes/no`
- 对应草稿文件路径

### 5.2 随机发一条未发布作品

```powershell
cd E:\PROJECT\wechat_republish_playwright\douyin-downloader
..\.venv\Scripts\python.exe -m tools.xhs_publish -c config.yml --random --publish
```

说明：
- 默认只会从“未发布”的作品里随机抽 1 条
- 已经发过的作品会自动跳过

### 5.2.1 只跑一次（测试用）

```powershell
cd E:\PROJECT\wechat_republish_playwright\douyin-downloader
..\.venv\Scripts\python.exe -m tools.auto_publisher --once
```

### 5.3 指定某条作品发布

```powershell
cd E:\PROJECT\wechat_republish_playwright\douyin-downloader
..\.venv\Scripts\python.exe -m tools.xhs_publish -c config.yml --aweme-id 7436012128940625178 --publish
```

### 5.4 允许重发已发布作品

```powershell
cd E:\PROJECT\wechat_republish_playwright\douyin-downloader
..\.venv\Scripts\python.exe -m tools.xhs_publish -c config.yml --aweme-id 7436012128940625178 --publish --include-published
```

### 5.5 只生成草稿，不真正发布

```powershell
cd E:\PROJECT\wechat_republish_playwright\douyin-downloader
..\.venv\Scripts\python.exe -m tools.xhs_publish -c config.yml --aweme-id 7436012128940625178
```

## 6. 常用文件说明

- `Downloaded/download_manifest.jsonl`
  - 下载清单
  - 记录每个作品的 `aweme_id`、标题、文件路径等
- `*.transcript.txt`
  - 文案提取结果
- `*.transcript.json`
  - 文案提取的结构化结果
- `*.xhs_draft.json`
  - 小红书发布草稿
- `*.xhs_publish_state.json`
  - 发布状态标记
  - `published=true` 表示已经发过，默认不会重复发

## 7. 推荐执行顺序

1. `conda activate playwright`
2. `python -m tools.cookie_fetcher --config config.yml`
3. `python run.py -c config.yml`
4. `python -m tools.text_extractor -c config.yml`
5. 启动 `xiaohongshu-login-windows-amd64.exe`
6. 启动 `xiaohongshu-mcp-windows-amd64.exe -headless=false`
7. `python -m tools.xhs_publish -c config.yml --list`
8. `python -m tools.xhs_publish -c config.yml --random --publish`
