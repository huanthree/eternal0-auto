from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
from datetime import datetime
import time
import os
import requests
import re
import sys # 导入sys模块

# 从环境变量读取登录凭据
EMAIL = os.getenv('EMAIL', '')        # 登录邮箱
PASSWORD = os.getenv('PASSWORD', '')  # 登录密码
SESSION_COOKIE = os.getenv('PTERODACTYL_SESSION', '') # PTERODACTYL_SESSION cookie值

# Telegram Bot 通知配置（可选）
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '')

def setup_driver():
    """
    设置Chrome WebDriver选项，包括无头模式、沙盒禁用等。
    """
    options = webdriver.ChromeOptions()
    options.add_argument('--headless') # 无头模式运行
    options.add_argument('--no-sandbox') # 禁用沙盒模式，GitHub Actions需要
    options.add_argument('--disable-dev-shm-usage') # 禁用/dev/shm使用，GitHub Actions需要
    options.add_argument('--disable-gpu') # 禁用GPU硬件加速
    options.add_argument('--window-size=1920,1080') # 设置窗口大小
    options.add_argument('--start-maximized') # 启动时最大化窗口
    options.add_argument('--enable-logging') # 启用日志
    options.add_argument('--v=1') # 详细日志
    options.add_argument('--disable-blink-features=AutomationControlled') # 避免被检测为自动化
    options.add_argument('--disable-extensions') # 禁用扩展
    # 添加一个随机的用户代理，减少被检测的风险
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
    
    try:
        driver = webdriver.Chrome(options=options)
        driver.set_page_load_timeout(60) # 设置页面加载超时时间
        return driver
    except WebDriverException as e:
        print(f"WebDriver 初始化失败: {e}")
        print("请确保 ChromeDriver 版本与 Chrome 浏览器版本匹配，并且 PATH 中包含 ChromeDriver。")
        sys.exit(1) # 退出脚本

def add_cookies(driver, domain):
    """
    向WebDriver添加PTERODACTYL_SESSION cookie。
    """
    print("Current cookies before adding:", driver.get_cookies())
    driver.delete_all_cookies() # 清除现有cookie

    if not SESSION_COOKIE:
        print("PTERODACTYL_SESSION 环境变量未设置，无法使用cookie登录。")
        return False

    # 尝试多种 domain 格式
    domains_to_try = [
        domain, # 原始域名 (e.g., gpanel.eternalzero.cloud)
        f".{domain}", # 带前缀的原始域名
    ]
    
    # 提取顶级域名
    parts = domain.split('.')
    if len(parts) >= 2:
        top_level_domain = f".{'.'.join(parts[len(parts)-2:])}" # 例如 .eternalzero.cloud
        if top_level_domain not in domains_to_try:
            domains_to_try.append(top_level_domain)
        top_level_domain_no_dot = '.'.join(parts[len(parts)-2:]) # 例如 eternalzero.cloud
        if top_level_domain_no_dot not in domains_to_try:
            domains_to_try.append(top_level_domain_no_dot)

    success = False
    for d in domains_to_try:
        try:
            cookie = {
                'name': 'PTERODACTYL_SESSION',
                'value': SESSION_COOKIE,
                'domain': d,
                'path': '/',
                'secure': True,
                'httpOnly': True
            }
            driver.add_cookie(cookie)
            print(f"尝试添加 cookie: {cookie['name']} for domain {cookie['domain']}")
            success = True # 只要一个成功就标记成功
            break # 找到一个成功的就跳出
        except Exception as e:
            print(f"添加 cookie {cookie['name']} 到域 {d} 失败: {str(e)}")
            continue
    
    print("Current cookies after adding:", driver.get_cookies())
    return success

def login_to_dashboard(driver, login_url, dashboard_base_url):
    """
    尝试通过cookie或邮箱/密码登录到Pterodactyl面板。
    """
    # 提取域名以设置cookie
    domain_match = re.match(r'https?://([^/]+)', dashboard_base_url)
    base_domain = domain_match.group(1) if domain_match else "gpanel.eternalzero.cloud" # 默认值

    # 尝试cookie登录
    try:
        print("尝试使用 cookies 登录...")
        driver.get(dashboard_base_url) # 首先访问仪表板URL
        time.sleep(3) # 短暂等待
        driver.save_screenshot('debug_before_cookie_add.png')

        if add_cookies(driver, base_domain): # 传入提取的域名
            print("添加 cookies 后刷新页面...")
            driver.refresh()
            time.sleep(8) # 给予更多时间加载
            driver.save_screenshot('debug_after_cookie_refresh.png')
            
            print(f"Cookie 刷新后当前 URL: {driver.current_url}")
            print(f"Cookie 刷新后当前页面标题: {driver.title}")

            # 检查是否成功登录到仪表板
            if driver.current_url.startswith(dashboard_base_url) and \
               ('Dashboard' in driver.title or 'Servers' in driver.title or 'Account' in driver.title or 'Pterodactyl' in driver.title):
                print("Cookie 登录成功！")
                return True
        else:
            print("Cookie 添加失败或未设置环境变量。")

        print("Cookie 登录未能到达仪表板。")
    except Exception as e:
        print(f"Cookie 登录过程中发生错误: {str(e)}")
    
    # 如果cookie登录失败或未配置，尝试使用邮箱和密码
    try:
        if not EMAIL or not PASSWORD:
            print("邮箱或密码未设置在环境变量中，无法使用邮箱/密码登录。")
            send_telegram_message("EternalZero Auto Renew 错误: 邮箱或密码未设置。")
            return False
        
        print("尝试使用邮箱和密码登录...")
        driver.get(login_url)
        
        time.sleep(5) # 等待登录页面加载
        driver.save_screenshot('debug_login_page_initial.png') # 登录页面初始截图

        # 寻找邮箱、密码输入框和登录按钮的各种选择器
        # **重要：请根据实际登录页面HTML进行调整**
        email_selectors = [
            (By.NAME, 'email'),
            (By.ID, 'email'),
            (By.XPATH, "//input[@type='email']"),
            (By.CSS_SELECTOR, "input[name='email']"), # 推荐 CSS 选择器
            (By.CSS_SELECTOR, "input#email"),
            (By.CSS_SELECTOR, "input[placeholder*='Email']") # 寻找 placeholder 包含 'Email' 的输入框
        ]
        
        password_selectors = [
            (By.NAME, 'password'),
            (By.ID, 'password'),
            (By.XPATH, "//input[@type='password']"),
            (By.CSS_SELECTOR, "input[name='password']"), # 推荐 CSS 选择器
            (By.CSS_SELECTOR, "input#password"),
            (By.CSS_SELECTOR, "input[placeholder*='Password']") # 寻找 placeholder 包含 'Password' 的输入框
        ]
        
        login_button_selectors = [
            (By.XPATH, "//button[@type='submit']"),
            (By.XPATH, "//button[contains(text(), 'Login')]"),
            (By.XPATH, "//button[contains(text(), '登录')]"),
            (By.CSS_SELECTOR, "button[type='submit']"), # 推荐 CSS 选择器
            (By.CSS_SELECTOR, "button:contains('Login')") # Selenium 4 兼容 :contains
        ]
        
        email_input = None
        for selector_type, selector_value in email_selectors:
            try:
                print(f"尝试查找邮箱输入框: {selector_type}: {selector_value}")
                email_input = WebDriverWait(driver, 15).until(EC.presence_of_element_located((selector_type, selector_value)))
                print(f"找到邮箱输入框: {selector_type}: {selector_value}")
                break
            except TimeoutException:
                print(f"未找到邮箱输入框: {selector_type}: {selector_value} (超时)")
            except Exception as e:
                print(f"查找邮箱输入框时发生错误 {selector_type}: {selector_value}: {e}")
        
        if not email_input:
            driver.save_screenshot('debug_login_no_email_input.png')
            raise Exception("未能找到邮箱输入字段，请检查页面HTML结构。")
        
        password_input = None
        for selector_type, selector_value in password_selectors:
            try:
                print(f"尝试查找密码输入框: {selector_type}: {selector_value}")
                password_input = WebDriverWait(driver, 15).until(EC.presence_of_element_located((selector_type, selector_value)))
                print(f"找到密码输入框: {selector_type}: {selector_value}")
                break
            except TimeoutException:
                print(f"未找到密码输入框: {selector_type}: {selector_value} (超时)")
            except Exception as e:
                print(f"查找密码输入框时发生错误 {selector_type}: {selector_value}: {e}")
        
        if not password_input:
            driver.save_screenshot('debug_login_no_password_input.png')
            raise Exception("未能找到密码输入字段，请检查页面HTML结构。")
        
        login_button = None
        for selector_type, selector_value in login_button_selectors:
            try:
                print(f"尝试查找登录按钮: {selector_type}: {selector_value}")
                login_button = WebDriverWait(driver, 15).until(EC.element_to_be_clickable((selector_type, selector_value)))
                print(f"找到登录按钮: {selector_type}: {selector_value}")
                break
            except TimeoutException:
                print(f"未找到登录按钮: {selector_type}: {selector_value} (超时)")
            except Exception as e:
                print(f"查找登录按钮时发生错误 {selector_type}: {selector_value}: {e}")
        
        if not login_button:
            driver.save_screenshot('debug_login_no_button.png')
            raise Exception("未能找到登录按钮，请检查页面HTML结构。")
        
        email_input.clear()
        email_input.send_keys(EMAIL)
        password_input.clear()
        password_input.send_keys(PASSWORD)
        
        print("点击登录按钮...")
        login_button.click()
        
        time.sleep(10) # 等待登录完成
        driver.save_screenshot('debug_after_email_login_click.png') # 登录点击后截图
        
        print(f"邮箱登录后当前 URL: {driver.current_url}")
        print(f"邮箱登录后当前页面标题: {driver.title}")
        
        # 检查是否成功登录到仪表板
        if driver.current_url.startswith(dashboard_base_url) and \
           ('Dashboard' in driver.title or 'Servers' in driver.title or 'Account' in driver.title or 'Pterodactyl' in driver.title):
            print("邮箱/密码登录成功！")
            return True
        
        # 检查是否有错误提示
        error_message_selectors = [
            (By.CSS_SELECTOR, ".alert.alert-danger"),
            (By.XPATH, "//*[contains(@class, 'alert-danger')]"),
            (By.XPATH, "//*[contains(text(), 'Credentials do not match')]"),
            (By.XPATH, "//*[contains(text(), '登录失败')]")
        ]
        
        for selector_type, selector_value in error_message_selectors:
            try:
                error_element = driver.find_element(selector_type, selector_value)
                if error_element.is_displayed():
                    error_text = error_element.text
                    print(f"登录页面显示错误信息: {error_text}")
                    send_telegram_message(f"EternalZero Auto Renew 登录失败: {error_text}")
                    return False
            except NoSuchElementException:
                continue
            except Exception as e:
                print(f"检查登录错误信息时发生错误: {e}")

        raise Exception("登录未能到达仪表板，且未找到明确的成功或失败提示。")
    
    except Exception as e:
        error_msg = f"登录失败: {str(e)}"
        print(error_msg)
        driver.save_screenshot('debug_login_final_failure.png')
        send_telegram_message(f"EternalZero Auto Renew 登录错误: {str(e)}")
        return False

def send_telegram_message(message):
    """
    发送Telegram通知。
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram bot token 或 chat ID 未配置。跳过 Telegram 通知。")
        return False
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown" # 支持Markdown格式
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10) # 增加超时
        response.raise_for_status()  # 如果请求失败则抛出HTTPError
        print("Telegram 通知发送成功。")
        return True
    except requests.exceptions.Timeout:
        print("发送 Telegram 通知超时。")
        return False
    except requests.exceptions.RequestException as e:
        print(f"发送 Telegram 通知失败: {e}")
        return False

def update_last_renew_status(success, message, server_id=None):
    """
    更新续期状态并发送Telegram通知。
    """
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    status = "成功" if success else "失败"
    
    content = f"服务器ID: {server_id or '未知'}\n"
    content += f"续期状态: {status}\n"
    content += f"执行时间: {current_time}\n"
    content += f"信息: {message}"
    
    # 写入文件（可选，用于本地记录）
    try:
        with open('last_renew_data.txt', 'w', encoding='utf-8') as f:
            f.write(content)
        print("续期状态已写入 last_renew_data.txt")
    except Exception as e:
        print(f"写入续期状态文件失败: {e}")
    
    # 发送Telegram通知
    telegram_message = f"**EternalZero 服务器续期通知**\n{content}"
    send_telegram_message(telegram_message)

def perform_renewal_action(driver, server_url):
    """
    执行服务器续期操作。
    """
    server_id = 'Unknown'
    try:
        print(f"导航到服务器页面: {server_url}")
        driver.get(server_url)
        
        print("等待服务器页面完全加载...")
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        time.sleep(5) # 额外等待，确保所有元素加载
        
        print(f"导航到服务器页面后当前 URL: {driver.current_url}")
        print(f"服务器页面标题: {driver.title}")
        driver.save_screenshot('debug_server_page_initial.png') # 截图方便调试
        
        # 尝试获取服务器ID
        try:
            server_id_match = re.search(r'/server/([a-f0-9]+)', driver.current_url)
            if server_id_match:
                server_id = server_id_match.group(1)
                print(f"提取的服务器 ID: {server_id}")
        except Exception as e:
            print(f"提取服务器 ID 失败: {e}")

        # 寻找并点击 "ADD 5H" 按钮
        # 建议您检查实际页面HTML，寻找更健壮的选择器
        renew_button_selectors = [
            (By.XPATH, "//button[.//span[contains(text(), 'ADD 5H')]]"), # 匹配包含 'ADD 5H' 文本的span的button
            (By.XPATH, "//button[contains(., 'ADD 5H')]"), # 匹配包含 'ADD 5H' 文本的button
            (By.CSS_SELECTOR, "button:has(span:contains('ADD 5H'))"), # CSS选择器 (Selenium 4.x版本且浏览器支持:has())
            (By.CSS_SELECTOR, "button.btn-primary"), # 如果按钮有明确的class且是唯一的，可以使用
            # 添加更多基于实际HTML的选择器
        ]

        renew_button = None
        for selector_type, selector_value in renew_button_selectors:
            try:
                print(f"寻找续期按钮: {selector_type}: {selector_value}")
                renew_button = WebDriverWait(driver, 20).until(
                    EC.element_to_be_clickable((selector_type, selector_value))
                )
                print(f"找到续期按钮，文本为: '{renew_button.text}'")
                print(f"按钮 HTML: {renew_button.get_attribute('outerHTML')}")
                break
            except TimeoutException:
                print(f"未找到续期按钮: {selector_type}: {selector_value} (超时)")
            except Exception as e:
                print(f"寻找续期按钮时发生错误 {selector_type}: {selector_value}: {str(e)}")
                continue

        if not renew_button:
            raise Exception("未能找到 'ADD 5H' 续期按钮，请检查页面HTML或选择器。")

        # 点击续期按钮
        print("点击 'ADD 5H' 按钮...")
        renew_button.click()
        
        # 点击后等待，等待页面更新或提示信息出现
        print("等待续期流程完成...")
        time.sleep(10) # 初始等待
        
        # 尝试刷新页面并检查是否成功
        print("刷新页面检查续期状态...")
        driver.refresh()
        time.sleep(10) # 刷新后再次等待加载
        
        driver.save_screenshot('debug_after_renew_click.png') # 续期点击后截图
        print(f"刷新后当前 URL: {driver.current_url}")
        
        # 验证续期是否成功
        success_indicators = [
            (By.XPATH, "//div[contains(text(), 'Server renewed successfully')]"),
            (By.XPATH, "//span[contains(text(), 'Your server has been renewed')]"),
            (By.CSS_SELECTOR, ".alert.alert-success"), # 成功提示框
            (By.XPATH, "//*[contains(@class, 'alert-success')]"),
            # 检查页面上表示时间已增加的元素（例如，服务器过期时间文本）
            # 这需要更具体的分析，例如通过 XPath 查找包含“到期时间：”的元素并检查日期
        ]
        
        renewal_successful = False
        message = "续期操作已执行，但未找到明确的成功提示。"
        for selector_type, selector_value in success_indicators:
            try:
                element = WebDriverWait(driver, 5).until(EC.visibility_of_element_located((selector_type, selector_value)))
                if element.is_displayed():
                    print(f"找到成功指示器: {element.text}")
                    renewal_successful = True
                    message = f"服务器续期成功！提示信息：{element.text}"
                    break
            except TimeoutException:
                continue
            except Exception as e:
                print(f"检查成功指示器 {selector_value} 时发生错误: {e}")
                continue

        # 如果没有找到成功提示，检查是否有错误提示
        if not renewal_successful:
            error_indicators = [
                (By.CSS_SELECTOR, ".alert.alert-danger"),
                (By.XPATH, "//*[contains(@class, 'alert-danger')]"),
                (By.XPATH, "//div[contains(text(), 'Error')]"),
                (By.XPATH, "//span[contains(text(), 'Failed to renew')]")
            ]
            
            for selector_type, selector_value in error_indicators:
                try:
                    error_element = WebDriverWait(driver, 5).until(EC.visibility_of_element_located((selector_type, selector_value)))
                    if error_element.is_displayed():
                        message = f"服务器续期失败: {error_element.text}"
                        print(message)
                        break
                except TimeoutException:
                    continue
                except Exception as e:
                    print(f"检查错误指示器 {selector_value} 时发生错误: {e}")
                    continue
            if message == "续期操作已执行，但未找到明确的成功提示。":
                message += "请手动检查服务器状态。"

        update_last_renew_status(renewal_successful, message, server_id)
        return renewal_successful # 返回续期结果

    except TimeoutException as e:
        error_msg = f"操作超时错误: {str(e)}。当前URL: {driver.current_url}"
        print(error_msg)
        driver.save_screenshot('error_timeout_renewal.png')
        update_last_renew_status(False, error_msg, server_id)
        return False
    except Exception as e:
        error_msg = f"执行续期操作时发生未知错误: {str(e)}。当前URL: {driver.current_url}"
        print(error_msg)
        driver.save_screenshot('error_general_renewal.png')
        update_last_renew_status(False, error_msg, server_id)
        return False

def main():
    LOGIN_URL = 'https://gpanel.eternalzero.cloud/auth/login'
    DASHBOARD_BASE_URL = 'https://gpanel.eternalzero.cloud'
    SERVER_URL = 'https://gpanel.eternalzero.cloud/server/5302206f' # 您的服务器特定URL
    RENEWAL_INTERVAL_HOURS = 3 # 每3小时点击一次

    # 主循环，实现定时执行
    while True:
        driver = None
        try:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 开始执行 EternalZero 服务器续期任务...")
            driver = setup_driver()
            
            # 尝试登录
            if not login_to_dashboard(driver, LOGIN_URL, DASHBOARD_BASE_URL):
                raise Exception("无法登录到 EternalZero 仪表板，将重试。")
            
            # 执行续期操作
            renewal_success = perform_renewal_action(driver, SERVER_URL)
            if renewal_success:
                print("服务器续期任务执行成功。")
            else:
                print("服务器续期任务执行完成，但可能未成功。请检查日志。")

        except Exception as e:
            error_msg = f"整个续期流程发生错误: {str(e)}"
            print(error_msg)
            update_last_renew_status(False, error_msg, server_id='N/A')
        finally:
            if driver:
                try:
                    driver.quit()
                    print("浏览器已关闭。")
                except Exception as e:
                    print(f"关闭浏览器时发生错误: {str(e)}")
        
        print(f"任务完成。等待 {RENEWAL_INTERVAL_HOURS} 小时后再次执行...")
        time.sleep(RENEWAL_INTERVAL_HOURS * 3600) # 转换为秒

if __name__ == "__main__":
    main()
