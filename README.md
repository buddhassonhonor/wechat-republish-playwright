本项目的虚拟环境 conda activate playwright
# WeChat Republish Playwright

基于 Playwright 的自动化脚本，用于将公开的微信公众号文章一键转载/重新发布到你自己的微信公众平台草稿箱。相比于传统的 Selenium 方案，Playwright 对现代 Web 界面的处理更为流畅，能更好地应对页面元素的加载和变化。

## ✨ 功能特点

1. **自动抓取解析**: 使用 `requests` 和 `BeautifulSoup` 获取目标微信文章的标题和 HTML 正文内容。
2. **自动化浏览器操作**: 使用 Playwright 自动打开浏览器并驱动前端操作。
3. **扫码登录支持**: 脚本会自动导航至微信公众平台首页，并提供充足的时间等待用户进行微信扫码登录。
4. **一键存为草稿**: 登录成功后，脚本会自动跳转素材管理、点击“新建图文”、填入抓取到的标题、向编辑器 iframe 中注入 HTML 正文，最后自动点击保存为图文草稿。

## 🛠️ 环境要求

* Python 3.8 或更高版本

## 📦 安装说明

1. 克隆或下载本项目到本地目录下：
   ```bash
   git clone <你的仓库地址>
   cd wechat_republish_playwright
   ```

2. 安装必要的 Python 依赖包：
   ```bash
   pip install beautifulsoup4 requests playwright
   ```

3. 安装 Playwright 所需的浏览器二进制文件（由于微信后台兼容性等原因，推荐使用 Chromium）：
   ```bash
   playwright install
   ```

## 🚀 使用方法

基本的运行方式非常简单，只需通过命令行提供你需要抓取的微信公众号文章链接（URL）即可：

```bash
python wechat_republish_playwright.py --url <微信文章_URL>
```

程序运行后，会自动弹出一个可见的浏览器窗口并打开微信公众平台登录页。请**使用绑定了公众号管理员或运营者的微信扫码登录**。

**登录态保持 (Session Persistence)**：
脚本现在会自动在本地创建一个 `wechat_session` 文件夹来保存你的登录状态。这意味着：
- **只需扫码一次**：只要你不手动删除该文件夹或在网页上退出登录，下次运行脚本时将直接进入后台，无需再次扫码。
- **自动化更彻底**：方便进行批量处理或多次测试。

扫码（或自动登录）完成后，你可以将双手离开键盘和鼠标，脚本会自动完成新建图文和保存的操作，并在结束后保留浏览器窗口供你审定。

### 高级选项配置

- **指定本地浏览器路径**：如果你希望使用本机自带的 Google Chrome，或者特定的 Chromium 发行版，可使用 `--browser-path` 指定其可执行文件路径：
  ```bash
  python wechat_republish_playwright.py --url <微信文章_URL> --browser-path "C:\Program Files\Google\Chrome\Application\chrome.exe"
  ```
  *(注：根据你的操作系统，路径可能不同，Mac 下例如 `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`)*

- **自定义扫码登录等待时间**：默认脚本会等待 120 秒供你扫码。如果需要更长的准备时间，可通过 `--login-timeout` 修改（单位：秒）：
  ```bash
  python wechat_republish_playwright.py --url <微信文章_URL> --login-timeout 180
  ```

## ⚠️ 注意事项及局限性

1. **需要人工校验**：为了安全和排版确认，本脚本**仅会将文章保存为草稿**，绝不会主动群发或发表。请在公众号后台自行预览排版后再做发布。
2. **图片防盗链与拉取**：脚本直接注入了原文的 HTML 及图片外链。正常情况下，微信编辑器发现外部图片外链时会自动触发图片抓取上传机制。但部分特殊图片也可能拉取失败，请务必在生成草稿后检查图片是否正常渲染。
3. **平台 UI 变更风险**：该自动化脚本依赖于微信公众平台当前前端的 DOM 结构（如寻找“新建图文”按钮、等待 iframe 出现等）。如果某天微信官方大幅修改了后台界面，该脚本可能会找不到对应的按钮而报错。你需要根据报错信息更新对应选择器的代码。
