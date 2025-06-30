import os
import time
from playwright.sync_api import sync_playwright, Cookie, TimeoutError as PlaywrightTimeoutError

def add_server_time(server_url="https://gpanel.eternalzero.cloud/server/7fce84a0"):
    """
    尝试登录 gpanel.eternalzero.cloud 并点击 "ADD 4H" 按钮。
    优先使用 REMEMBER_WEB_COOKIE 进行会话登录，如果不存在则回退到邮箱密码登录。
    此函数设计为每次GitHub Actions运行时执行一次。
    """
    # 获取环境变量
    remember_web_cookie = os.environ.get('REMEMBER_WEB_COOKIE')
    pterodactyl_email = os.environ.get('PTERODACTYL_EMAIL')
    pterodactyl_password = os.environ.get('PTERODACTYL_PASSWORD')

    # 检查是否提供了任何登录凭据
    if not (remember_web_cookie or (pterodactyl_email and pterodactyl_password)):
        print("错误: 缺少登录凭据。请设置 REMEMBER_WEB_COOKIE 或 PTERODACTYL_EMAIL 和 PTERODACTYL_PASSWORD 环境变量。")
        return False

    with sync_playwright() as p:
        # 在 GitHub Actions 中，通常使用 headless 模式
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        # 增加默认超时时间，给网络波动和慢加载留出更多空间
        page.set_default_timeout(90000) # 将默认超时从30秒增加到90秒

        try:
            # --- 尝试通过 REMEMBER_WEB_COOKIE 会话登录 ---
            if remember_web_cookie:
                print("尝试使用 REMEMBER_WEB_COOKIE 会话登录...")
                session_cookie = {
                    'name': 'remember_web_59ba36addc2b2f9401580f014c7f58ea4e30989d',
                    'value': remember_web_cookie,
                    'domain': '.eternalzero.cloud',
                    'path': '/',
                    'expires': int(time.time()) + 3600 * 24 * 365,
                    'httpOnly': True,
                    'secure': True,
                    'sameSite': 'Lax'
                }
                page.context.add_cookies([session_cookie])
                print(f"已设置 REMEMBER_WEB_COOKIE。正在访问服务器页面: {server_url}")
                
                try:
                    # 【关键修改】将 wait_until 从 'networkidle' 改为 'domcontentloaded'
                    # 这会更快地返回，然后我们可以依赖 wait_for_selector 来确保页面元素加载完毕
                    page.goto(server_url, wait_until="domcontentloaded", timeout=90000)
                except PlaywrightTimeoutError:
                    print(f"页面加载超时（90秒）。页面可能卡住了或加载极慢。")
                    page.screenshot(path="goto_timeout_error.png")
                    # 即使超时，也继续检查URL，看是否被重定向到了登录页
                
                # 检查是否因为cookie无效而被重定向到登录页
                if "login" in page.url or "auth" in page.url:
                    print("使用 REMEMBER_WEB_COOKIE 登录失败或会话无效。将尝试使用邮箱密码登录。")
                    page.context.clear_cookies()
                    remember_web_cookie = None # 标记cookie登录失败
                else:
                    print("REMEMBER_WEB_COOKIE 登录似乎成功，当前URL正确。")

            # --- 如果 REMEMBER_WEB_COOKIE 不可用或失败，则回退到邮箱密码登录 ---
            if not remember_web_cookie:
                if not (pterodactyl_email and pterodactyl_password):
                    print("错误: REMEMBER_WEB_COOKIE 无效，且未提供 PTERODACTYL_EMAIL 或 PTERODACTYL_PASSWORD。无法登录。")
                    browser.close()
                    return False

                login_url = "https://gpanel.eternalzero.cloud/auth/login"
                print(f"正在访问登录页: {login_url}")
                page.goto(login_url, wait_until="domcontentloaded", timeout=90000)

                email_selector = 'input[name="email"]'
                password_selector = 'input[name="password"]'
                login_button_selector = 'button[type="submit"]'

                print("正在等待登录元素加载...")
                page.wait_for_selector(email_selector)
                page.wait_for_selector(password_selector)
                page.wait_for_selector(login_button_selector)

                print("正在填充邮箱和密码...")
                page.fill(email_selector, pterodactyl_email)
                page.fill(password_selector, pterodactyl_password)

                print("正在点击登录按钮...")
                # 点击后等待导航完成
                with page.expect_navigation(wait_until="domcontentloaded", timeout=60000):
                    page.click(login_button_selector)

                # 检查登录后的URL
                if "login" in page.url or "auth" in page.url:
                    error_message_selector = '.alert.alert-danger, .error-message, .form-error'
                    error_element = page.query_selector(error_message_selector)
                    error_text = error_element.inner_text().strip() if error_element else "未知错误，URL仍在登录页。"
                    print(f"邮箱密码登录失败: {error_text}")
                    page.screenshot(path="login_fail_error.png")
                    browser.close()
                    return False
                else:
                    print("邮箱密码登录成功。")

            # --- 确保当前页面是目标服务器页面 ---
            print(f"当前页面URL: {page.url}")
            if page.url != server_url:
                print(f"当前不在目标服务器页面，导航到: {server_url}")
                page.goto(server_url, wait_until="domcontentloaded", timeout=90000)
                if "login" in page.url:
                    print("导航到服务器页面失败，会话可能已过期，需要重新登录。")
                    page.screenshot(path="server_page_nav_fail.png")
                    browser.close()
                    return False

            # --- 查找并点击 "ADD 4H" 按钮 ---
            add_button_selector = 'button:has-text("ADD 4H")'
            print(f"正在查找并等待 'ADD 4H' 按钮: {add_button_selector}")

            try:
                # 等待按钮变为可见状态
                add_button = page.locator(add_button_selector)
                add_button.wait_for(state='visible', timeout=30000)
                add_button.click()
                print("成功点击 'ADD 4H' 按钮。")
                time.sleep(5) # 等待一下，让操作生效
                print("等待 5 秒后完成。")
                browser.close()
                return True
            except PlaywrightTimeoutError:
                print(f"在30秒内未找到或 'ADD 4H' 按钮不可见。")
                page.screenshot(path="add_4h_button_not_found.png")
                browser.close()
                return False

        except Exception as e:
            print(f"执行过程中发生未知错误: {e}")
            page.screenshot(path="general_error.png")
            browser.close()
            return False

if __name__ == "__main__":
    print("开始执行添加服务器时间任务...")
    # 直接调用 add_server_time，不进行内部调度
    success = add_server_time()
    if success:
        print("任务执行成功。")
        exit(0)
    else:
        print("任务执行失败。")
        exit(1)
