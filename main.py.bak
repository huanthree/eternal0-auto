import os
import time
from playwright.sync_api import sync_playwright, Cookie

def add_server_time(server_url="https://gpanel.eternalzero.cloud/server/5302206f"):
    """
    尝试登录 gpanel.eternalzero.cloud 并点击 "ADD 5H" 按钮。
    优先使用 PTERODACTYL_SESSION 进行会话登录，如果不存在则回退到邮箱密码登录。
    """
    # 获取环境变量
    pterodactyl_session = os.environ.get('PTERODACTYL_SESSION')
    pterodactyl_email = os.environ.get('PTERODACTYL_EMAIL')
    pterodactyl_password = os.environ.get('PTERODACTYL_PASSWORD')

    # 检查是否提供了任何登录凭据
    if not (pterodactyl_session or (pterodactyl_email and pterodactyl_password)):
        print("错误: 缺少登录凭据。请设置 PTERODACTYL_SESSION 或 PTERODACTYL_EMAIL 和 PTERODACTYL_PASSWORD 环境变量。")
        return False

    with sync_playwright() as p:
        # 在 GitHub Actions 中，通常使用 headless 模式
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        try:
            # --- 尝试通过 PTERODACTYL_SESSION 会话登录 ---
            if pterodactyl_session:
                print("尝试使用 PTERODACTYL_SESSION 会话登录...")
                # Pterodactyl 会话 Cookie 通常是 'pterodactyl_session'
                # 域名需要设置为 .eternalzero.cloud 以覆盖所有子域名
                session_cookie = Cookie(
                    name='pterodactyl_session',
                    value=pterodactyl_session,
                    domain='.eternalzero.cloud',
                    path='/',
                    expires=time.time() + 3600 * 24 * 7, # 7天后过期，确保足够长
                    httpOnly=True,
                    secure=True,
                    sameSite='Lax'
                )
                page.context.add_cookies([session_cookie])
                print(f"已设置 PTERODACTYL_SESSION Cookie。正在访问服务器页面: {server_url}")
                page.goto(server_url, wait_until="networkidle")

                # 检查是否成功登录并停留在服务器页面，如果重定向到登录页则会话无效
                # 通过检查URL是否包含登录相关的路径来判断
                if "login" in page.url or "auth" in page.url:
                    print("使用 PTERODACTYL_SESSION 登录失败或会话无效。将尝试使用邮箱密码登录。")
                    # 清除可能无效的cookie，以便进行新的登录尝试
                    page.context.clear_cookies()
                    pterodactyl_session = None # 标记为失效，强制回退到密码登录
                else:
                    print("PTERODACTYL_SESSION 登录成功。")
                    # 如果登录后不在目标服务器页面，则导航过去
                    if page.url != server_url:
                         print(f"当前URL不是预期服务器页面 ({page.url})，导航到: {server_url}")
                         page.goto(server_url, wait_until="networkidle")

            # --- 如果 PTERODACTYL_SESSION 不可用或失败，则回退到邮箱密码登录 ---
            if not pterodactyl_session:
                if not (pterodactyl_email and pterodactyl_password):
                    print("错误: PTERODACTYL_SESSION 无效，且未提供 PTERODACTYL_EMAIL 或 PTERODACTYL_PASSWORD。无法登录。")
                    return False

                login_url = "https://gpanel.eternalzero.cloud/auth/login"
                print(f"正在访问登录页: {login_url}")
                page.goto(login_url, wait_until="networkidle")

                # 登录表单元素选择器，根据Pterodactyl面板常见结构设定
                email_selector = 'input[name="email"]'
                password_selector = 'input[name="password"]'
                login_button_selector = 'button[type="submit"]' # 通常是提交按钮

                print("正在等待登录元素加载...")
                page.wait_for_selector(email_selector, timeout=30000)
                page.wait_for_selector(password_selector, timeout=30000)
                page.wait_for_selector(login_button_selector, timeout=30000)

                print("正在填充邮箱和密码...")
                page.fill(email_selector, pterodactyl_email)
                page.fill(password_selector, pterodactyl_password)

                print("正在点击登录按钮...")
                page.click(login_button_selector)

                # 等待登录成功后的页面跳转
                try:
                    # 等待URL变为服务器URL，或者等待一个指示登录成功的元素
                    # 假设登录成功后会重定向到服务器管理页面或其他仪表板页面
                    page.wait_for_url(server_url, timeout=30000)
                    print("邮箱密码登录成功，已跳转到服务器页面。")
                except Exception:
                    # 如果没有直接跳转到服务器页面，检查是否有错误消息
                    error_message_selector = '.alert.alert-danger, .error-message, .form-error'
                    error_element = page.query_selector(error_message_selector)
                    if error_element:
                        error_text = error_element.inner_text().strip()
                        print(f"邮箱密码登录失败: {error_text}")
                        page.screenshot(path="login_fail_error_message.png")
                    else:
                        print("邮箱密码登录失败: 未能跳转到预期页面或检测到错误信息。")
                        page.screenshot(path="login_fail_no_error.png")
                    return False

            # --- 确保当前页面是目标服务器页面 ---
            print(f"当前页面URL: {page.url}")
            if page.url != server_url:
                print(f"当前不在目标服务器页面，导航到: {server_url}")
                page.goto(server_url, wait_until="networkidle")
                # 再次检查是否到达，或者是否被重定向回登录页
                if page.url != server_url and "login" in page.url:
                    print("导航到服务器页面失败，可能需要重新登录或会话已过期。")
                    page.screenshot(path="server_page_nav_fail.png")
                    return False

            # --- 查找并点击 "ADD 5H" 按钮 ---
            add_button_selector = 'button:has-text("ADD 5H")'
            print(f"正在查找并等待 'ADD 5H' 按钮: {add_button_selector}")

            try:
                # 等待按钮可见并可点击
                page.wait_for_selector(add_button_selector, state='visible', timeout=30000)
                page.click(add_button_selector)
                print("成功点击 'ADD 5H' 按钮。")
                # 增加短暂等待，确保页面有时间处理点击事件或显示确认信息
                time.sleep(5)
                print("等待 5 秒后继续。")
                return True
            except Exception as e:
                print(f"未找到 'ADD 5H' 按钮或点击失败: {e}")
                page.screenshot(path="add_5h_button_not_found.png")
                return False

        except Exception as e:
            print(f"执行过程中发生未知错误: {e}")
            page.screenshot(path="general_error.png")
            return False
        finally:
            browser.close()

if __name__ == "__main__":
    print("开始执行添加服务器时间任务...")
    success = add_server_time()
    if success:
        print("任务执行成功。")
        exit(0)
    else:
        print("任务执行失败。")
        exit(1)
