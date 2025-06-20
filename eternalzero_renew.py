from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from datetime import datetime
import time
import os
import requests
import re

# 从环境变量读取登录凭据
# 默认使用PTERODACTYL_SESSION，账号密码作为备用方案
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
    return webdriver.Chrome(options=options)

def add_cookies(driver, domain):
    """
    向WebDriver添加PTERODACTYL_SESSION cookie。
    """
    print("Current cookies before adding:", driver.get_cookies())
    driver.delete_all_cookies() # 清除现有cookie

    if not SESSION_COOKIE:
        print("PTERODACTYL_SESSION 环境变量未设置，无法使用cookie登录。")
        return False

    cookies = [
        {
            'name': 'PTERODACTYL_SESSION',
            'value': SESSION_COOKIE,
            'domain': domain,
            'path': '/',
            'secure': True,
            'httpOnly': True
        }
    ]
    
    success = True
    for cookie in cookies:
        try:
            driver.add_cookie(cookie)
            print(f"Added cookie: {cookie['name']} for domain {cookie['domain']}")
        except Exception as e:
            print(f"Error adding cookie {cookie['name']}: {str(e)}")
            success = False
    
    print("Current cookies after adding:", driver.get_cookies())
    return success

def login_to_dashboard(driver, login_url, dashboard_base_url):
    """
    尝试通过cookie或邮箱/密码登录到Pterodactyl面板。
    """
    # 尝试cookie登录
    try:
        print("Attempting to login with cookies...")
        driver.get(dashboard_base_url) # 首先访问仪表板URL
        time.sleep(5)
        
        # 提取域名以设置cookie
        domain_match = re.match(r'https?://([^/]+)', dashboard_base_url)
        if domain_match:
            base_domain = domain_match.group(1)
            # 对于某些面板，cookie可能需要设置在主域，例如 gpanel.eternalzero.cloud 的主域是 eternalzero.cloud
            # 这里尝试使用当前URL的域名
            parts = base_domain.split('.')
            if len(parts) > 2:
                # 例如 gpanel.eternalzero.cloud -> .eternalzero.cloud
                cookie_domain = f".{'.'.join(parts[len(parts)-2:])}" 
            else:
                cookie_domain = base_domain

            if add_cookies(driver, cookie_domain): # 传入提取的域名
                print("Refreshing page after adding cookies...")
                driver.refresh()
                time.sleep(8) # 给予更多时间加载
                
                print(f"Current URL after cookie refresh: {driver.current_url}")
                print(f"Current page title: {driver.title}")

                # 检查是否成功登录到仪表板
                # 仪表板通常会有特定元素或标题
                if driver.current_url.startswith(dashboard_base_url) and ('Dashboard' in driver.title or 'Servers' in driver.title or 'Account' in driver.title):
                    print("Cookie login successful!")
                    return True
            else:
                print("Cookie添加失败或未设置。")

        print("Cookie login failed to reach dashboard.")
    except Exception as e:
        print(f"Cookie login error: {str(e)}")
    
    # 如果cookie登录失败，尝试使用邮箱和密码
    try:
        if not EMAIL or not PASSWORD:
            print("邮箱或密码未设置在环境变量中，无法使用邮箱/密码登录。")
            raise ValueError("Email or password not set in environment variables")
        
        print("Attempting to login with email and password...")
        driver.get(login_url)
        
        time.sleep(5) # 等待登录页面加载
        
        # 寻找邮箱、密码输入框和登录按钮的各种选择器
        email_selectors = [
            (By.NAME, 'email'),
            (By.ID, 'email'),
            (By.XPATH, "//input[@type='email']"),
        ]
        
        password_selectors = [
            (By.NAME, 'password'),
            (By.ID, 'password'),
            (By.XPATH, "//input[@type='password']"),
        ]
        
        login_button_selectors = [
            (By.XPATH, "//button[@type='submit']"),
            (By.XPATH, "//button[contains(text(), 'Login')]"),
            (By.XPATH, "//button[contains(text(), '登录')]"),
        ]
        
        email_input = None
        for selector in email_selectors:
            try:
                email_input = WebDriverWait(driver, 10).until(EC.presence_of_element_located(selector))
                print(f"Found email input with selector: {selector}")
                break
            except Exception as e:
                print(f"Failed to find email input with selector {selector}: {e}")
        
        if not email_input:
            raise Exception("Could not find email input field")
        
        password_input = None
        for selector in password_selectors:
            try:
                password_input = WebDriverWait(driver, 10).until(EC.presence_of_element_located(selector))
                print(f"Found password input with selector: {selector}")
                break
            except Exception as e:
                print(f"Failed to find password input with selector {selector}: {e}")
        
        if not password_input:
            raise Exception("Could not find password input field")
        
        login_button = None
        for selector in login_button_selectors:
            try:
                login_button = WebDriverWait(driver, 10).until(EC.presence_of_element_located(selector))
                print(f"Found login button with selector: {selector}")
                break
            except Exception as e:
                print(f"Failed to find login button with selector {selector}: {e}")
        
        if not login_button:
            raise Exception("Could not find login button")
        
        email_input.clear()
        email_input.send_keys(EMAIL)
        password_input.clear()
        password_input.send_keys(PASSWORD)
        
        login_button.click()
        
        time.sleep(10) # 等待登录完成
        
        print(f"Current URL after email login: {driver.current_url}")
        print(f"Current page title: {driver.title}")
        
        # 检查是否成功登录到仪表板
        if driver.current_url.startswith(dashboard_base_url) and ('Dashboard' in driver.title or 'Servers' in driver.title or 'Account' in driver.title):
            print("Email/password login successful!")
            return True
        
        raise Exception("Login did not reach dashboard")
    
    except Exception as e:
        print(f"Login failed: {str(e)}")
        send_telegram_message(f"EternalZero Auto Renew Login Error: {str(e)}")
        return False

def send_telegram_message(message):
    """
    发送Telegram通知。
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram bot token or chat ID not configured. Skipping Telegram notification.")
        return False
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown" # 支持Markdown格式
    }
    
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()  # 如果请求失败则抛出HTTPError
        print("Telegram notification sent successfully.")
        return True
    except Exception as e:
        print(f"Failed to send Telegram notification: {e}")
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
    with open('last_renew_data.txt', 'w', encoding='utf-8') as f:
        f.write(content)
    
    # 发送Telegram通知
    telegram_message = f"**EternalZero 服务器续期通知**\n{content}"
    send_telegram_message(telegram_message)

def main():
    driver = None
    LOGIN_URL = 'https://gpanel.eternalzero.cloud/auth/login'
    DASHBOARD_BASE_URL = 'https://gpanel.eternalzero.cloud'
    SERVER_URL = 'https://gpanel.eternalzero.cloud/server/5302206f' # 您的服务器特定URL

    try:
        print("Starting browser...")
        driver = setup_driver()
        driver.set_page_load_timeout(60) # 设置页面加载超时时间
        
        # 尝试登录
        if not login_to_dashboard(driver, LOGIN_URL, DASHBOARD_BASE_URL):
            raise Exception("Unable to login to EternalZero dashboard.")
        
        print(f"Successfully logged in. Navigating to server page: {SERVER_URL}")
        driver.get(SERVER_URL)
        
        print("Waiting for server page to load completely...")
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        time.sleep(5) # 额外等待，确保所有元素加载
        
        print(f"Current URL after navigating to server page: {driver.current_url}")
        print(f"Server page title: {driver.title}")
        driver.save_screenshot('debug_server_page_initial.png') # 截图方便调试
        
        # 尝试获取服务器ID
        server_id = 'Unknown'
        try:
            server_id_match = re.search(r'/server/([a-f0-9]+)', driver.current_url)
            if server_id_match:
                server_id = server_id_match.group(1)
                print(f"Extracted Server ID: {server_id}")
        except Exception as e:
            print(f"Error extracting server ID: {e}")

        # 寻找并点击 "ADD 5H" 按钮
        renew_button_selectors = [
            (By.XPATH, "//button[.//span[contains(text(), 'ADD 5H')]]"), # 匹配包含 'ADD 5H' 文本的span的button
            (By.XPATH, "//button[contains(., 'ADD 5H')]"), # 匹配包含 'ADD 5H' 文本的button
            (By.CSS_SELECTOR, "button:has(span:contains('ADD 5H'))"), # CSS选择器 (需要Selenium 4.x版本且浏览器支持:has())
            (By.CSS_SELECTOR, "button.btn.btn-primary.some-class-if-exists") # 如果有明确的class可以添加
        ]

        renew_button = None
        for selector_type, selector_value in renew_button_selectors:
            try:
                print(f"Looking for renew button with {selector_type}: {selector_value}")
                # 使用WebDriverWait等待按钮出现并可点击
                renew_button = WebDriverWait(driver, 20).until(
                    EC.element_to_be_clickable((selector_type, selector_value))
                )
                print(f"Found renew button with text: '{renew_button.text}'")
                print(f"Button HTML: {renew_button.get_attribute('outerHTML')}")
                break
            except Exception as e:
                print(f"Failed to find button with {selector_type} selector {selector_value}: {str(e)}")
                continue

        if not renew_button:
            raise Exception("Could not find 'ADD 5H' renew button.")

        # 点击续期按钮
        print("Clicking 'ADD 5H' button...")
        renew_button.click()
        
        # 点击后等待，等待页面更新或提示信息出现
        print("Waiting for renewal process to complete...")
        time.sleep(10) # 初始等待
        
        # 尝试刷新页面并检查是否成功
        print("Refreshing page to check renewal status...")
        driver.refresh()
        time.sleep(10) # 刷新后再次等待加载
        
        driver.save_screenshot('debug_after_renew_click.png') # 续期点击后截图
        print(f"Current URL after refresh: {driver.current_url}")
        
        # 验证续期是否成功
        # 假设续期成功后会有一些提示信息，或者按钮状态变化
        success_indicators = [
            (By.XPATH, "//div[contains(text(), 'Server renewed successfully')]"), # 常见成功提示
            (By.XPATH, "//span[contains(text(), 'Your server has been renewed')]"),
            (By.XPATH, "//button[.//span[contains(text(), 'ADD 5H')]]"), # 检查按钮是否仍然存在（如果每次点击都增加时间，按钮可能不变）
            (By.CSS_SELECTOR, ".alert.alert-success") # 成功提示框
        ]
        
        renewal_successful = False
        message = "续期操作已执行，但未找到明确的成功提示。"
        for selector_type, selector_value in success_indicators:
            try:
                # 检查元素是否存在，不强制等待其可点击
                element = driver.find_element(selector_type, selector_value)
                if element.is_displayed():
                    print(f"Found success indicator: {element.text}")
                    renewal_successful = True
                    message = "服务器续期成功！"
                    break
            except NoSuchElementException:
                continue
            except Exception as e:
                print(f"Error checking success indicator {selector_value}: {e}")
                continue

        # 如果没有找到成功提示，检查是否有错误提示
        if not renewal_successful:
            error_indicators = [
                (By.CSS_SELECTOR, ".alert.alert-danger"), # 错误提示框
                (By.XPATH, "//div[contains(text(), 'Error')]"),
                (By.XPATH, "//span[contains(text(), 'Failed to renew')]")
            ]
            
            for selector_type, selector_value in error_indicators:
                try:
                    error_element = driver.find_element(selector_type, selector_value)
                    if error_element.is_displayed():
                        message = f"服务器续期失败: {error_element.text}"
                        print(message)
                        break
                except NoSuchElementException:
                    continue
                except Exception as e:
                    print(f"Error checking error indicator {selector_value}: {e}")
                    continue
            if message == "续期操作已执行，但未找到明确的成功提示。": # 如果既没有成功也没有明确错误
                message += "请手动检查服务器状态。"

        update_last_renew_status(renewal_successful, message, server_id)

    except TimeoutException as e:
        error_msg = f"操作超时错误: {str(e)}。当前URL: {driver.current_url}"
        print(error_msg)
        if driver:
            driver.save_screenshot('error_timeout.png')
        update_last_renew_status(False, error_msg, server_id='Unknown')
    except Exception as e:
        error_msg = f"发生未知错误: {str(e)}。当前URL: {driver.current_url if driver else 'N/A'}"
        print(error_msg)
        if driver:
            driver.save_screenshot('error_general.png')
        update_last_renew_status(False, error_msg, server_id='Unknown')
    finally:
        if driver:
            try:
                driver.quit()
                print("Browser closed.")
            except Exception as e:
                print(f"关闭浏览器时发生错误: {str(e)}")

if __name__ == "__main__":
    main()
