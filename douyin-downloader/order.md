# douyin-downloader 使用顺序

## 快手自动随机发布

先进入目录并激活环境：

```powershell
conda activate playwright
cd D:\github\wechat_republish_playwright\douyin-downloader
```

快手自动随机发布命令：

```powershell
python -m tools.ks_auto_publisher -c config.yml --min-hours 3 --max-hours 4
```

说明：
- 会从未发布的视频素材里随机抽 1 条发布到快手
- 每次发布成功后，下一次会在 `3~4` 小时之间随机等待
- 已发布过的视频会自动跳过

下面按实际操作流程整理：先登录抖音，下载作品，再提取文案，最后发布到小红书或快手。

## 1. 激活环境

```powershell
conda activate playwright
cd D:\github\wechat_republish_playwright\douyin-downloader
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
cd D:\github\wechat_republish_playwright\xiaohongshu-mcp-bin
.\xiaohongshu-login-windows-amd64.exe
```

### 4.2 启动 MCP / HTTP 服务

这个窗口也要保持运行，不要关闭。

```powershell
cd D:\github\wechat_republish_playwright\xiaohongshu-mcp-bin
.\xiaohongshu-mcp-windows-amd64.exe -headless=false
```

## 5. 发布到小红书

### 5.1 先列出可发作品

```powershell
python -m tools.xhs_publish -c config.yml --list
```

输出里会显示：
- `published=yes/no`
- 对应草稿文件路径

### 5.2 随机发一条未发布作品

```powershell
python -m tools.xhs_publish -c config.yml --random --publish
```

说明：
- 默认只会从“未发布”的作品里随机抽 1 条
- 已经发过的作品会自动跳过

### 5.3 指定某条作品发布

```powershell
python -m tools.xhs_publish -c config.yml --aweme-id 7436012128940625178 --publish
```

### 5.4 允许重发已发布作品

```powershell
python -m tools.xhs_publish -c config.yml --aweme-id 7436012128940625178 --publish --include-published
```

### 5.5 只生成草稿，不真正发布

```powershell
python -m tools.xhs_publish -c config.yml --aweme-id 7436012128940625178
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
- `*.ks_draft.json`
  - 快手发布草稿
- `*.ks_publish_state.json`
  - 快手发布状态标记
  - `published=true` 表示已经发过，默认不会重复发

## 7. 发布到快手

### 7.1 先登录快手并保存登录态

首次使用先执行：

```powershell
python -m tools.ks_login
```

默认会把快手登录态保存到：

```text
..\matrix\ks_uploader\account\default_account.json
```

### 7.2 列出可发视频

```powershell
python -m tools.ks_publish -c config.yml --list
```

### 7.3 随机发一条未发布视频到快手

```powershell
python -m tools.ks_publish -c config.yml --random --publish
```

### 7.4 指定某条视频发布到快手

```powershell
python -m tools.ks_publish -c config.yml --aweme-id 7610252027532879091 --publish
```

### 7.5 允许重发已发布视频

```powershell
python -m tools.ks_publish -c config.yml --aweme-id 7610252027532879091 --publish --include-published
```

### 7.6 自动循环随机发布

```powershell
python -m tools.ks_auto_publisher -c config.yml
```

## 8. 推荐执行顺序

1. `conda activate playwright`
2. `python -m tools.cookie_fetcher --config config.yml`
3. `python run.py -c config.yml`
4. `python -m tools.text_extractor -c config.yml`
5. 启动 `xiaohongshu-login-windows-amd64.exe`
6. 启动 `xiaohongshu-mcp-windows-amd64.exe -headless=false`
7. `python -m tools.xhs_publish -c config.yml --list`
8. `python -m tools.xhs_publish -c config.yml --random --publish`
9. `python -m tools.ks_login`
10. `python -m tools.ks_publish -c config.yml --list`
11. `python -m tools.ks_publish -c config.yml --random --publish`

